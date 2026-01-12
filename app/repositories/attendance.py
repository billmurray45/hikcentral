"""
AttendanceRepository - работа с attendance_records
Read-only репозиторий для денормализованных данных
"""

from typing import Optional
from datetime import datetime
from sqlalchemy import select, func, or_, and_, distinct
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

        # Фильтр по факультету
        if filters.faculty:
            query = query.where(AttendanceRecord.person_group.ilike(f"%{filters.faculty}%"))

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

        if filters.faculty:
            query = query.where(AttendanceRecord.person_group.ilike(f"%{filters.faculty}%"))

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

    # ==========================================
    # РАБОТА С ФАКУЛЬТЕТАМИ
    # ==========================================

    async def get_faculties_list(
        self, include_stats: bool = False, person_type: Optional[str] = None, date: Optional[str] = None
    ) -> list[dict]:
        """
        Получить список всех факультетов с базовой статистикой

        Args:
            include_stats: Включить детальную статистику
            person_type: Фильтр по типу пользователя
            date: Дата для статистики

        Returns:
            Список словарей с данными о факультетах
        """
        # Базовый запрос
        query = select(AttendanceRecord).where(AttendanceRecord.person_group.isnot(None))

        # Фильтр по дате
        if date:
            query = query.where(AttendanceRecord.access_date == date)

        # Выполнить запрос
        result = await self.session.execute(query)
        records = result.scalars().all()

        # Группировать по факультетам
        from collections import defaultdict

        faculty_data = defaultdict(
            lambda: {
                "total_records": 0,
                "students": 0,
                "teachers": 0,
                "employees": 0,
                "other": 0,
                "unique_persons": set(),
                "last_activity": None,
            }
        )

        for record in records:
            faculty = record.faculty

            if not faculty:
                continue

            # Фильтр по типу пользователя
            if person_type:
                record_type = record.person_type
                # Группировать student_yu, student_yc, bachelor, master -> students
                if person_type == "students":
                    if record_type not in ["student_yu", "student_yc", "bachelor", "master"]:
                        continue
                elif person_type != record_type:
                    continue

            faculty_data[faculty]["total_records"] += 1

            # Подсчет по типам
            record_type = record.person_type
            if record_type in ["student_yu", "student_yc", "bachelor", "master"]:
                faculty_data[faculty]["students"] += 1
            elif record_type == "teacher":
                faculty_data[faculty]["teachers"] += 1
            elif record_type == "employee":
                faculty_data[faculty]["employees"] += 1
            else:
                faculty_data[faculty]["other"] += 1

            # Уникальные персоны
            if include_stats:
                faculty_data[faculty]["unique_persons"].add(record.employee_id)

            # Последняя активность
            if include_stats:
                if (
                    faculty_data[faculty]["last_activity"] is None
                    or record.access_datetime > faculty_data[faculty]["last_activity"]
                ):
                    faculty_data[faculty]["last_activity"] = record.access_datetime

        # Преобразовать в список
        faculties = []
        for name, stats in faculty_data.items():
            item = {"name": name, "total_records": stats["total_records"]}

            if include_stats:
                item.update(
                    {
                        "total_students": stats["students"],
                        "total_teachers": stats["teachers"],
                        "total_employees": stats["employees"],
                        "total_other": stats["other"],
                        "unique_persons": len(stats["unique_persons"]),
                        "last_activity": stats["last_activity"],
                    }
                )

            faculties.append(item)

        return faculties

    async def get_faculty_stats(
        self, faculty_name: str, date_from: Optional[str] = None, date_to: Optional[str] = None
    ) -> dict:
        """
        Получить детальную статистику факультета

        Args:
            faculty_name: Название факультета
            date_from: Начало периода
            date_to: Конец периода

        Returns:
            Словарь со статистикой
        """
        # Запрос для получения всех записей факультета
        query = select(AttendanceRecord).where(AttendanceRecord.person_group.isnot(None))

        # Фильтр по периоду
        if date_from:
            query = query.where(AttendanceRecord.access_date >= date_from)
        if date_to:
            query = query.where(AttendanceRecord.access_date <= date_to)

        result = await self.session.execute(query)
        all_records = result.scalars().all()

        # Фильтровать только записи нужного факультета
        faculty_records = [r for r in all_records if r.faculty == faculty_name]

        if not faculty_records:
            return {
                "total_entries": 0,
                "total_exits": 0,
                "unique_persons": 0,
                "by_type": {},
                "by_day": [],
                "peak_hour": None,
                "peak_hour_count": 0,
                "avg_daily_visits": 0.0,
            }

        # Подсчет статистики
        from collections import defaultdict

        total_entries = sum(1 for r in faculty_records if r.is_entry)
        total_exits = sum(1 for r in faculty_records if r.is_exit)
        unique_persons = len(set(r.employee_id for r in faculty_records))

        # По типам
        by_type = defaultdict(int)
        for r in faculty_records:
            type_name = r.person_type
            # Группировать студентов
            if type_name in ["student_yu", "student_yc"]:
                by_type["students"] += 1
            elif type_name in ["bachelor", "master"]:
                by_type["students"] += 1
            elif type_name == "teacher":
                by_type["teachers"] += 1
            elif type_name == "employee":
                by_type["employees"] += 1
            else:
                by_type["other"] += 1

        # По дням
        by_day_dict = defaultdict(int)
        for r in faculty_records:
            by_day_dict[r.access_date] += 1

        by_day = [{"date": date, "count": count} for date, count in sorted(by_day_dict.items())]

        # Час пик
        by_hour = defaultdict(int)
        for r in faculty_records:
            if r.access_time:
                hour = r.access_time[:2]  # Первые 2 символа (час)
                by_hour[hour] += 1

        peak_hour = None
        peak_hour_count = 0
        if by_hour:
            peak_hour, peak_hour_count = max(by_hour.items(), key=lambda x: x[1])

        # Средние значения
        days_count = len(by_day_dict) if by_day_dict else 1
        avg_daily_visits = len(faculty_records) / days_count

        return {
            "total_entries": total_entries,
            "total_exits": total_exits,
            "unique_persons": unique_persons,
            "by_type": dict(by_type),
            "by_day": by_day,
            "peak_hour": peak_hour,
            "peak_hour_count": peak_hour_count,
            "avg_daily_visits": round(avg_daily_visits, 2),
        }

    async def get_departments_list(self) -> list[dict]:
        """
        Получить список подразделений без факультета (для группировки)

        Returns:
            Список словарей с данными о подразделениях
        """
        # Получить все записи без факультета
        query = select(AttendanceRecord).where(AttendanceRecord.person_group.isnot(None))

        result = await self.session.execute(query)
        all_records = result.scalars().all()

        # Фильтровать записи без факультета
        no_faculty_records = [r for r in all_records if not r.faculty]

        # Группировать по первому уровню иерархии
        from collections import defaultdict

        departments = defaultdict(lambda: {"count": 0, "category": "other"})

        for record in no_faculty_records:
            # Извлечь первый уровень (до первого " > ")
            parts = record.person_group.split(" > ")
            if parts:
                dept_name = parts[0].strip()

                # Определить категорию
                category = "other"
                if "YC" in dept_name or "Обучающиеся YC" in dept_name:
                    category = "college"
                elif "Морская академия" in dept_name:
                    category = "marine"
                elif "Сотрудники YU" in dept_name or "Офис" in dept_name:
                    category = "administrative"

                departments[dept_name]["count"] += 1
                departments[dept_name]["category"] = category

        # Преобразовать в список
        result_list = [
            {"name": name, "total_records": data["count"], "category": data["category"]}
            for name, data in departments.items()
        ]

        return result_list

    async def get_late_arrivals(
        self, faculty_name: str, date: str, threshold_time: str = "09:00:00"
    ) -> list[dict]:
        """
        Получить список опоздавших по факультету

        Логика: Берем первый ВХОД каждого человека за день в факультете,
        фильтруем где access_time > threshold_time

        Args:
            faculty_name: Полное название факультета
            date: Дата в формате YYYY-MM-DD
            threshold_time: Пороговое время в формате HH:MM:SS

        Returns:
            Список dict с данными об опоздавших
        """
        # Подзапрос: найти ID первой записи "Вход" для каждого человека за день
        subquery = (
            select(AttendanceRecord.employee_id, func.min(AttendanceRecord.id).label("first_entry_id"))
            .where(
                and_(
                    AttendanceRecord.access_date == date,
                    AttendanceRecord.direction == "Вход",
                    AttendanceRecord.person_group.ilike(f"%{faculty_name}%"),
                )
            )
            .group_by(AttendanceRecord.employee_id)
            .subquery()
        )

        # Основной запрос: получить записи первых входов
        query = (
            select(AttendanceRecord)
            .join(subquery, AttendanceRecord.id == subquery.c.first_entry_id)
            .where(AttendanceRecord.access_time > threshold_time)
            .order_by(AttendanceRecord.access_time.asc())
        )

        result = await self.session.execute(query)
        records = result.scalars().all()

        # Вычислить минуты опоздания
        late_arrivals = []
        for record in records:
            # Парсинг времени для вычисления опоздания
            threshold_parts = threshold_time.split(":")
            arrival_parts = record.access_time.split(":")

            threshold_minutes = int(threshold_parts[0]) * 60 + int(threshold_parts[1])
            arrival_minutes = int(arrival_parts[0]) * 60 + int(arrival_parts[1])
            minutes_late = arrival_minutes - threshold_minutes

            late_arrivals.append(
                {
                    "employee_id": record.employee_id,
                    "person_name": record.person_name,
                    "iin": record.iin,
                    "person_type": record.person_type,
                    "faculty": record.faculty,
                    "first_entry_time": record.access_time,
                    "first_entry_datetime": record.access_datetime,
                    "minutes_late": minutes_late,
                }
            )

        return late_arrivals
