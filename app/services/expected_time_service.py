"""
Сервис для определения ожидаемого времени начала работы сотрудников
"""
from typing import Optional, Dict, Tuple
from datetime import date, datetime
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import WorkScheduleRule, TeacherSchedule


class ExpectedTimeService:
    """Сервис для определения expected_time сотрудников"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self._rules_cache: Optional[list[WorkScheduleRule]] = None
        self._result_cache: Dict[Tuple, Optional[str]] = {}

    async def load_rules(self):
        """Загрузить все активные правила в кеш (вызывать один раз перед батчем)"""
        if self._rules_cache is None:
            query = select(WorkScheduleRule).where(
                WorkScheduleRule.is_active == True
            ).order_by(WorkScheduleRule.priority.desc())
            result = await self.db.execute(query)
            self._rules_cache = result.scalars().all()

    async def get_expected_time(
        self,
        position_type: Optional[str],
        position: Optional[str],
        subdivision_id: Optional[int],
        faculty_id: Optional[int],
        iin: Optional[str] = None,
        target_date: Optional[date] = None,
    ) -> Optional[str]:
        """
        Определить ожидаемое время начала работы

        Логика:
        1. Преподаватели -> время первого урока на указанную дату (или "Нет уроков")
        2. Остальные -> поиск правила по каскадной логике:
           - Конкретная должность (position)
           - Тип должности (position_type)
           - Подразделение (subdivision_id)
           - Факультет (faculty_id)
           - Общее правило (все NULL)

        Args:
            position_type: Тип должности
            position: Должность
            subdivision_id: ID подразделения
            faculty_id: ID факультета
            iin: ИИН сотрудника (для преподавателей)
            target_date: Дата для определения расписания (по умолчанию сегодня)

        Returns:
            str: Время в формате "HH:MM" или "Нет уроков" или None
        """

        # Преподаватели идут по расписанию уроков
        if position_type == "Преподаватель":
            if not iin:
                return "Нет данных"

            # Получить первый урок на указанную дату
            if target_date is None:
                target_date = date.today()

            weekday = target_date.isoweekday()  # 1=Понедельник, 7=Воскресенье

            # Найти первый урок преподавателя на этот день недели
            first_lesson_query = select(TeacherSchedule).where(
                and_(
                    TeacherSchedule.iin == iin,
                    TeacherSchedule.week_day == weekday,
                    TeacherSchedule.study_year == 2025,
                    TeacherSchedule.study_term == 2,
                )
            ).order_by(TeacherSchedule.lesson_start).limit(1)

            result = await self.db.execute(first_lesson_query)
            first_lesson = result.scalars().first()

            if first_lesson:
                return first_lesson.lesson_start.strftime("%H:%M")
            else:
                return "Нет уроков"

        # Проверить кеш для не-преподавателей
        cache_key = (position_type, position, subdivision_id, faculty_id)
        if cache_key in self._result_cache:
            return self._result_cache[cache_key]

        # Загрузить правила если еще не загружены
        await self.load_rules()

        # Для остальных ищем правило по каскадной логике (используя кеш правил)
        rule = self._find_work_schedule_rule_from_cache(
            position_type, position, subdivision_id, faculty_id
        )

        result = rule.start_time.strftime("%H:%M") if rule else None
        self._result_cache[cache_key] = result
        return result

    def _find_work_schedule_rule_from_cache(
        self,
        position_type: Optional[str],
        position: Optional[str],
        subdivision_id: Optional[int],
        faculty_id: Optional[int],
    ) -> Optional[WorkScheduleRule]:
        """
        Найти применимое правило рабочего времени из кеша по каскадной логике

        Приоритеты (от высокого к низкому):
        1. Конкретная должность (position)
        2. Тип должности (position_type)
        3. Подразделение (subdivision_id)
        4. Факультет (faculty_id)
        5. Общее правило (все NULL)
        """

        if not self._rules_cache:
            return None

        # 1. Сначала ищем по конкретной должности
        if position:
            for rule in self._rules_cache:
                if rule.position == position:
                    return rule

        # 2. Если не нашли, ищем по типу должности
        if position_type:
            for rule in self._rules_cache:
                if (
                    rule.position_type == position_type
                    and rule.position is None
                ):
                    return rule

        # 3. Если не нашли, ищем по подразделению
        if subdivision_id:
            for rule in self._rules_cache:
                if (
                    rule.subdivision_id == subdivision_id
                    and rule.position is None
                    and rule.position_type is None
                ):
                    return rule

        # 4. Если не нашли, ищем по факультету
        if faculty_id:
            for rule in self._rules_cache:
                if (
                    rule.faculty_id == faculty_id
                    and rule.position is None
                    and rule.position_type is None
                    and rule.subdivision_id is None
                ):
                    return rule

        # 5. Если не нашли, ищем общее правило (все критерии NULL)
        for rule in self._rules_cache:
            if (
                rule.position is None
                and rule.position_type is None
                and rule.subdivision_id is None
                and rule.faculty_id is None
            ):
                return rule

        return None
