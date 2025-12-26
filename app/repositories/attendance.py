"""
AttendanceRepository - работа с attendance_records
Read-only репозиторий для денормализованных данных
"""

from typing import Optional
from datetime import datetime
from sqlalchemy import select, func, or_, distinct
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AttendanceRecord
from app.schemas.attendance import AttendanceFilter, PersonFilter

# Whitelist допустимых полей для сортировки (защита от SQL injection)
ALLOWED_SORT_FIELDS = {
    "id",
    "employee_id",
    "person_name",
    "access_date",
    "access_time",
    "access_datetime",
    "direction",
    "position",
    "position1",
    "person_group",
}


class AttendanceRepository:
    """
    Repository для работы с AttendanceRecord
    Только read операции для денормализованных данных
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    # ==========================================
    # ОСНОВНЫЕ ОПЕРАЦИИ ЧТЕНИЯ
    # ==========================================

    async def get_by_id(self, record_id: int) -> Optional[AttendanceRecord]:
        """
        Получить запись по ID

        Args:
            record_id: ID записи

        Returns:
            AttendanceRecord или None
        """
        stmt = select(AttendanceRecord).where(AttendanceRecord.id == record_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_list(self, filters: AttendanceFilter) -> tuple[list[AttendanceRecord], int]:
        """
        Получить список записей с фильтрами и пагинацией

        Args:
            filters: Параметры фильтрации (AttendanceFilter)

        Returns:
            (список AttendanceRecord, общее количество)
        """
        # Базовый запрос
        query = select(AttendanceRecord)

        # Применяем фильтры
        query = self._apply_filters(query, filters)

        # Подсчет общего количества
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.session.execute(count_query)
        total = total_result.scalar()

        # Сортировка (с защитой от SQL injection через whitelist)
        sort_field = filters.sort_by if filters.sort_by in ALLOWED_SORT_FIELDS else "id"
        sort_column = getattr(AttendanceRecord, sort_field)
        if filters.sort_order == "desc":
            query = query.order_by(sort_column.desc())
        else:
            query = query.order_by(sort_column.asc())

        # Пагинация
        offset = (filters.page - 1) * filters.page_size
        query = query.offset(offset).limit(filters.page_size)

        # Выполнение
        result = await self.session.execute(query)
        records = result.scalars().all()

        return list(records), total

    def _apply_filters(self, query, filters: AttendanceFilter):
        """Применить фильтры к запросу"""

        # Фильтр по дате
        if filters.date:
            query = query.where(AttendanceRecord.access_date == filters.date)

        # Фильтр по периоду
        if filters.date_from:
            query = query.where(AttendanceRecord.access_date >= filters.date_from)
        if filters.date_to:
            query = query.where(AttendanceRecord.access_date <= filters.date_to)

        # Фильтр по времени
        if filters.time_from:
            query = query.where(AttendanceRecord.access_time >= filters.time_from)
        if filters.time_to:
            query = query.where(AttendanceRecord.access_time <= filters.time_to)

        # Фильтр по направлению
        if filters.direction:
            query = query.where(AttendanceRecord.direction == filters.direction)

        # Фильтр по типу (нужно использовать CASE или подзапрос, но проще через фильтрацию в памяти или через position/position1)
        if filters.person_type:
            # Упрощенная фильтрация через position1
            if filters.person_type == "student_yu":
                query = query.where(AttendanceRecord.position1.ilike("%Студент YU%"))
            elif filters.person_type == "student_yc":
                query = query.where(AttendanceRecord.position1.ilike("%Студент YC%"))
            elif filters.person_type == "bachelor":
                query = query.where(AttendanceRecord.position1.ilike("%Бакалавр%"))
            elif filters.person_type == "master":
                query = query.where(AttendanceRecord.position1.ilike("%Магистрант%"))
            elif filters.person_type == "teacher":
                query = query.where(
                    or_(
                        AttendanceRecord.position.ilike("%преподаватель%"),
                        AttendanceRecord.position.ilike("%профессор%"),
                        AttendanceRecord.position.ilike("%доцент%"),
                    )
                )
            elif filters.person_type == "employee":
                query = query.where(AttendanceRecord.person_group.ilike("%Сотрудники YU%"))

        # Фильтр по position
        if filters.position:
            query = query.where(AttendanceRecord.position.ilike(f"%{filters.position}%"))

        # Фильтр по группе
        if filters.person_group:
            query = query.where(AttendanceRecord.person_group.ilike(f"%{filters.person_group}%"))

        # Фильтр по конкретному человеку
        if filters.employee_id:
            query = query.where(AttendanceRecord.employee_id == filters.employee_id)

        # Фильтр по ИИН
        if filters.iin:
            query = query.where(AttendanceRecord.iin == filters.iin)

        # Поиск
        if filters.search:
            search_pattern = f"%{filters.search}%"
            query = query.where(
                or_(
                    AttendanceRecord.person_name.ilike(search_pattern),
                    AttendanceRecord.iin.ilike(search_pattern),
                    AttendanceRecord.card_number.ilike(search_pattern),
                )
            )

        # Фильтр по устройству
        if filters.device_name:
            query = query.where(AttendanceRecord.device_name.ilike(f"%{filters.device_name}%"))

        return query

    # ==========================================
    # РАБОТА С ПЕРСОНАМИ (уникальные пользователи)
    # ==========================================

    async def get_unique_persons(self, filters: PersonFilter) -> tuple[list[dict], int]:
        """
        Получить список уникальных персон

        Args:
            filters: Параметры фильтрации (PersonFilter)

        Returns:
            (список dict с данными о персонах, общее количество)
        """
        # Подзапрос для получения последней записи каждого человека
        subquery = (
            select(
                AttendanceRecord.employee_id,
                func.max(AttendanceRecord.id).label("max_id"),
            )
            .group_by(AttendanceRecord.employee_id)
            .subquery()
        )

        # Основной запрос
        query = (
            select(AttendanceRecord)
            .join(subquery, AttendanceRecord.id == subquery.c.max_id)
        )

        # Применяем фильтры
        if filters.person_type:
            # Аналогично как в _apply_filters
            if filters.person_type == "student_yu":
                query = query.where(AttendanceRecord.position1.ilike("%Студент YU%"))
            elif filters.person_type == "student_yc":
                query = query.where(AttendanceRecord.position1.ilike("%Студент YC%"))
            # ... другие типы

        if filters.position:
            query = query.where(AttendanceRecord.position.ilike(f"%{filters.position}%"))

        if filters.person_group:
            query = query.where(AttendanceRecord.person_group.ilike(f"%{filters.person_group}%"))

        if filters.search:
            search_pattern = f"%{filters.search}%"
            query = query.where(
                or_(
                    AttendanceRecord.person_name.ilike(search_pattern),
                    AttendanceRecord.iin.ilike(search_pattern),
                )
            )

        # Подсчет
        count_query = select(func.count(distinct(AttendanceRecord.employee_id))).select_from(
            query.subquery()
        )
        total_result = await self.session.execute(count_query)
        total = total_result.scalar()

        # Сортировка и пагинация (с защитой от SQL injection)
        sort_field = filters.sort_by if filters.sort_by in ALLOWED_SORT_FIELDS else "person_name"
        sort_column = getattr(AttendanceRecord, sort_field)
        if filters.sort_order == "desc":
            query = query.order_by(sort_column.desc())
        else:
            query = query.order_by(sort_column.asc())

        offset = (filters.page - 1) * filters.page_size
        query = query.offset(offset).limit(filters.page_size)

        # Выполнение
        result = await self.session.execute(query)
        records = result.scalars().all()

        # Конвертируем в dict для удобства и получаем total_visits для каждого
        persons = []
        for record in records:
            # Получить количество визитов для данного человека
            count_query = select(func.count(AttendanceRecord.id)).where(
                AttendanceRecord.employee_id == record.employee_id
            )
            count_result = await self.session.execute(count_query)
            total_visits = count_result.scalar()

            persons.append(
                {
                    "employee_id": record.employee_id,
                    "person_name": record.person_name,
                    "first_name": record.first_name,
                    "last_name": record.last_name,
                    "patronymic": record.patronymic,
                    "iin": record.iin,
                    "person_type": record.person_type,
                    "position": record.position,
                    "position1": record.position1,
                    "person_group": record.person_group,
                    "faculty": record.faculty,
                    "department": record.department,
                    "group_name": record.group_name,
                    "total_visits": total_visits,
                    "last_visit": record.access_datetime,
                }
            )

        return persons, total

    async def get_person_by_id(self, employee_id: str) -> Optional[dict]:
        """
        Получить информацию о персоне по employee_id

        Args:
            employee_id: ID сотрудника

        Returns:
            dict с данными о персоне или None
        """
        # Получить последнюю запись этого человека
        query = (
            select(AttendanceRecord)
            .where(AttendanceRecord.employee_id == employee_id)
            .order_by(AttendanceRecord.id.desc())
            .limit(1)
        )

        result = await self.session.execute(query)
        record = result.scalar_one_or_none()

        if not record:
            return None

        # Подсчитать количество визитов
        count_query = select(func.count(AttendanceRecord.id)).where(
            AttendanceRecord.employee_id == employee_id
        )
        total_visits = await self.session.scalar(count_query)

        return {
            "employee_id": record.employee_id,
            "person_name": record.person_name,
            "first_name": record.first_name,
            "last_name": record.last_name,
            "patronymic": record.patronymic,
            "iin": record.iin,
            "person_type": record.person_type,
            "position": record.position,
            "position1": record.position1,
            "person_group": record.person_group,
            "faculty": record.faculty,
            "department": record.department,
            "group_name": record.group_name,
            "total_visits": total_visits,
            "last_visit": record.access_datetime,
        }

    async def get_person_history(
        self, employee_id: str, page: int = 1, page_size: int = 50
    ) -> dict:
        """
        Получить историю проходов конкретной персоны

        Args:
            employee_id: ID сотрудника
            page: Номер страницы
            page_size: Размер страницы

        Returns:
            dict с ключами: person, records, total, page, page_size
        """
        # Получить информацию о персоне
        person = await self.get_person_by_id(employee_id)

        if not person:
            return {
                "person": None,
                "records": [],
                "total": 0,
                "page": page,
                "page_size": page_size,
            }

        # Запрос для истории
        query = (
            select(AttendanceRecord)
            .where(AttendanceRecord.employee_id == employee_id)
            .order_by(AttendanceRecord.id.desc())
        )

        # Подсчет
        count_query = select(func.count(AttendanceRecord.id)).where(
            AttendanceRecord.employee_id == employee_id
        )
        total = await self.session.scalar(count_query)

        # Пагинация
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size)

        # Выполнение
        result = await self.session.execute(query)
        records = result.scalars().all()

        return {
            "person": person,
            "records": list(records),
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    # ==========================================
    # СТАТИСТИКА
    # ==========================================

    async def get_total_count(self, filters: Optional[AttendanceFilter] = None) -> int:
        """Общее количество записей с учетом фильтров"""
        query = select(func.count(AttendanceRecord.id))

        if filters:
            base_query = select(AttendanceRecord)
            base_query = self._apply_filters(base_query, filters)
            query = select(func.count()).select_from(base_query.subquery())

        result = await self.session.execute(query)
        return result.scalar()

    async def get_unique_persons_count(self, date: Optional[str] = None) -> int:
        """Количество уникальных персон"""
        query = select(func.count(distinct(AttendanceRecord.employee_id)))

        if date:
            query = query.where(AttendanceRecord.access_date == date)

        result = await self.session.execute(query)
        return result.scalar()

    async def count_by_direction(self, date: Optional[str] = None) -> list[tuple[str, int]]:
        """
        Группировка по направлениям (Вход/Выход)

        Args:
            date: Опциональная дата для фильтрации

        Returns:
            Список кортежей (direction, count)
        """
        query = (
            select(AttendanceRecord.direction, func.count(AttendanceRecord.id))
            .group_by(AttendanceRecord.direction)
        )

        if date:
            query = query.where(AttendanceRecord.access_date == date)

        result = await self.session.execute(query)
        return result.all()

    async def count_by_hour(self, date: str) -> list[tuple[str, int]]:
        """
        Группировка по часам для конкретной даты

        Args:
            date: Дата (YYYY-MM-DD)

        Returns:
            Список кортежей (hour, count)
        """
        # Извлечь час из access_time (формат HH:MM:SS)
        query = (
            select(
                func.substr(AttendanceRecord.access_time, 1, 2).label("hour"),
                func.count(AttendanceRecord.id),
            )
            .where(AttendanceRecord.access_date == date)
            .group_by("hour")
            .order_by("hour")
        )

        result = await self.session.execute(query)
        return result.all()

    async def get_stats(
        self, date_from: Optional[str] = None, date_to: Optional[str] = None
    ) -> dict:
        """
        Получить полную статистику

        Args:
            date_from: Дата начала (опционально)
            date_to: Дата окончания (опционально)

        Returns:
            dict со статистикой
        """
        # Базовый запрос
        base_query = select(AttendanceRecord)

        if date_from:
            base_query = base_query.where(AttendanceRecord.access_date >= date_from)
        if date_to:
            base_query = base_query.where(AttendanceRecord.access_date <= date_to)

        # Общее количество
        count_query = select(func.count()).select_from(base_query.subquery())
        total = await self.session.scalar(count_query)

        # Уникальные персоны
        unique_query = select(func.count(distinct(AttendanceRecord.employee_id))).select_from(
            base_query.subquery()
        )
        unique_persons = await self.session.scalar(unique_query)

        # По направлениям
        direction_query = (
            select(AttendanceRecord.direction, func.count(AttendanceRecord.id))
            .select_from(base_query.subquery())
            .group_by(AttendanceRecord.direction)
        )
        directions = await self.session.execute(direction_query)
        by_direction_dict = dict(directions.all())

        # Получаем записи для подсчета по типам (придется загрузить все и подсчитать в памяти)
        # Это не эффективно, но учитывая что person_type - это property, нужно так
        result = await self.session.execute(base_query)
        all_records = result.scalars().all()

        # Подсчет по типам
        type_counts = {}
        for record in all_records:
            p_type = record.person_type
            type_counts[p_type] = type_counts.get(p_type, 0) + 1

        # Форматирование результатов
        by_type = [{"person_type": k, "count": v} for k, v in type_counts.items()]
        by_direction = [{"direction": k, "count": v} for k, v in by_direction_dict.items()]

        return {
            "total_records": total,
            "total_entries": by_direction_dict.get("Вход", 0),
            "total_exits": by_direction_dict.get("Выход", 0),
            "unique_persons": unique_persons,
            "by_type": by_type,
            "by_direction": by_direction,
            "date_from": date_from,
            "date_to": date_to,
        }

    async def get_daily_summary(self, date: str) -> dict:
        """
        Получить сводку за день

        Args:
            date: Дата (YYYY-MM-DD)

        Returns:
            dict с дневной статистикой
        """
        # Базовая статистика
        stats = await self.get_stats(date_from=date, date_to=date)

        # По часам
        by_hour = await self.count_by_hour(date)

        # Пиковый час
        peak_hour = None
        peak_hour_count = 0
        if by_hour:
            peak_hour, peak_hour_count = max(by_hour, key=lambda x: x[1])

        # Извлечь счетчики по типам из stats
        students_yu = 0
        students_yc = 0
        teachers = 0
        employees = 0
        other = 0

        for item in stats["by_type"]:
            if item["person_type"] == "student_yu":
                students_yu = item["count"]
            elif item["person_type"] == "student_yc":
                students_yc = item["count"]
            elif item["person_type"] == "teacher":
                teachers = item["count"]
            elif item["person_type"] == "employee":
                employees = item["count"]
            else:
                other += item["count"]

        return {
            "date": date,
            "total_entries": stats["total_entries"],
            "total_exits": stats["total_exits"],
            "unique_persons": stats["unique_persons"],
            "students_yu": students_yu,
            "students_yc": students_yc,
            "teachers": teachers,
            "employees": employees,
            "other": other,
            "peak_hour": peak_hour,
            "peak_hour_count": peak_hour_count,
        }

    # ==========================================
    # ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ
    # ==========================================

    async def search(self, query: str, limit: int = 20) -> list[AttendanceRecord]:
        """
        Быстрый поиск записей

        Args:
            query: Поисковый запрос
            limit: Максимальное количество результатов

        Returns:
            Список найденных записей
        """
        search_pattern = f"%{query}%"

        stmt = (
            select(AttendanceRecord)
            .where(
                or_(
                    AttendanceRecord.person_name.ilike(search_pattern),
                    AttendanceRecord.iin.ilike(search_pattern),
                    AttendanceRecord.employee_id.ilike(search_pattern),
                )
            )
            .order_by(AttendanceRecord.id.desc())
            .limit(limit)
        )

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_latest(self, limit: int = 50) -> list[AttendanceRecord]:
        """
        Получить последние записи

        Args:
            limit: Количество записей

        Returns:
            Список последних записей
        """
        stmt = select(AttendanceRecord).order_by(AttendanceRecord.id.desc()).limit(limit)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())
