"""
Сервис синхронизации расписания преподавателей из Platonus
Запускается раз в день
"""

from datetime import datetime, time, timedelta
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text, delete
from sshtunnel import SSHTunnelForwarder
from sqlalchemy import create_engine
import logging
import asyncio

from app.models import TeacherSchedule, PlatonusEmployee
from app.core.config import settings

logger = logging.getLogger(__name__)


def timedelta_to_time(td):
    """Конвертировать timedelta в time"""
    if isinstance(td, timedelta):
        total_seconds = int(td.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        return time(hours, minutes, seconds)
    elif isinstance(td, time):
        return td
    else:
        raise ValueError(f"Unexpected type for time: {type(td)}")


class TeacherScheduleSyncService:
    """Сервис синхронизации расписания преподавателей из Platonus"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def sync_schedules(
        self,
        study_year: Optional[int] = None,
        study_term: Optional[int] = None
    ) -> dict:
        """
        Синхронизировать расписание преподавателей из Platonus

        Args:
            study_year: Учебный год (например, 2025). Если None - берется текущий семестр
            study_term: Семестр (1 или 2). Если None - берется текущий семестр

        Процесс:
        1. Определить учебный год и семестр (если не указаны)
        2. Подключиться к Platonus через SSH туннель
        3. Получить расписание для всех преподавателей
        4. Удалить старые данные для этого года/семестра
        5. Вставить новые данные батчами
        """

        start_time = datetime.utcnow()
        logger.info("Начало синхронизации расписания преподавателей из Platonus")

        # Определить учебный год и семестр (по умолчанию текущий семестр)
        if study_year is None or study_term is None:
            current_date = datetime.now()
            current_month = current_date.month

            # 2025 год, семестр 2 (февраль 2026)
            if study_year is None:
                study_year = 2025

            if study_term is None:
                # Январь-июнь = 2 семестр, Сентябрь-Декабрь = 1 семестр
                study_term = 2 if current_month <= 6 else 1

        logger.info(f"Синхронизация расписания для {study_year} уч.года, {study_term} семестра")

        try:
            tunnel = None
            platonus_engine = None
            platonus_conn = None

            synced_lessons = 0
            synced_teachers = set()
            errors = []

            try:
                # Шаг 1: Создать SSH туннель
                logger.info("Создание SSH туннеля к Platonus...")

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

                loop = asyncio.get_event_loop()
                tunnel = await loop.run_in_executor(None, create_and_start_tunnel)
                logger.info(f"SSH туннель установлен на порту {tunnel.local_bind_port}")

                # Шаг 2: Подключиться к MySQL Platonus
                db_url = settings.platonus_db_url(tunnel.local_bind_port)
                platonus_engine = create_engine(db_url, echo=False)
                platonus_conn = platonus_engine.connect()
                logger.info("Подключено к Platonus MySQL")

                # Шаг 3: Предварительная загрузка справочника времени пар
                logger.info("Загрузка справочника времени пар (lesson_hours)...")

                # Словарь времени пар: lesson_number -> (start, finish)
                lesson_hours_query = text("SELECT number, start, finish FROM lesson_hours ORDER BY number")
                lesson_hours_result = platonus_conn.execute(lesson_hours_query)
                lesson_hours_dict = {row[0]: (row[1], row[2]) for row in lesson_hours_result}
                logger.info(f"Загружено {len(lesson_hours_dict)} записей о времени пар")

                # Шаг 4: Получить список IIN из platonus_employees (только актуальные преподаватели)
                logger.info("Получение списка актуальных преподавателей из PostgreSQL...")

                employees_query = text("SELECT DISTINCT iin FROM platonus_employees WHERE iin IS NOT NULL")
                employees_result = await self.db.execute(employees_query)
                employee_iins = [row[0] for row in employees_result.fetchall()]

                if not employee_iins:
                    logger.warning("Нет актуальных преподавателей в platonus_employees!")
                    return {
                        "status": "success",
                        "message": "Нет актуальных преподавателей для синхронизации",
                        "teachers_synced": 0,
                        "lessons_synced": 0,
                        "duration_seconds": 0,
                        "errors": []
                    }

                logger.info(f"Найдено {len(employee_iins)} актуальных преподавателей")

                # Шаг 5: Получить расписание ТОЛЬКО для актуальных преподавателей
                logger.info(f"Получение расписания из Platonus (year={study_year}, term={study_term})...")

                # Создать placeholder для IN clause
                placeholders = ','.join([f':iin{i}' for i in range(len(employee_iins))])

                # SQL запрос для получения расписания только для актуальных преподавателей
                schedule_query = text(f"""
                    SELECT
                        t2.iinplt as iin,
                        t.week_day,
                        t.number as lesson_number,
                        su.SubjectNameRU as subject_name,
                        sg.groupname as group_name,
                        t.auditoryID,
                        t.buildingID,
                        t.lessonID,
                        sg.studyGroupID,
                        sg.year,
                        sg.term
                    FROM timetable t
                    INNER JOIN studygroups sg ON sg.studyGroupID = t.studyGroupID
                    INNER JOIN subjects su ON su.SubjectID = sg.subjectid
                    INNER JOIN tutors t2 ON t2.TutorID = sg.tutorid
                    WHERE sg.year = :year
                        AND sg.term = :term
                        AND t2.iinplt IS NOT NULL
                        AND t2.iinplt != ''
                        AND t2.iinplt IN ({placeholders})
                    ORDER BY t2.iinplt, t.week_day, t.number
                """)

                # Создать параметры для запроса
                query_params = {"year": study_year, "term": study_term}
                for i, iin in enumerate(employee_iins):
                    query_params[f'iin{i}'] = iin

                result = platonus_conn.execute(schedule_query, query_params)
                schedule_rows = result.fetchall()

                logger.info(f"Получено {len(schedule_rows)} записей расписания из Platonus")

                if not schedule_rows:
                    logger.warning("Нет данных расписания в Platonus для актуальных преподавателей!")
                    return {
                        "status": "success",
                        "message": "Нет данных для синхронизации",
                        "teachers_synced": 0,
                        "lessons_synced": 0,
                        "duration_seconds": 0,
                        "errors": []
                    }

                # Шаг 6: Удалить старые данные для этого года/семестра
                logger.info(f"Удаление старых данных расписания для {study_year}-{study_term}...")
                delete_query = delete(TeacherSchedule).where(
                    TeacherSchedule.study_year == study_year,
                    TeacherSchedule.study_term == study_term
                )
                await self.db.execute(delete_query)
                await self.db.commit()
                logger.info("Старые данные удалены")

                # Шаг 7: Вставить новые данные батчами
                logger.info("Вставка новых данных расписания...")

                batch_size = 50
                batch = []
                sync_timestamp = datetime.utcnow()

                for idx, row in enumerate(schedule_rows, 1):
                    try:
                        iin = row[0]

                        # Пропустить записи с пустым или NULL ИИН
                        if not iin or iin.strip() == '':
                            logger.warning(f"Пропуск записи {idx}: пустой ИИН")
                            errors.append(f"Строка {idx}: пустой ИИН")
                            continue

                        week_day = row[1]
                        lesson_number = row[2]
                        subject_name = row[3]
                        group_name = row[4]
                        auditory_id = row[5]
                        building_id = row[6]
                        lesson_id = row[7]
                        study_group_id = row[8]

                        # Получить время пары из словаря
                        lesson_times = lesson_hours_dict.get(lesson_number)
                        if not lesson_times:
                            logger.warning(f"Не найдено время для пары {lesson_number}, пропускаем")
                            errors.append(f"Не найдено время для пары {lesson_number}")
                            continue

                        lesson_start, lesson_finish = lesson_times

                        # Конвертировать timedelta в time для PostgreSQL
                        lesson_start = timedelta_to_time(lesson_start)
                        lesson_finish = timedelta_to_time(lesson_finish)

                        # Использовать ID как строки (т.к. они уже являются номерами в Platonus)
                        auditory_number = str(auditory_id) if auditory_id else None
                        building_number = str(building_id) if building_id else None

                        # Создать объект расписания
                        schedule_obj = TeacherSchedule(
                            iin=iin,
                            week_day=week_day,
                            lesson_number=lesson_number,
                            lesson_start=lesson_start,
                            lesson_finish=lesson_finish,
                            subject_name=subject_name,
                            group_name=group_name,
                            auditory_number=auditory_number,
                            building_number=building_number,
                            study_year=study_year,
                            study_term=study_term,
                            platonus_lesson_id=lesson_id,
                            platonus_study_group_id=study_group_id,
                            synced_at=sync_timestamp,
                        )

                        batch.append(schedule_obj)
                        synced_teachers.add(iin)

                        # Commit батчами
                        if len(batch) >= batch_size:
                            self.db.add_all(batch)
                            await self.db.commit()
                            synced_lessons += len(batch)
                            logger.info(f"Обработано {idx}/{len(schedule_rows)}, синхронизировано {synced_lessons} занятий...")
                            batch = []

                    except Exception as e:
                        logger.error(f"Ошибка обработки строки {idx}: {e}")
                        errors.append(f"Строка {idx}: {str(e)}")
                        continue

                # Commit оставшихся записей
                if batch:
                    self.db.add_all(batch)
                    await self.db.commit()
                    synced_lessons += len(batch)
                    logger.info(f"Финальный батч: синхронизировано {len(batch)} занятий")

                end_time = datetime.utcnow()
                duration = (end_time - start_time).total_seconds()

                logger.info(
                    f"Синхронизация завершена. Преподавателей: {len(synced_teachers)}, "
                    f"Занятий: {synced_lessons}, Длительность: {duration:.2f} сек"
                )

                return {
                    "status": "success",
                    "message": f"Успешно синхронизировано расписание для {study_year}-{study_term}",
                    "teachers_synced": len(synced_teachers),
                    "lessons_synced": synced_lessons,
                    "duration_seconds": duration,
                    "errors": errors
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
                        loop = asyncio.get_event_loop()
                        await loop.run_in_executor(None, tunnel.stop)
                        logger.info("SSH туннель закрыт")
                    except Exception as e:
                        logger.error(f"Ошибка при закрытии туннеля: {e}")

        except Exception as e:
            logger.error(f"Критическая ошибка синхронизации: {e}", exc_info=True)
            await self.db.rollback()
            raise

    async def get_sync_stats(self, study_year: int = 2025, study_term: int = 2) -> dict:
        """
        Получить статистику синхронизации расписания

        Args:
            study_year: Учебный год
            study_term: Семестр

        Returns:
            Словарь со статистикой
        """

        # Всего преподавателей
        query = text("""
            SELECT COUNT(DISTINCT iin)
            FROM teacher_schedule
            WHERE study_year = :year AND study_term = :term
        """)
        result = await self.db.execute(query, {"year": study_year, "term": study_term})
        total_teachers = result.scalar() or 0

        # Всего занятий
        query = text("""
            SELECT COUNT(*)
            FROM teacher_schedule
            WHERE study_year = :year AND study_term = :term
        """)
        result = await self.db.execute(query, {"year": study_year, "term": study_term})
        total_lessons = result.scalar() or 0

        # Уникальных предметов
        query = text("""
            SELECT COUNT(DISTINCT subject_name)
            FROM teacher_schedule
            WHERE study_year = :year AND study_term = :term
        """)
        result = await self.db.execute(query, {"year": study_year, "term": study_term})
        unique_subjects = result.scalar() or 0

        # Уникальных групп
        query = text("""
            SELECT COUNT(DISTINCT group_name)
            FROM teacher_schedule
            WHERE study_year = :year AND study_term = :term
        """)
        result = await self.db.execute(query, {"year": study_year, "term": study_term})
        unique_groups = result.scalar() or 0

        # Последняя синхронизация
        query = text("""
            SELECT MAX(synced_at)
            FROM teacher_schedule
            WHERE study_year = :year AND study_term = :term
        """)
        result = await self.db.execute(query, {"year": study_year, "term": study_term})
        last_sync = result.scalar()

        return {
            "total_teachers": total_teachers,
            "total_lessons": total_lessons,
            "unique_subjects": unique_subjects,
            "unique_groups": unique_groups,
            "study_year": study_year,
            "study_term": study_term,
            "last_sync": last_sync.isoformat() if last_sync else None,
        }

    async def clear_schedules(self, study_year: Optional[int] = None, study_term: Optional[int] = None) -> int:
        """
        Очистить расписание

        Args:
            study_year: Учебный год (если None - все годы)
            study_term: Семестр (если None - все семестры)

        Returns:
            Количество удаленных записей
        """

        if study_year and study_term:
            result = await self.db.execute(
                delete(TeacherSchedule).where(
                    TeacherSchedule.study_year == study_year,
                    TeacherSchedule.study_term == study_term
                )
            )
        elif study_year:
            result = await self.db.execute(
                delete(TeacherSchedule).where(TeacherSchedule.study_year == study_year)
            )
        else:
            result = await self.db.execute(delete(TeacherSchedule))

        await self.db.commit()
        return result.rowcount
