"""
Сервис для работы с правилами рабочего времени
"""

from datetime import time
from typing import Optional, Dict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import WorkScheduleRule, PlatonusEmployee


class WorkScheduleService:
    """Сервис для получения правил рабочего времени"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self._rules_cache: Optional[list[WorkScheduleRule]] = None

    async def load_active_rules(self) -> list[WorkScheduleRule]:
        """
        Загрузить все активные правила из БД и кешировать

        Правила сортируются по приоритету (от высокого к низкому)
        """
        if self._rules_cache is None:
            query = (
                select(WorkScheduleRule)
                .where(WorkScheduleRule.is_active == True)
                .order_by(WorkScheduleRule.priority.desc(), WorkScheduleRule.id)
            )
            result = await self.db.execute(query)
            self._rules_cache = result.scalars().all()

        return self._rules_cache

    def get_threshold_for_employee(
        self,
        employee: PlatonusEmployee,
        rules: list[WorkScheduleRule],
        default_threshold: time,
        entry_time: Optional[time] = None,
    ) -> time:
        """
        Получить пороговое время для конкретного сотрудника на основе правил

        Логика применения правил (по приоритету):
        1. Специальная логика для охранников (определение смены по времени прихода)
        2. Точное совпадение по должности + faculty_id/subdivision_id
        3. Точное совпадение по должности
        4. Совпадение по типу должности + faculty_id/subdivision_id
        5. Совпадение по типу должности
        6. Дефолтное время

        Args:
            employee: Объект сотрудника из Platonus
            rules: Список активных правил (отсортированных по приоритету)
            default_threshold: Время по умолчанию если ничего не подошло
            entry_time: Время прихода сотрудника (для определения смены)

        Returns:
            time: Пороговое время начала работы для этого сотрудника
        """

        # Специальная логика для охранников - определяем смену по времени прихода
        if employee.position and 'охранник' in employee.position.lower() and entry_time:
            # Дневная смена: 06:00 - 18:00 → проверяем с 08:00
            # Ночная смена: 18:00 - 06:00 → проверяем с 20:00
            if time(6, 0) <= entry_time < time(18, 0):
                # Дневная смена
                return time(8, 0)
            else:
                # Ночная смена
                return time(20, 0)

        for rule in rules:
            # Проверка совпадения по должности (точное совпадение или ILIKE)
            position_match = False
            if rule.position:
                if employee.position and rule.position.lower() in employee.position.lower():
                    position_match = True

            # Проверка совпадения по типу должности
            position_type_match = False
            if rule.position_type:
                if employee.position_type == rule.position_type:
                    position_type_match = True
                # Специальный случай: "Все сотрудники"
                elif rule.position_type == "Все сотрудники":
                    position_type_match = True

            # Если ни одно из условий не совпало - пропускаем правило
            if not position_match and not position_type_match:
                continue

            # Проверка дополнительных фильтров (faculty_id, subdivision_id)
            # Если в правиле указан faculty_id, он должен совпадать
            if rule.faculty_id is not None:
                if employee.faculty_id != rule.faculty_id:
                    continue

            # Если в правиле указан subdivision_id, он должен совпадать
            if rule.subdivision_id is not None:
                if employee.subdivision_id != rule.subdivision_id:
                    continue

            # Если мы дошли сюда - правило подошло!
            return rule.start_time

        # Если ничего не подошло - вернуть дефолтное время
        return default_threshold

    async def get_thresholds_for_employees(
        self,
        employees: list[PlatonusEmployee],
        default_threshold: time,
    ) -> Dict[str, time]:
        """
        Получить пороговые времена для списка сотрудников

        Args:
            employees: Список сотрудников
            default_threshold: Время по умолчанию

        Returns:
            Dict[str, time]: Словарь {iin: threshold_time}
        """

        # Загрузить правила один раз
        rules = await self.load_active_rules()

        # Определить пороговое время для каждого сотрудника
        thresholds = {}
        for employee in employees:
            threshold = self.get_threshold_for_employee(employee, rules, default_threshold)
            thresholds[employee.iin] = threshold

        return thresholds

    async def get_threshold_for_iin(
        self,
        iin: str,
        default_threshold: time,
    ) -> time:
        """
        Получить пороговое время для конкретного IIN

        Args:
            iin: ИИН сотрудника
            default_threshold: Время по умолчанию

        Returns:
            time: Пороговое время
        """

        # Найти сотрудника
        query = select(PlatonusEmployee).where(PlatonusEmployee.iin == iin)
        result = await self.db.execute(query)
        employee = result.scalar_one_or_none()

        if not employee:
            return default_threshold

        # Загрузить правила
        rules = await self.load_active_rules()

        # Получить пороговое время
        return self.get_threshold_for_employee(employee, rules, default_threshold)

    async def get_all_unique_thresholds(self) -> Dict[str, time]:
        """
        Получить все уникальные пороговые времена из активных правил

        Полезно для отображения в интерфейсе или аналитики

        Returns:
            Dict[str, time]: Словарь {описание_условия: threshold_time}
        """

        rules = await self.load_active_rules()

        thresholds = {}
        for rule in rules:
            condition = rule.position_type or rule.position or "Unknown"
            thresholds[condition] = rule.start_time

        return thresholds
