"""
Сервис для определения опозданий студентов
Учитывает расписание студенческих групп
"""

from datetime import date, time, datetime, timedelta
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
                dt_str = first_entry_datetime.replace("T", " ")
                first_entry_datetime = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")

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

    async def get_late_arrivals_period(
        self,
        date_from: date,
        date_to: date,
        specialization_id: Optional[int] = None,
        student_group_id: Optional[int] = None,
        student_type: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> Dict[str, Any]:
        """
        Получить список опоздавших студентов за период

        Args:
            date_from: Начало периода
            date_to: Конец периода
            specialization_id: Фильтр по специальности
            student_group_id: Фильтр по группе
            student_type: Фильтр по типу студента
            page: Номер страницы
            page_size: Размер страницы

        Returns:
            Словарь с результатами
        """

        logger.info(f"Получение опозданий студентов за период {date_from} - {date_to}")

        all_late_arrivals = []

        # Проходим по каждому дню периода
        current_date = date_from
        while current_date <= date_to:
            # Пропускаем выходные (суббота=6, воскресенье=7)
            if current_date.isoweekday() <= 5:
                day_result = await self.get_late_arrivals(
                    target_date=current_date,
                    specialization_id=specialization_id,
                    student_group_id=student_group_id,
                    student_type=student_type,
                    page=1,
                    page_size=10000,  # Получаем все за день
                )

                # Добавляем дату к каждой записи
                for item in day_result["items"]:
                    item["late_date"] = current_date.isoformat()
                    all_late_arrivals.append(item)

            current_date += timedelta(days=1)

        # Сортировка: сначала по дате (новые сверху), потом по минутам опоздания
        all_late_arrivals.sort(
            key=lambda x: (x["late_date"], -x["minutes_late"]),
            reverse=True
        )

        # Пагинация
        total = len(all_late_arrivals)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        paginated_items = all_late_arrivals[start_idx:end_idx]

        total_pages = (total + page_size - 1) // page_size

        # Статистика по дням
        days_count = (date_to - date_from).days + 1
        working_days = sum(1 for i in range(days_count)
                         if (date_from + timedelta(days=i)).isoweekday() <= 5)

        return {
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "working_days": working_days,
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

    async def get_absent_students(
        self,
        date_from: date,
        date_to: date,
        specialization_id: Optional[int] = None,
        student_group_id: Optional[int] = None,
        course_number: Optional[int] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> Dict[str, Any]:
        """
        Получить список студентов, которые отсутствовали (не пришли на занятия)

        Логика:
        - Для каждого дня проверяем есть ли занятия у группы студента
        - Если занятия есть, но студент не прошёл турникет - он отсутствовал

        Args:
            date_from: Начало периода
            date_to: Конец периода
            specialization_id: Фильтр по специальности
            student_group_id: Фильтр по группе
            course_number: Фильтр по курсу
            page: Номер страницы
            page_size: Размер страницы

        Returns:
            Словарь с результатами
        """

        logger.info(f"Получение отсутствующих студентов за период {date_from} - {date_to}")

        all_absent = []

        # Проходим по каждому дню периода
        current_date = date_from
        while current_date <= date_to:
            # Пропускаем выходные (суббота=6, воскресенье=7)
            if current_date.isoweekday() <= 5:
                day_absent = await self._get_absent_for_day(
                    target_date=current_date,
                    specialization_id=specialization_id,
                    student_group_id=student_group_id,
                    course_number=course_number,
                )
                all_absent.extend(day_absent)

            current_date += timedelta(days=1)

        # Сортировка: сначала по дате (новые сверху), потом по группе
        all_absent.sort(
            key=lambda x: (x["absent_date"], x["student_group"] or ""),
            reverse=True
        )

        # Пагинация
        total = len(all_absent)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        paginated_items = all_absent[start_idx:end_idx]

        total_pages = (total + page_size - 1) // page_size

        # Статистика по дням
        days_count = (date_to - date_from).days + 1
        working_days = sum(1 for i in range(days_count)
                         if (date_from + timedelta(days=i)).isoweekday() <= 5)

        return {
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "working_days": working_days,
            "total_absent": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "items": paginated_items,
        }

    async def _get_absent_for_day(
        self,
        target_date: date,
        specialization_id: Optional[int] = None,
        student_group_id: Optional[int] = None,
        course_number: Optional[int] = None,
    ) -> list:
        """
        Получить список отсутствующих студентов за один день

        Логика:
        1. Найти все группы у которых есть занятия в этот день
        2. Найти студентов этих групп
        3. Проверить кто из них НЕ прошёл турникет
        """

        weekday = target_date.isoweekday()

        # Шаг 1: Найти группы с занятиями в этот день
        groups_query = text("""
            SELECT DISTINCT student_group_id
            FROM student_schedule
            WHERE week_day = :weekday
                AND study_year = 2025
                AND study_term = 2
        """)

        result = await self.db.execute(groups_query, {"weekday": weekday})
        groups_with_lessons = [row[0] for row in result.fetchall()]

        if not groups_with_lessons:
            return []

        # Шаг 2: Найти студентов которые должны были быть, но не пришли
        # Построить запрос с динамическими фильтрами
        base_query = """
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
                ps.course_number
            FROM platonus_students ps
            WHERE ps.student_group_id = ANY(:group_ids)
                AND ps.student_group_id IS NOT NULL
                AND NOT EXISTS (
                    SELECT 1 FROM attendance_records ar
                    WHERE ar.iin = ps.iin
                        AND ar.access_date = :target_date
                        AND ar.direction = 'Вход'
                )
        """

        params = {
            "group_ids": groups_with_lessons,
            "target_date": target_date.isoformat(),
        }

        if specialization_id is not None:
            base_query += " AND ps.specialization_id = :specialization_id"
            params["specialization_id"] = specialization_id

        if student_group_id is not None:
            base_query += " AND ps.student_group_id = :student_group_id"
            params["student_group_id"] = student_group_id

        if course_number is not None:
            base_query += " AND ps.course_number = :course_number"
            params["course_number"] = course_number

        result = await self.db.execute(text(base_query), params)
        absent_students = result.fetchall()

        # Шаг 3: Для каждого студента получить информацию о первом занятии
        absent_list = []

        for student in absent_students:
            student_group_id_val = student[5]

            # Получить первое занятие группы
            first_lesson = await self._get_first_lesson_for_group(
                student_group_id=student_group_id_val,
                weekday=weekday,
            )

            absent_list.append({
                "iin": student[0],
                "firstname": student[1],
                "lastname": student[2],
                "patronymic": student[3],
                "student_type": student[4],
                "student_group": student[6],
                "student_group_id": student_group_id_val,
                "specialization": student[8],
                "specialization_id": student[7],
                "course_number": student[9],
                "absent_date": target_date.isoformat(),
                "expected_time": first_lesson["lesson_start"] if first_lesson else None,
                "first_lesson": first_lesson,
            })

        return absent_list

    async def _get_first_lesson_for_group(
        self,
        student_group_id: int,
        weekday: int,
    ) -> Optional[Dict[str, Any]]:
        """
        Получить информацию о первом занятии группы на день недели
        """

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
            return {
                "subject": first_lesson.subject_name,
                "teacher": first_lesson.teacher_name,
                "time_range": first_lesson.time_range,
                "auditory": first_lesson.full_auditory,
                "lesson_start": first_lesson.lesson_start.strftime("%H:%M:%S"),
            }

        return None
