"""
Сервис для определения опозданий студентов
Учитывает расписание студенческих групп
"""

from datetime import date, time, datetime
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text, and_
import logging

from app.models import PlatonusStudent, AttendanceRecord, StudentSchedule

logger = logging.getLogger(__name__)


class StudentLateService:
    """Сервис для определения опозданий студентов"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_late_arrivals(
        self,
        target_date: date,
        specialization_id: Optional[int] = None,
        student_group_id: Optional[int] = None,
        student_type: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> Dict[str, Any]:
        """
        Получить список опоздавших студентов за день

        Логика:
        - Сравнить время первого входа с началом первого занятия группы
        - Если нет расписания - не считается опозданием

        Args:
            target_date: Дата для проверки
            specialization_id: Фильтр по специальности
            student_group_id: Фильтр по группе
            student_type: Фильтр по типу студента
            page: Номер страницы
            page_size: Размер страницы

        Returns:
            Словарь с результатами
        """

        logger.info(f"Получение опозданий студентов за {target_date}")

        # Определить день недели (1=Monday, 7=Sunday)
        weekday = target_date.isoweekday()

        # Построить запрос с динамическими фильтрами
        base_query = """
            WITH first_entries AS (
                SELECT DISTINCT ON (ar.iin)
                    ar.iin,
                    ar.access_time,
                    ar.access_datetime
                FROM attendance_records ar
                WHERE ar.access_date = :target_date
                    AND ar.direction = 'Вход'
                    AND ar.iin IS NOT NULL
                    AND ar.iin != ''
                    AND (
                        ar.position1 LIKE '%Студент YU%'
                        OR ar.position1 LIKE '%Студент YC%'
                        OR ar.position1 LIKE '%Бакалавр%'
                        OR ar.position1 LIKE '%Магистрант%'
                        OR ar.person_group LIKE '%Студенты YU%'
                        OR ar.person_group LIKE '%Обучающиеся YC%'
                        OR ar.person_group LIKE '%Магистратура%'
                    )
                ORDER BY ar.iin, ar.access_datetime
            )
            SELECT
                ps.iin,
                ps.firstname,
                ps.lastname,
                ps.patronymic,
                ps.student_type,
                ps.student_group_id,
                ps.student_group_name,
                ps.specialization_id,
                ps.specialization_name,
                fe.access_time,
                fe.access_datetime
            FROM platonus_students ps
            INNER JOIN first_entries fe ON ps.iin = fe.iin
            WHERE 1=1
        """

        # Добавить фильтры динамически
        params = {"target_date": target_date.isoformat()}

        if specialization_id is not None:
            base_query += " AND ps.specialization_id = :specialization_id"
            params["specialization_id"] = specialization_id

        if student_group_id is not None:
            base_query += " AND ps.student_group_id = :student_group_id"
            params["student_group_id"] = student_group_id

        if student_type is not None:
            base_query += " AND ps.student_type = :student_type"
            params["student_type"] = student_type

        query = text(base_query)

        result = await self.db.execute(query, params)
        students = result.fetchall()

        logger.info(f"Найдено {len(students)} студентов с входом за {target_date}")

        # Обработать каждого студента
        late_arrivals = []

        for student in students:
            # Конвертировать access_time из строки в time, если нужно
            first_entry_time = student[9]
            if isinstance(first_entry_time, str):
                hour, minute, second = first_entry_time.split(":")
                first_entry_time = time(int(hour), int(minute), int(second))

            # Конвертировать access_datetime из строки в datetime, если нужно
            first_entry_datetime = student[10]
            if isinstance(first_entry_datetime, str):
                first_entry_datetime = datetime.fromisoformat(first_entry_datetime)

            late_info = await self._check_student_late(
                iin=student[0],
                firstname=student[1],
                lastname=student[2],
                patronymic=student[3],
                student_type=student[4],
                student_group_id=student[5],
                student_group_name=student[6],
                specialization_id=student[7],
                specialization_name=student[8],
                first_entry_time=first_entry_time,
                first_entry_datetime=first_entry_datetime,
                weekday=weekday,
            )

            if late_info:
                late_arrivals.append(late_info)

        # Сортировка по времени опоздания (больше -> раньше)
        late_arrivals.sort(key=lambda x: x["minutes_late"], reverse=True)

        # Пагинация
        total = len(late_arrivals)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        paginated_items = late_arrivals[start_idx:end_idx]

        total_pages = (total + page_size - 1) // page_size

        return {
            "date": target_date.isoformat(),
            "total_late": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "items": paginated_items,
        }

    async def _check_student_late(
        self,
        iin: str,
        firstname: str,
        lastname: str,
        patronymic: Optional[str],
        student_type: Optional[str],
        student_group_id: Optional[int],
        student_group_name: Optional[str],
        specialization_id: Optional[int],
        specialization_name: Optional[str],
        first_entry_time: time,
        first_entry_datetime: datetime,
        weekday: int,
    ) -> Optional[Dict[str, Any]]:
        """
        Проверить опоздал ли конкретный студент на первое занятие

        Логика:
        1. Найти первое занятие группы в этот день недели
        2. Если занятия нет - не считается опозданием
        3. Если занятие есть - сравнить время прихода с началом занятия
        """

        # Нет группы - не можем определить опоздание
        if not student_group_id:
            return None

        # Получить первое занятие группы на этот день недели
        query = select(StudentSchedule).where(
            and_(
                StudentSchedule.student_group_id == student_group_id,
                StudentSchedule.week_day == weekday,
                StudentSchedule.study_year == 2025,  # TODO: сделать динамическим
                StudentSchedule.study_term == 2,
            )
        ).order_by(StudentSchedule.lesson_start)

        result = await self.db.execute(query)
        first_lesson = result.scalars().first()

        # Нет занятия в этот день - не опоздание
        if not first_lesson:
            return None

        # Сравнить время прихода с началом первого занятия
        lesson_start = first_lesson.lesson_start

        # Если пришел ПОСЛЕ начала занятия - опоздал
        if first_entry_time > lesson_start:
            # Вычислить опоздание в минутах
            entry_seconds = first_entry_time.hour * 3600 + first_entry_time.minute * 60 + first_entry_time.second
            lesson_seconds = lesson_start.hour * 3600 + lesson_start.minute * 60 + lesson_start.second
            late_seconds = entry_seconds - lesson_seconds
            minutes_late = late_seconds // 60

            return {
                "iin": iin,
                "firstname": firstname,
                "lastname": lastname,
                "patronymic": patronymic,
                "student_type": student_type,
                "student_group": student_group_name,
                "student_group_id": student_group_id,
                "specialization": specialization_name,
                "specialization_id": specialization_id,
                "expected_time": lesson_start.strftime("%H:%M:%S"),
                "first_entry_time": first_entry_time.strftime("%H:%M:%S"),
                "first_entry_datetime": first_entry_datetime.isoformat(),
                "minutes_late": int(minutes_late),
                "first_lesson": {
                    "subject": first_lesson.subject_name,
                    "teacher": first_lesson.teacher_name,
                    "time_range": first_lesson.time_range,
                    "auditory": first_lesson.full_auditory,
                } if first_lesson else None,
            }

        # Пришел вовремя
        return None

    async def get_first_lesson_time(
        self,
        student_group_id: int,
        target_date: date,
    ) -> Optional[time]:
        """
        Получить время первого занятия группы на дату

        Args:
            student_group_id: ID группы
            target_date: Дата

        Returns:
            Время начала первого занятия или None
        """

        weekday = target_date.isoweekday()

        query = select(StudentSchedule).where(
            and_(
                StudentSchedule.student_group_id == student_group_id,
                StudentSchedule.week_day == weekday,
                StudentSchedule.study_year == 2025,
                StudentSchedule.study_term == 2,
            )
        ).order_by(StudentSchedule.lesson_start)

        result = await self.db.execute(query)
        first_lesson = result.scalars().first()

        if first_lesson:
            return first_lesson.lesson_start

        return None
