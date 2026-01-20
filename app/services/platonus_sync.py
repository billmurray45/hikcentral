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

from app.models import AttendanceRecord, PlatonusEmployee
from app.core.config import settings

logger = logging.getLogger(__name__)


def determine_position_type(position_name: Optional[str]) -> Optional[str]:
    """Определить тип должности"""
    if not position_name:
        return None

    position_lower = position_name.lower()

    # Преподаватели
    if any(word in position_lower for word in ["профессор", "доцент", "преподаватель"]):
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
                AND person_type != 'student'
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

            with SSHTunnelForwarder(
                (settings.PLATONUS_SSH_HOST, settings.PLATONUS_SSH_PORT),
                ssh_username=settings.PLATONUS_SSH_USER,
                ssh_password=settings.PLATONUS_SSH_PASSWORD,
                remote_bind_address=(settings.PLATONUS_DB_HOST, settings.PLATONUS_DB_PORT),
                local_bind_address=("127.0.0.1", 0),
            ) as tunnel:

                # Подключение к MySQL Platonus
                db_url = settings.platonus_db_url(tunnel.local_bind_port)
                platonus_engine = create_engine(db_url, echo=False)

                with platonus_engine.connect() as platonus_conn:
                    logger.info("Подключено к Platonus")

                    # Для каждого IIN получить данные из Platonus
                    for idx, (iin, person_name) in enumerate(hikcentral_employees, 1):
                        if idx % 50 == 0:
                            logger.info(f"Обработано {idx}/{len(hikcentral_employees)}...")

                        try:
                            # Запрос к Platonus
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
                                    t.mobilePhone
                                FROM tutors t
                                LEFT JOIN tutor_positions tp ON t.job_title_int = tp.id
                                LEFT JOIN cafedras c ON t.CafedraID = c.cafedraID
                                LEFT JOIN faculties f ON c.FacultyID = f.FacultyID
                                WHERE t.iinplt = :iin
                                LIMIT 1;
                            """)

                            result = platonus_conn.execute(platonus_query, {"iin": iin})
                            row = result.fetchone()

                            if row:
                                # Данные найдены в Platonus
                                position_type = determine_position_type(row[5])

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
                                    synced_at=datetime.utcnow(),
                                )

                                # Merge (insert or update)
                                await self.db.merge(employee)
                                synced_count += 1

                            else:
                                # Не найдено в Platonus
                                logger.warning(f"Сотрудник с IIN {iin} ({person_name}) не найден в Platonus")
                                not_found_count += 1

                        except Exception as e:
                            logger.error(f"Ошибка обработки IIN {iin}: {e}")
                            error_count += 1

            # Commit всех изменений
            await self.db.commit()

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
