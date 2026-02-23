"""
Сервис синхронизации данных студентов из Platonus
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

from app.models import AttendanceRecord, PlatonusStudent
from app.core.config import settings

logger = logging.getLogger(__name__)


def determine_student_type(
    position1: Optional[str],
    person_group: Optional[str]
) -> Optional[str]:
    """
    Определить тип студента по данным из HikCentral

    Логика (по приоритету):
    1. student_yc: "Студент YC" в position1 ИЛИ "Обучающиеся YC" в person_group
    2. student_yu: "Студент YU" в position1 ИЛИ "Студенты YU" в person_group
    3. bachelor: "Бакалавр" в position1
    4. master: "Магистрант" в position1 ИЛИ "Магистратура" в person_group
    """

    position_lower = (position1 or "").lower()
    group_lower = (person_group or "").lower()

    # YC студенты (иностранные или с особым статусом)
    if "студент yc" in position_lower or "обучающиеся yc" in group_lower:
        return "student_yc"

    # YU студенты (основной контингент)
    if "студент yu" in position_lower or "студенты yu" in group_lower:
        return "student_yu"

    # Бакалавры
    if "бакалавр" in position_lower:
        return "bachelor"

    # Магистранты
    if "магистрант" in position_lower or "магистратура" in group_lower:
        return "master"

    return None


class StudentSyncService:
    """Сервис синхронизации данных студентов из Platonus"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def sync_students(self) -> dict:
        """
        Синхронизировать данные студентов из Platonus

        Процесс:
        1. Получить всех уникальных студентов с IIN из HikCentral
        2. Для каждого IIN получить данные из Platonus (students, student_groups, specializations)
        3. Сохранить/обновить в таблице platonus_students
        """

        logger.info("Начало синхронизации студентов из Platonus")

        try:
            # Шаг 1: Получить всех уникальных студентов с IIN
            logger.info("Получение списка студентов из HikCentral...")

            query = text("""
                SELECT DISTINCT iin, person_name, position1, person_group
                FROM attendance_records
                WHERE iin IS NOT NULL
                AND iin != ''
                AND iin ~ '^[0-9]{12}$'
                AND (
                    position1 LIKE '%Студент YU%'
                    OR position1 LIKE '%Студент YC%'
                    OR position1 LIKE '%Бакалавр%'
                    OR position1 LIKE '%Магистрант%'
                    OR person_group LIKE '%Студенты YU%'
                    OR person_group LIKE '%Обучающиеся YC%'
                    OR person_group LIKE '%Магистратура%'
                )
                ORDER BY iin;
            """)

            result = await self.db.execute(query)
            hikcentral_students = result.fetchall()

            logger.info(f"Найдено {len(hikcentral_students)} уникальных студентов в HikCentral")

            if not hikcentral_students:
                return {"status": "success", "synced": 0, "message": "Нет студентов для синхронизации"}

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
                for idx, (iin, person_name, position1, person_group) in enumerate(hikcentral_students, 1):
                    if idx % batch_size == 0:
                        logger.info(f"Обработано {idx}/{len(hikcentral_students)}...")

                    try:
                        # Определить тип студента из HikCentral
                        student_type = determine_student_type(position1, person_group)

                        # Запрос к Platonus с правильной структурой таблиц
                        # students.groupID -> groups.groupID
                        # students.specializationID -> specializations.id
                        platonus_query = text("""
                            SELECT
                                s.StudentID as student_id,
                                s.iinplt,
                                s.firstname,
                                s.lastname,
                                s.patronymic,
                                s.groupID,
                                g.name as group_name,
                                s.specializationID,
                                sp.nameru as spec_name,
                                sp.specializationCode as spec_code,
                                s.mail as email,
                                s.mobilePhone as phone
                            FROM students s
                            LEFT JOIN `groups` g ON s.groupID = g.groupID
                            LEFT JOIN specializations sp ON s.specializationID = sp.id
                            WHERE s.iinplt = :iin
                            LIMIT 1;
                        """)

                        result = platonus_conn.execute(platonus_query, {"iin": iin})
                        row = result.fetchone()

                        if row:
                            # Данные найдены в Platonus
                            # row: student_id, iinplt, firstname, lastname, patronymic,
                            #      groupID, group_name, specializationID, spec_name, spec_code,
                            #      email, phone
                            student = PlatonusStudent(
                                iin=iin,
                                student_id=row[0],
                                firstname=row[2],
                                lastname=row[3],
                                patronymic=row[4],
                                student_type=student_type,
                                student_group_id=row[5],
                                student_group_name=row[6],
                                specialization_id=row[7],
                                specialization_code=row[9],
                                specialization_name=row[8],
                                enrollment_year=None,
                                study_year=None,
                                email=row[10],
                                phone=row[11],
                                synced_at=datetime.utcnow(),
                            )

                            # Merge (insert or update)
                            await self.db.merge(student)
                            synced_count += 1

                        else:
                            # Не найдено в Platonus
                            logger.warning(f"Студент с IIN {iin} ({person_name}) не найден в Platonus")
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
                    "total": len(hikcentral_students),
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
        result = await self.db.execute(select(PlatonusStudent))
        total = len(result.scalars().all())

        # Последняя синхронизация
        query = text("SELECT MAX(synced_at) FROM platonus_students;")
        result = await self.db.execute(query)
        last_sync = result.scalar()

        # Статистика по типам студентов
        query = text("""
            SELECT student_type, COUNT(*) as count
            FROM platonus_students
            WHERE student_type IS NOT NULL
            GROUP BY student_type
            ORDER BY count DESC;
        """)
        result = await self.db.execute(query)
        by_student_type = {row[0]: row[1] for row in result}

        # Статистика по специальностям
        query = text("""
            SELECT specialization_name, COUNT(*) as count
            FROM platonus_students
            WHERE specialization_name IS NOT NULL
            GROUP BY specialization_name
            ORDER BY count DESC
            LIMIT 20;
        """)
        result = await self.db.execute(query)
        by_specialization = {row[0]: row[1] for row in result}

        # Статистика по группам
        query = text("""
            SELECT student_group_name, COUNT(*) as count
            FROM platonus_students
            WHERE student_group_name IS NOT NULL
            GROUP BY student_group_name
            ORDER BY count DESC
            LIMIT 20;
        """)
        result = await self.db.execute(query)
        by_group = {row[0]: row[1] for row in result}

        return {
            "total_students": total,
            "last_sync": last_sync.isoformat() if last_sync else None,
            "by_student_type": by_student_type,
            "by_specialization": by_specialization,
            "by_group": by_group,
        }

    async def clear_cache(self) -> int:
        """Очистить весь кеш"""
        result = await self.db.execute(delete(PlatonusStudent))
        await self.db.commit()
        return result.rowcount
