"""
Сервис синхронизации расписания студенческих групп из Platonus
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

from app.models import StudentSchedule, PlatonusStudent
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


class StudentScheduleSyncService:
    """Сервис синхронизации расписания студенческих групп из Platonus"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def sync_schedules(
        self,
        study_year: Optional[int] = None,
        study_term: Optional[int] = None
    ) -> dict:
        """
        Синхронизировать расписание студенческих групп из Platonus

        Структура Platonus:
        - groups (группы студентов) -> students -> studentstudygroup -> studygroups -> timetable
        - timetable.number -> lesson_hours.number (время пары)
        """

        start_time = datetime.utcnow()
        logger.info("Начало синхронизации расписания студентов из Platonus")

        # Определить учебный год и семестр
        if study_year is None or study_term is None:
            current_date = datetime.now()
            current_month = current_date.month

            if study_year is None:
                study_year = 2025

            if study_term is None:
                study_term = 2 if current_month <= 6 else 1

        logger.info(f"Синхронизация расписания для {study_year} уч.года, {study_term} семестра")

        try:
            tunnel = None
            platonus_engine = None
            platonus_conn = None

            synced_lessons = 0
            synced_groups = set()
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

                # Шаг 3: Получить расписание всех групп
                logger.info(f"Получение расписания из Platonus (year={study_year}, term={study_term})...")

                schedule_query = text("""
                    SELECT DISTINCT
                        g.groupID as student_group_id,
                        g.name as student_group_name,
                        t.week_day,
                        lh.displayNumber as lesson_number,
                        lh.start as lesson_start,
                        lh.`finish` as lesson_finish,
                        sub.SubjectNameRU as subject_name,
                        CONCAT(tut.lastname, ' ', tut.firstname) as teacher_name,
                        tut.iinplt as teacher_iin,
                        t.auditoryID,
                        t.buildingID,
                        t.lessonID
                    FROM `groups` g
                    JOIN students s ON s.groupID = g.groupID
                    JOIN studentstudygroup ssg ON ssg.studentID = s.StudentID
                    JOIN studygroups sg ON sg.StudyGroupID = ssg.studyGroupID
                    JOIN timetable t ON t.studyGroupID = sg.StudyGroupID
                    JOIN lesson_hours lh ON lh.number = t.number
                    JOIN subjects sub ON sub.SubjectID = sg.subjectid
                    LEFT JOIN tutors tut ON tut.TutorID = t.tutorID
                    WHERE sg.year = :year
                      AND sg.term = :term
                    ORDER BY g.groupID, t.week_day, lh.displayNumber
                """)

                result = platonus_conn.execute(schedule_query, {"year": study_year, "term": study_term})
                schedule_rows = result.fetchall()

                logger.info(f"Получено {len(schedule_rows)} записей расписания из Platonus")

                if not schedule_rows:
                    logger.warning("Нет данных расписания в Platonus!")
                    return {
                        "status": "success",
                        "message": "Нет данных для синхронизации",
                        "groups_synced": 0,
                        "lessons_synced": 0,
                        "duration_seconds": 0,
                        "errors": []
                    }

                # Шаг 4: Удалить старые данные для этого года/семестра
                logger.info(f"Удаление старых данных расписания для {study_year}-{study_term}...")
                delete_query = delete(StudentSchedule).where(
                    StudentSchedule.study_year == study_year,
                    StudentSchedule.study_term == study_term
                )
                await self.db.execute(delete_query)
                await self.db.commit()
                logger.info("Старые данные удалены")

                # Шаг 5: Вставить новые данные батчами
                logger.info("Вставка новых данных расписания...")

                batch_size = 100
                batch = []
                sync_timestamp = datetime.utcnow()
                seen_keys = set()  # Для дедупликации

                for idx, row in enumerate(schedule_rows, 1):
                    try:
                        student_group_id = row[0]
                        student_group_name = row[1]
                        week_day = row[2]
                        lesson_number = row[3]
                        lesson_start_td = row[4]
                        lesson_finish_td = row[5]
                        subject_name = row[6]
                        teacher_name = row[7]
                        teacher_iin = row[8]
                        auditory_id = row[9]
                        building_id = row[10]
                        lesson_id = row[11]

                        # Дедупликация по ключу
                        key = (student_group_id, week_day, lesson_number, subject_name)
                        if key in seen_keys:
                            continue
                        seen_keys.add(key)

                        # Конвертировать timedelta в time
                        lesson_start = timedelta_to_time(lesson_start_td)
                        lesson_finish = timedelta_to_time(lesson_finish_td)

                        auditory_number = str(auditory_id) if auditory_id else None
                        building_number = str(building_id) if building_id else None

                        schedule_obj = StudentSchedule(
                            student_group_id=student_group_id,
                            student_group_name=student_group_name,
                            week_day=week_day,
                            lesson_number=lesson_number,
                            lesson_start=lesson_start,
                            lesson_finish=lesson_finish,
                            subject_name=subject_name,
                            teacher_name=teacher_name,
                            teacher_iin=teacher_iin,
                            auditory_number=auditory_number,
                            building_number=building_number,
                            study_year=study_year,
                            study_term=study_term,
                            platonus_lesson_id=lesson_id,
                            synced_at=sync_timestamp,
                        )

                        batch.append(schedule_obj)
                        synced_groups.add(student_group_id)

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
                    f"Синхронизация завершена. Групп: {len(synced_groups)}, "
                    f"Занятий: {synced_lessons}, Длительность: {duration:.2f} сек"
                )

                return {
                    "status": "success",
                    "message": f"Успешно синхронизировано расписание для {study_year}-{study_term}",
                    "groups_synced": len(synced_groups),
                    "lessons_synced": synced_lessons,
                    "duration_seconds": duration,
                    "errors": errors
                }

            finally:
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

        # Всего групп
        query = text("""
            SELECT COUNT(DISTINCT student_group_id)
            FROM student_schedule
            WHERE study_year = :year AND study_term = :term
        """)
        result = await self.db.execute(query, {"year": study_year, "term": study_term})
        total_groups = result.scalar() or 0

        # Всего занятий
        query = text("""
            SELECT COUNT(*)
            FROM student_schedule
            WHERE study_year = :year AND study_term = :term
        """)
        result = await self.db.execute(query, {"year": study_year, "term": study_term})
        total_lessons = result.scalar() or 0

        # Уникальных предметов
        query = text("""
            SELECT COUNT(DISTINCT subject_name)
            FROM student_schedule
            WHERE study_year = :year AND study_term = :term
        """)
        result = await self.db.execute(query, {"year": study_year, "term": study_term})
        unique_subjects = result.scalar() or 0

        # Последняя синхронизация
        query = text("""
            SELECT MAX(synced_at)
            FROM student_schedule
            WHERE study_year = :year AND study_term = :term
        """)
        result = await self.db.execute(query, {"year": study_year, "term": study_term})
        last_sync = result.scalar()

        return {
            "total_groups": total_groups,
            "total_lessons": total_lessons,
            "unique_subjects": unique_subjects,
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
                delete(StudentSchedule).where(
                    StudentSchedule.study_year == study_year,
                    StudentSchedule.study_term == study_term
                )
            )
        elif study_year:
            result = await self.db.execute(
                delete(StudentSchedule).where(StudentSchedule.study_year == study_year)
            )
        else:
            result = await self.db.execute(delete(StudentSchedule))

        await self.db.commit()
        return result.rowcount
