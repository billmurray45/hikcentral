"""
Сервис для определения опозданий сотрудников
Учитывает расписание преподавателей и правила рабочего времени
"""

from datetime import date, time, datetime
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text, and_, func
import logging

from app.models import PlatonusEmployee, AttendanceRecord, TeacherSchedule, WorkScheduleRule

logger = logging.getLogger(__name__)


class LateArrivalService:
    """Сервис для определения опозданий сотрудников"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_late_arrivals(
        self,
        target_date: date,
        faculty_id: Optional[int] = None,
        subdivision_id: Optional[int] = None,
        position_type: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> Dict[str, Any]:
        """
        Получить список опоздавших сотрудников за день

        Логика:
        - Для преподавателей: опоздание на первый урок из teacher_schedule
        - Для остальных: опоздание по work_schedule_rules
        - Если нет расписания и нет правила - не считается опозданием

        Args:
            target_date: Дата для проверки
            faculty_id: Фильтр по факультету
            subdivision_id: Фильтр по подразделению
            position_type: Фильтр по типу должности
            page: Номер страницы
            page_size: Размер страницы

        Returns:
            Словарь с результатами
        """

        logger.info(f"Получение опозданий за {target_date}")

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
                ORDER BY ar.iin, ar.access_datetime
            )
            SELECT
                pe.iin,
                pe.firstname,
                pe.lastname,
                pe.patronymic,
                pe.position,
                pe.position_type,
                pe.cafedra_id,
                pe.cafedra_name,
                pe.faculty_id,
                pe.faculty_name,
                pe.subdivision_id,
                pe.subdivision_name,
                fe.access_time,
                fe.access_datetime
            FROM platonus_employees pe
            INNER JOIN first_entries fe ON pe.iin = fe.iin
            WHERE 1=1
        """

        # Добавить фильтры динамически
        # AsyncPG requires date as string when using text()
        params = {"target_date": target_date.isoformat()}

        if faculty_id is not None:
            base_query += " AND pe.faculty_id = :faculty_id"
            params["faculty_id"] = faculty_id

        if subdivision_id is not None:
            base_query += " AND pe.subdivision_id = :subdivision_id"
            params["subdivision_id"] = subdivision_id

        if position_type is not None:
            base_query += " AND pe.position_type = :position_type"
            params["position_type"] = position_type

        query = text(base_query)

        result = await self.db.execute(query, params)
        employees = result.fetchall()

        logger.info(f"Найдено {len(employees)} сотрудников с входом за {target_date}")

        # Обработать каждого сотрудника
        late_arrivals = []

        for emp in employees:
            # Конвертировать access_time из строки в time, если нужно
            first_entry_time = emp[12]
            if isinstance(first_entry_time, str):
                # Parse time string (format: "HH:MM:SS")
                hour, minute, second = first_entry_time.split(":")
                first_entry_time = time(int(hour), int(minute), int(second))

            # Конвертировать access_datetime из строки в datetime, если нужно
            first_entry_datetime = emp[13]
            if isinstance(first_entry_datetime, str):
                # Parse datetime string (format: "YYYY-MM-DD HH:MM:SS")
                first_entry_datetime = datetime.fromisoformat(first_entry_datetime)

            late_info = await self._check_employee_late(
                iin=emp[0],
                firstname=emp[1],
                lastname=emp[2],
                patronymic=emp[3],
                position=emp[4],
                emp_position_type=emp[5],
                cafedra_id=emp[6],
                cafedra_name=emp[7],
                faculty_id=emp[8],
                faculty_name=emp[9],
                subdivision_id=emp[10],
                subdivision_name=emp[11],
                first_entry_time=first_entry_time,
                first_entry_datetime=first_entry_datetime,
                target_date=target_date,
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

    async def _check_employee_late(
        self,
        iin: str,
        firstname: str,
        lastname: str,
        patronymic: Optional[str],
        position: Optional[str],
        emp_position_type: Optional[str],
        cafedra_id: Optional[int],
        cafedra_name: Optional[str],
        faculty_id: Optional[int],
        faculty_name: Optional[str],
        subdivision_id: Optional[int],
        subdivision_name: Optional[str],
        first_entry_time: time,
        first_entry_datetime: datetime,
        target_date: date,
        weekday: int,
    ) -> Optional[Dict[str, Any]]:
        """
        Проверить опоздал ли конкретный сотрудник

        Returns:
            Словарь с информацией об опоздании или None если не опоздал
        """

        # Преподаватели - проверяем по расписанию
        if emp_position_type == "Преподаватель":
            return await self._check_teacher_late(
                iin=iin,
                firstname=firstname,
                lastname=lastname,
                patronymic=patronymic,
                position=position,
                emp_position_type=emp_position_type,
                cafedra_id=cafedra_id,
                cafedra_name=cafedra_name,
                faculty_id=faculty_id,
                faculty_name=faculty_name,
                first_entry_time=first_entry_time,
                first_entry_datetime=first_entry_datetime,
                weekday=weekday,
            )
        else:
            # Остальные - проверяем по work_schedule_rules
            return await self._check_admin_late(
                iin=iin,
                firstname=firstname,
                lastname=lastname,
                patronymic=patronymic,
                position=position,
                emp_position_type=emp_position_type,
                subdivision_id=subdivision_id,
                subdivision_name=subdivision_name,
                faculty_id=faculty_id,
                first_entry_time=first_entry_time,
                first_entry_datetime=first_entry_datetime,
            )

    async def _check_teacher_late(
        self,
        iin: str,
        firstname: str,
        lastname: str,
        patronymic: Optional[str],
        position: Optional[str],
        emp_position_type: str,
        cafedra_id: Optional[int],
        cafedra_name: Optional[str],
        faculty_id: Optional[int],
        faculty_name: Optional[str],
        first_entry_time: time,
        first_entry_datetime: datetime,
        weekday: int,
    ) -> Optional[Dict[str, Any]]:
        """
        Проверить опоздание преподавателя на первый урок

        Логика:
        1. Найти первый урок в этот день недели
        2. Если урока нет - не считается опозданием
        3. Если урок есть - сравнить время прихода с началом урока
        """

        # Получить первый урок на этот день недели (текущий год/семестр)
        query = select(TeacherSchedule).where(
            and_(
                TeacherSchedule.iin == iin,
                TeacherSchedule.week_day == weekday,
                TeacherSchedule.study_year == 2025,  # TODO: сделать динамическим
                TeacherSchedule.study_term == 2,
            )
        ).order_by(TeacherSchedule.lesson_start)

        result = await self.db.execute(query)
        first_lesson = result.scalars().first()

        # Нет урока в этот день - не опоздание
        if not first_lesson:
            return None

        # Сравнить время прихода с началом первого урока
        lesson_start = first_lesson.lesson_start

        # Если пришел ПОСЛЕ начала урока - опоздал
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
                "position": position,
                "position_type": emp_position_type,
                "cafedra": cafedra_name,
                "faculty": faculty_name,
                "faculty_id": faculty_id,
                "subdivision": None,
                "subdivision_id": None,
                "late_type": "lesson",
                "expected_time": lesson_start.strftime("%H:%M:%S"),
                "first_entry_time": first_entry_time.strftime("%H:%M:%S"),
                "first_entry_datetime": first_entry_datetime.isoformat(),
                "minutes_late": int(minutes_late),
                "first_lesson": {
                    "subject": first_lesson.subject_name,
                    "group": first_lesson.group_name,
                    "time_range": first_lesson.time_range,
                    "auditory": first_lesson.full_auditory,
                } if first_lesson else None,
                "work_schedule_rule": None,
            }

        # Пришел вовремя
        return None

    async def _check_admin_late(
        self,
        iin: str,
        firstname: str,
        lastname: str,
        patronymic: Optional[str],
        position: Optional[str],
        emp_position_type: Optional[str],
        subdivision_id: Optional[int],
        subdivision_name: Optional[str],
        faculty_id: Optional[int],
        first_entry_time: time,
        first_entry_datetime: datetime,
    ) -> Optional[Dict[str, Any]]:
        """
        Проверить опоздание административного персонала по work_schedule_rules

        Логика:
        1. Найти применимое правило (по position_type, position, subdivision, faculty)
        2. Если правила нет - не считается опозданием
        3. Если правило есть - сравнить время прихода с start_time
        """

        # Найти применимое правило по каскадной логике (от специфичного к общему)
        # 1. Сначала ищем по конкретной должности
        query = select(WorkScheduleRule).where(
            and_(
                WorkScheduleRule.is_active == True,
                WorkScheduleRule.position == position,
            )
        ).order_by(WorkScheduleRule.priority.desc())
        result = await self.db.execute(query)
        rule = result.scalars().first()

        # 2. Если не нашли, ищем по типу должности
        if not rule:
            query = select(WorkScheduleRule).where(
                and_(
                    WorkScheduleRule.is_active == True,
                    WorkScheduleRule.position_type == emp_position_type,
                    WorkScheduleRule.position.is_(None),
                )
            ).order_by(WorkScheduleRule.priority.desc())
            result = await self.db.execute(query)
            rule = result.scalars().first()

        # 3. Если не нашли, ищем по подразделению
        if not rule and subdivision_id:
            query = select(WorkScheduleRule).where(
                and_(
                    WorkScheduleRule.is_active == True,
                    WorkScheduleRule.subdivision_id == subdivision_id,
                    WorkScheduleRule.position.is_(None),
                    WorkScheduleRule.position_type.is_(None),
                )
            ).order_by(WorkScheduleRule.priority.desc())
            result = await self.db.execute(query)
            rule = result.scalars().first()

        # 4. Если не нашли, ищем по факультету
        if not rule and faculty_id:
            query = select(WorkScheduleRule).where(
                and_(
                    WorkScheduleRule.is_active == True,
                    WorkScheduleRule.faculty_id == faculty_id,
                    WorkScheduleRule.position.is_(None),
                    WorkScheduleRule.position_type.is_(None),
                    WorkScheduleRule.subdivision_id.is_(None),
                )
            ).order_by(WorkScheduleRule.priority.desc())
            result = await self.db.execute(query)
            rule = result.scalars().first()

        # 5. Если не нашли, ищем общее правило (все критерии NULL)
        if not rule:
            query = select(WorkScheduleRule).where(
                and_(
                    WorkScheduleRule.is_active == True,
                    WorkScheduleRule.position.is_(None),
                    WorkScheduleRule.position_type.is_(None),
                    WorkScheduleRule.subdivision_id.is_(None),
                    WorkScheduleRule.faculty_id.is_(None),
                )
            ).order_by(WorkScheduleRule.priority.desc())
            result = await self.db.execute(query)
            rule = result.scalars().first()

        # Нет правила - не опоздание
        if not rule:
            return None

        # Сравнить время прихода с началом работы
        start_time = rule.start_time

        # Если пришел ПОСЛЕ начала работы - опоздал
        if first_entry_time > start_time:
            # Вычислить опоздание в минутах
            entry_seconds = first_entry_time.hour * 3600 + first_entry_time.minute * 60 + first_entry_time.second
            start_seconds = start_time.hour * 3600 + start_time.minute * 60 + start_time.second
            late_seconds = entry_seconds - start_seconds
            minutes_late = late_seconds // 60

            return {
                "iin": iin,
                "firstname": firstname,
                "lastname": lastname,
                "patronymic": patronymic,
                "position": position,
                "position_type": emp_position_type,
                "cafedra": None,
                "faculty": None,
                "faculty_id": faculty_id,
                "subdivision": subdivision_name,
                "subdivision_id": subdivision_id,
                "late_type": "work_schedule",
                "expected_time": start_time.strftime("%H:%M:%S"),
                "first_entry_time": first_entry_time.strftime("%H:%M:%S"),
                "first_entry_datetime": first_entry_datetime.isoformat(),
                "minutes_late": int(minutes_late),
                "first_lesson": None,
                "work_schedule_rule": {
                    "position_type": rule.position_type,
                    "position": rule.position,
                    "start_time": start_time.strftime("%H:%M:%S"),
                    "description": rule.description,
                } if rule else None,
            }

        # Пришел вовремя
        return None
