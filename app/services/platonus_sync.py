"""
Сервис синхронизации данных сотрудников из Platonus
Запускается раз в неделю
"""

from datetime import datetime
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text, delete
from sshtunnel import SSHTunnelForwarder
from sqlalchemy import create_engine
import logging
import asyncio

from app.models import AttendanceRecord, PlatonusEmployee
from app.core.config import settings

logger = logging.getLogger(__name__)


def determine_position_type(
    position_name: Optional[str],
    cafedra_id: Optional[int] = None,
    subdivision_id: Optional[int] = None
) -> Optional[str]:
    """
    Определить тип должности

    Логика:
    1. Если есть кафедра - это преподаватель (даже если должность не указана)
    2. Если есть подразделение но нет кафедры - определяем по должности или "Административный персонал"
    3. Если есть должность - определяем по ключевым словам
    """

    # Если есть кафедра - это точно преподаватель
    if cafedra_id and cafedra_id > 0:
        return "Преподаватель"

    # Если нет должности
    if not position_name:
        # Есть подразделение - административный персонал
        if subdivision_id and subdivision_id > 0:
            return "Административный персонал"
        return None

    position_lower = position_name.lower()

    # Преподаватели (по ключевым словам)
    if any(word in position_lower for word in ["профессор", "доцент", "преподаватель", "лектор", "ассистент"]):
        return "Преподаватель"

    # Руководители
    if any(
        word in position_lower
        for word in [
            "декан",
            "проректор",
            "ректор",
            "президент",
            "вице-президент",
            "директор",
            "заместитель",
            "начальник",
            "руководитель",
            "зав",
            "зам",
        ]
    ):
        return "Руководитель"

    # Специалисты
    if "специалист" in position_lower or "методист" in position_lower:
        return "Специалист"

    # Технический персонал
    if any(word in position_lower for word in ["лаборант", "инженер"]):
        return "Технический персонал"

    # Административный персонал (если есть подразделение)
    if subdivision_id and subdivision_id > 0:
        return "Административный персонал"

    return "Прочие"


class PlatonusSyncService:
    """Сервис синхронизации данных из Platonus"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def sync_employees(self) -> dict:
        """
        Синхронизировать данные сотрудников из Platonus

        Процесс:
        1. Получить всех уникальных пользователей с IIN из HikCentral (не студентов)
        2. Для каждого IIN получить данные из Platonus
        3. Сохранить/обновить в таблице platonus_employees
        """

        logger.info("Начало синхронизации сотрудников из Platonus")

        try:
            # Шаг 1: Получить всех уникальных пользователей с IIN (не студентов)
            logger.info("Получение списка сотрудников из HikCentral...")

            query = text("""
                SELECT DISTINCT iin, person_name
                FROM attendance_records
                WHERE iin IS NOT NULL
                AND iin != ''
                AND iin ~ '^[0-9]{12}$'
                AND person_group LIKE '%Сотрудники YU%'
                ORDER BY iin;
            """)

            result = await self.db.execute(query)
            hikcentral_employees = result.fetchall()

            logger.info(f"Найдено {len(hikcentral_employees)} уникальных сотрудников в HikCentral")

            if not hikcentral_employees:
                return {"status": "success", "synced": 0, "message": "Нет сотрудников для синхронизации"}

            # Шаг 2: Подключиться к Platonus и получить данные
            logger.info("Подключение к Platonus...")

            synced_count = 0
            not_found_count = 0
            error_count = 0

            tunnel = None
            platonus_engine = None
            platonus_conn = None

            try:
                # Создать SSH туннель (синхронная операция)
                def create_and_start_tunnel():
                    t = SSHTunnelForwarder(
                        (settings.PLATONUS_SSH_HOST, settings.PLATONUS_SSH_PORT),
                        ssh_username=settings.PLATONUS_SSH_USER,
                        ssh_password=settings.PLATONUS_SSH_PASSWORD,
                        remote_bind_address=(settings.PLATONUS_DB_HOST, settings.PLATONUS_DB_PORT),
                        local_bind_address=("127.0.0.1", 0),
                        allow_agent=False,
                        host_pkey_directories=[],
                        compression=True,
                        set_keepalive=30,
                    )
                    t.start()
                    return t

                # Запустить в отдельном потоке
                loop = asyncio.get_event_loop()
                tunnel = await loop.run_in_executor(None, create_and_start_tunnel)
                logger.info(f"SSH туннель установлен на порту {tunnel.local_bind_port}")

                # Подключение к MySQL Platonus
                db_url = settings.platonus_db_url(tunnel.local_bind_port)
                platonus_engine = create_engine(db_url, echo=False)

                platonus_conn = platonus_engine.connect()
                logger.info("Подключено к Platonus")

                # Для каждого IIN получить данные из Platonus
                batch_size = 50
                for idx, (iin, person_name) in enumerate(hikcentral_employees, 1):
                        if idx % batch_size == 0:
                            logger.info(f"Обработано {idx}/{len(hikcentral_employees)}...")

                        try:
                            # Запрос к Platonus
                            # Берем запись с максимальной ставкой (RATE)
                            # Если есть RATE = 1, берем её; если нет - берем максимальную доступную
                            platonus_query = text("""
                                SELECT
                                    t.TutorID,
                                    t.iinplt,
                                    t.firstname,
                                    t.lastname,
                                    t.patronymic,
                                    tp.nameRU as position_name,
                                    t.CafedraID,
                                    c.cafedraNameRU as cafedra_name,
                                    f.FacultyID as faculty_id,
                                    f.facultyNameRU as faculty_name,
                                    t.mail,
                                    t.mobilePhone,
                                    t.departmentid as subdivision_id,
                                    ss.nameru as subdivision_name,
                                    ss.subdivision_type,
                                    t.RATE
                                FROM tutors t
                                LEFT JOIN tutor_positions tp ON t.job_title_int = tp.id
                                LEFT JOIN cafedras c ON t.CafedraID = c.cafedraID
                                LEFT JOIN faculties f ON c.FacultyID = f.FacultyID
                                LEFT JOIN structural_subdivision ss ON t.departmentid = ss.id
                                WHERE t.iinplt = :iin
                                ORDER BY t.RATE DESC
                                LIMIT 1;
                            """)

                            result = platonus_conn.execute(platonus_query, {"iin": iin})
                            row = result.fetchone()

                            if row:
                                # Данные найдены в Platonus
                                rate = row[15]

                                # Логировать если RATE != 1 (для отладки)
                                if rate != 1.0 and idx % 50 == 1:
                                    logger.info(f"Сотрудник {person_name} синхронизирован с RATE = {rate}")

                                # Определить тип должности на основе должности, кафедры и подразделения
                                position_type = determine_position_type(
                                    position_name=row[5],
                                    cafedra_id=row[6],
                                    subdivision_id=row[12]
                                )

                                # Логика для определения основного места работы:
                                #
                                # Случай 1: Есть И кафедра И подразделение
                                #   → Проверяем должность:
                                #      - Если преподавательская (профессор, доцент, преподаватель, учитель, лектор, ассистент)
                                #        → используем КАФЕДРУ (subdivision_id = NULL)
                                #      - Если НЕ преподавательская (консультант, специалист и т.д.)
                                #        → используем ПОДРАЗДЕЛЕНИЕ (cafedra_id сохраняем, но subdivision - основное место)
                                #
                                # Случай 2: Есть ТОЛЬКО кафедра (нет подразделения)
                                #   → ПРЕПОДАВАТЕЛЬ (используем кафедру)
                                #
                                # Случай 3: Есть ТОЛЬКО подразделение (нет кафедры)
                                #   → АДМИНИСТРАТИВНЫЙ ПЕРСОНАЛ (используем подразделение)
                                #
                                # Примеры:
                                #   1. Кенесары: CafedraID=15, DepartmentID=50, должность="Учитель-тренер"
                                #      → subdivision=NULL (преподаватель)
                                #   2. Ерлан: CafedraID=11, DepartmentID=5, должность="Консультант..."
                                #      → subdivision=5 (административный персонал в офисе президента)
                                #   3. Библиотекарь: CafedraID=0, DepartmentID=43
                                #      → subdivision=43 (административный персонал)

                                cafedra_id = row[6]
                                dept_id = row[12]
                                position_name = row[5]

                                # Проверка является ли должность ЯВНО административной (не преподавательской)
                                def is_administrative_position(pos_name: Optional[str]) -> bool:
                                    """
                                    Проверка явно непреподавательских должностей на основе списка tutor_positions.

                                    Преподавательские должности (НЕ в списке АУП):
                                    - Профессор, Доцент, Преподаватель, Ассистент, Лектор

                                    Все остальные должности из tutor_positions - это АУП
                                    """
                                    if not pos_name:
                                        return False  # NULL не является явной административной должностью

                                    pos_lower = pos_name.lower()

                                    # Сначала проверяем ПРЕПОДАВАТЕЛЬСКИЕ должности
                                    # Если это преподаватель - возвращаем False (НЕ административный)
                                    teaching_keywords = [
                                        "профессор", "доцент", "преподаватель", "ассистент", "лектор",
                                        "учитель"  # Включая учитель-тренер
                                    ]
                                    if any(keyword in pos_lower for keyword in teaching_keywords):
                                        return False

                                    # Все остальные должности из списка - это АУП
                                    # Проверяем по ключевым словам из списка tutor_positions
                                    admin_keywords = [
                                        # Разработчики и IT
                                        "разработчик", "программист", "дизайнер", "администратор",
                                        # Специалисты
                                        "специалист", "ведущий", "главный", "старший",
                                        # Руководители
                                        "руководитель", "директор", "декан", "проректор", "президент",
                                        "вице-", "заведующий", "зам", "начальник", "председатель",
                                        # Советники и помощники
                                        "консультант", "советник", "помощник", "ассистент президента", "референт",
                                        # Офисные
                                        "менеджер", "координатор", "секретарь", "офицер",
                                        # Финансы и право
                                        "бухгалтер", "экономист", "юрист",
                                        # Техперсонал и другие
                                        "инженер", "лаборант", "методист", "библиотекарь",
                                        "механик", "электрик", "сантехник", "водитель", "охранник",
                                        "уборщица", "дворник", "рабочий", "мастер", "садовник",
                                        "воспитатель", "медсестра", "наставник", "оператор",
                                        "инструктор",  # НЕ включаем "учитель" и "тренер" - они преподаватели
                                        "сотрудник", "аналитик", "маркетолог"
                                    ]
                                    return any(keyword in pos_lower for keyword in admin_keywords)

                                # Определение subdivision_id
                                if cafedra_id and cafedra_id > 0 and dept_id and dept_id > 0:
                                    # Есть И кафедра И подразделение → проверяем должность
                                    if is_administrative_position(position_name):
                                        # ЯВНО административная должность → приоритет подразделению
                                        subdivision_id = dept_id
                                        subdivision_name = row[13]
                                        subdivision_type = row[14]
                                    else:
                                        # НЕ административная (преподавательская или NULL) → приоритет кафедре
                                        subdivision_id = None
                                        subdivision_name = None
                                        subdivision_type = None
                                elif cafedra_id and cafedra_id > 0:
                                    # Есть ТОЛЬКО кафедра → ПРЕПОДАВАТЕЛЬ
                                    subdivision_id = None
                                    subdivision_name = None
                                    subdivision_type = None
                                elif dept_id and dept_id > 0:
                                    # Есть ТОЛЬКО подразделение → АДМИНИСТРАТИВНЫЙ ПЕРСОНАЛ
                                    subdivision_id = dept_id
                                    subdivision_name = row[13]
                                    subdivision_type = row[14]
                                else:
                                    # Нет ни кафедры, ни подразделения
                                    subdivision_id = None
                                    subdivision_name = None
                                    subdivision_type = None

                                # Создать или обновить запись
                                employee = PlatonusEmployee(
                                    iin=iin,
                                    tutor_id=row[0],
                                    firstname=row[2],
                                    lastname=row[3],
                                    patronymic=row[4],
                                    position=row[5],
                                    position_type=position_type,
                                    cafedra_id=row[6],
                                    cafedra_name=row[7],
                                    faculty_id=row[8],
                                    faculty_name=row[9],
                                    email=row[10],
                                    phone=row[11],
                                    subdivision_id=subdivision_id,
                                    subdivision_name=subdivision_name,
                                    subdivision_type=subdivision_type,
                                    synced_at=datetime.utcnow(),
                                )

                                # Merge (insert or update)
                                await self.db.merge(employee)
                                synced_count += 1

                            else:
                                # Не найдено в Platonus
                                logger.warning(f"Сотрудник с IIN {iin} ({person_name}) не найден в Platonus")
                                not_found_count += 1

                            # Commit каждые batch_size записей
                            if idx % batch_size == 0:
                                try:
                                    await self.db.commit()
                                    logger.info(f"Commit батча на {idx} записях")
                                except Exception as commit_error:
                                    logger.error(f"Ошибка при commit батча: {commit_error}")
                                    await self.db.rollback()
                                    error_count += batch_size

                        except Exception as e:
                            logger.error(f"Ошибка обработки IIN {iin}: {e}")
                            error_count += 1
                            # При ошибке откатываем транзакцию
                            try:
                                await self.db.rollback()
                            except Exception:
                                pass

                # Финальный commit для оставшихся записей
                try:
                    await self.db.commit()
                    logger.info("Финальный commit выполнен")
                except Exception as e:
                    logger.error(f"Ошибка при финальном commit: {e}")
                    await self.db.rollback()

                logger.info(
                    f"Синхронизация завершена. Синхронизировано: {synced_count}, "
                    f"Не найдено: {not_found_count}, Ошибок: {error_count}"
                )

                return {
                    "status": "success",
                    "synced": synced_count,
                    "not_found": not_found_count,
                    "errors": error_count,
                    "total": len(hikcentral_employees),
                }

            finally:
                # Закрыть все ресурсы
                if platonus_conn:
                    try:
                        platonus_conn.close()
                        logger.info("Platonus connection закрыто")
                    except Exception as e:
                        logger.error(f"Ошибка при закрытии connection: {e}")

                if platonus_engine:
                    try:
                        platonus_engine.dispose()
                        logger.info("Platonus engine закрыт")
                    except Exception as e:
                        logger.error(f"Ошибка при закрытии engine: {e}")

                if tunnel:
                    try:
                        # Закрыть туннель в отдельном потоке
                        loop = asyncio.get_event_loop()
                        await loop.run_in_executor(None, tunnel.stop)
                        logger.info("SSH туннель закрыт")
                    except Exception as e:
                        logger.error(f"Ошибка при закрытии туннеля: {e}")

        except Exception as e:
            logger.error(f"Ошибка синхронизации: {e}", exc_info=True)
            await self.db.rollback()
            raise

    async def get_sync_stats(self) -> dict:
        """Получить статистику синхронизации"""

        # Всего записей
        result = await self.db.execute(select(PlatonusEmployee))
        total = len(result.scalars().all())

        # Последняя синхронизация
        query = text("SELECT MAX(synced_at) FROM platonus_employees;")
        result = await self.db.execute(query)
        last_sync = result.scalar()

        # Статистика по типам должностей
        query = text("""
            SELECT position_type, COUNT(*) as count
            FROM platonus_employees
            WHERE position_type IS NOT NULL
            GROUP BY position_type
            ORDER BY count DESC;
        """)
        result = await self.db.execute(query)
        by_position_type = {row[0]: row[1] for row in result}

        # Статистика по факультетам
        query = text("""
            SELECT faculty_name, COUNT(*) as count
            FROM platonus_employees
            WHERE faculty_name IS NOT NULL
            GROUP BY faculty_name
            ORDER BY count DESC;
        """)
        result = await self.db.execute(query)
        by_faculty = {row[0]: row[1] for row in result}

        return {
            "total_employees": total,
            "last_sync": last_sync.isoformat() if last_sync else None,
            "by_position_type": by_position_type,
            "by_faculty": by_faculty,
        }

    async def clear_cache(self) -> int:
        """Очистить весь кеш"""
        result = await self.db.execute(delete(PlatonusEmployee))
        await self.db.commit()
        return result.rowcount
