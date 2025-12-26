"""
AttendanceService - Бизнес-логика для работы с attendance records
"""

import json
from typing import Optional
from datetime import datetime, date
from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis

from app.repositories.attendance import AttendanceRepository
from app.schemas import (
    AttendanceFilter,
    AttendanceListResponse,
    AttendanceRecordResponse,
    AttendanceRecordShort,
    AttendanceStatsResponse,
    PersonFilter,
    PersonInfo,
    PersonListResponse,
    PersonHistoryResponse,
    DailyAttendanceSummary,
)
from app.core.config import settings


class AttendanceService:
    """
    Service для работы с attendance records.
    Содержит бизнес-логику, кэширование и трансформацию данных.
    """

    def __init__(self, session: AsyncSession, redis: Redis):
        self.repo = AttendanceRepository(session)
        self.redis = redis

    # ==========================================
    # ОСНОВНЫЕ МЕТОДЫ (с кэшированием)
    # ==========================================

    async def get_stats(
        self, date_from: Optional[str] = None, date_to: Optional[str] = None
    ) -> AttendanceStatsResponse:
        """
        Получить статистику по посещаемости с кэшированием

        Args:
            date_from: Дата начала периода (YYYY-MM-DD)
            date_to: Дата окончания периода (YYYY-MM-DD)

        Returns:
            AttendanceStatsResponse со статистикой
        """
        # Валидация дат
        self._validate_date_range(date_from, date_to)

        # Проверка кэша
        cache_key = f"stats:{date_from or 'all'}:{date_to or 'all'}"
        cached = await self._get_cached(cache_key)
        if cached:
            return AttendanceStatsResponse(**cached)

        # Получение из репозитория
        stats = await self.repo.get_stats(date_from=date_from, date_to=date_to)

        # Сохранение в кэш (TTL 5 минут)
        await self._set_cache(cache_key, stats, ttl=settings.CACHE_DAILY_TTL)

        return AttendanceStatsResponse(**stats)

    async def get_daily_summary(self, date: str) -> DailyAttendanceSummary:
        """
        Получить дневную сводку с кэшированием

        Args:
            date: Дата (YYYY-MM-DD)

        Returns:
            DailyAttendanceSummary с дневной статистикой
        """
        # Валидация даты
        self._validate_date(date)

        # Проверка кэша
        cache_key = f"daily_summary:{date}"
        cached = await self._get_cached(cache_key)
        if cached:
            return DailyAttendanceSummary(**cached)

        # Получение из репозитория
        summary = await self.repo.get_daily_summary(date)

        # Сохранение в кэш (TTL 5 минут)
        await self._set_cache(cache_key, summary, ttl=settings.CACHE_DAILY_TTL)

        return DailyAttendanceSummary(**summary)

    async def get_unique_persons(self, filters: PersonFilter) -> PersonListResponse:
        """
        Получить список уникальных персон с кэшированием

        Args:
            filters: Параметры фильтрации

        Returns:
            PersonListResponse со списком персон
        """
        # Проверка кэша
        cache_key = self._build_cache_key("persons", filters.model_dump())
        cached = await self._get_cached(cache_key)
        if cached:
            return PersonListResponse(**cached)

        # Получение из репозитория
        persons_data, total = await self.repo.get_unique_persons(filters)

        # Конвертация в PersonInfo
        persons = [PersonInfo(**p) for p in persons_data]

        # Подсчет количества страниц
        pages = (total + filters.page_size - 1) // filters.page_size

        response = PersonListResponse(
            total=total,
            page=filters.page,
            page_size=filters.page_size,
            pages=pages,
            items=persons,
        )

        # Сохранение в кэш (TTL 10 минут)
        await self._set_cache(cache_key, response.model_dump(), ttl=settings.CACHE_SUMMARY_TTL)

        return response

    async def get_person_by_id(self, employee_id: str) -> PersonInfo:
        """
        Получить информацию о персоне с кэшированием

        Args:
            employee_id: ID сотрудника

        Returns:
            PersonInfo с данными о персоне

        Raises:
            ValueError: Если персона не найдена
        """
        # Проверка кэша
        cache_key = f"person:{employee_id}"
        cached = await self._get_cached(cache_key)
        if cached:
            return PersonInfo(**cached)

        # Получение из репозитория
        person_data = await self.repo.get_person_by_id(employee_id)

        if not person_data:
            raise ValueError(f"Person with employee_id={employee_id} not found")

        person = PersonInfo(**person_data)

        # Сохранение в кэш (TTL 15 минут - person info редко меняется)
        await self._set_cache(cache_key, person.model_dump(), ttl=settings.CACHE_EMPLOYEE_TTL)

        return person

    # ==========================================
    # РЕАЛЬНОГО ВРЕМЕНИ (без кэша)
    # ==========================================

    async def get_list(self, filters: AttendanceFilter) -> AttendanceListResponse:
        """
        Получить список attendance records БЕЗ кэша (реальное время)

        Args:
            filters: Параметры фильтрации

        Returns:
            AttendanceListResponse со списком записей
        """
        # Валидация дат
        if filters.date_from and filters.date_to:
            self._validate_date_range(filters.date_from, filters.date_to)

        # Получение из репозитория
        records, total = await self.repo.get_list(filters)

        # Конвертация в AttendanceRecordShort
        items = []
        for record in records:
            items.append(
                AttendanceRecordShort(
                    id=record.id,
                    employee_id=record.employee_id,
                    person_name=record.person_name,
                    iin=record.iin,
                    person_type=record.person_type,
                    access_datetime=record.access_datetime,
                    access_date=record.access_date,
                    access_time=record.access_time,
                    direction=record.direction,
                    device_name=record.device_name,
                )
            )

        # Подсчет количества страниц
        pages = (total + filters.page_size - 1) // filters.page_size

        return AttendanceListResponse(
            total=total,
            page=filters.page,
            page_size=filters.page_size,
            pages=pages,
            items=items,
        )

    async def get_by_id(self, record_id: int) -> AttendanceRecordResponse:
        """
        Получить одну запись по ID

        Args:
            record_id: ID записи

        Returns:
            AttendanceRecordResponse с полной информацией

        Raises:
            ValueError: Если запись не найдена
        """
        # Используем фильтр для поиска по ID
        filters = AttendanceFilter(page=1, page_size=1)
        records, _ = await self.repo.get_list(filters)

        # Ищем по ID
        record = None
        for r in records:
            if r.id == record_id:
                record = r
                break

        if not record:
            raise ValueError(f"Record with id={record_id} not found")

        # Конвертация в AttendanceRecordResponse
        return AttendanceRecordResponse(
            id=record.id,
            employee_id=record.employee_id,
            person_name=record.person_name,
            first_name=record.first_name,
            last_name=record.last_name,
            patronymic=record.patronymic,
            iin=record.iin,
            position=record.position,
            position1=record.position1,
            person_group=record.person_group,
            person_type=record.person_type,
            faculty=record.faculty,
            department=record.department,
            group_name=record.group_name,
            access_datetime=record.access_datetime,
            access_date=record.access_date,
            access_time=record.access_time,
            direction=record.direction,
            is_entry=record.is_entry,
            is_exit=record.is_exit,
            device_name=record.device_name,
            resource_name=record.resource_name,
            card_number=record.card_number,
            auth_result=record.auth_result,
            auth_type=record.auth_type,
            created_at=record.created_at,
        )

    async def get_person_history(
        self, employee_id: str, page: int = 1, page_size: int = 50
    ) -> PersonHistoryResponse:
        """
        Получить историю проходов персоны БЕЗ кэша

        Args:
            employee_id: ID сотрудника
            page: Номер страницы
            page_size: Размер страницы

        Returns:
            PersonHistoryResponse с историей

        Raises:
            ValueError: Если персона не найдена
        """
        # Получение из репозитория
        result = await self.repo.get_person_history(employee_id, page, page_size)

        if not result["person"]:
            raise ValueError(f"Person with employee_id={employee_id} not found")

        # Конвертация PersonInfo
        person = PersonInfo(**result["person"])

        # Конвертация records
        records = []
        for r in result["records"]:
            records.append(
                AttendanceRecordShort(
                    id=r.id,
                    employee_id=r.employee_id,
                    person_name=r.person_name,
                    iin=r.iin,
                    person_type=r.person_type,
                    access_datetime=r.access_datetime,
                    access_date=r.access_date,
                    access_time=r.access_time,
                    direction=r.direction,
                    device_name=r.device_name,
                )
            )

        return PersonHistoryResponse(
            person=person,
            records=records,
            total=result["total"],
            page=result["page"],
            page_size=result["page_size"],
        )

    # ==========================================
    # ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ
    # ==========================================

    async def search(self, query: str, limit: int = 20) -> list[AttendanceRecordShort]:
        """
        Быстрый поиск записей

        Args:
            query: Поисковый запрос
            limit: Максимальное количество результатов

        Returns:
            Список AttendanceRecordShort
        """
        records = await self.repo.search(query, limit)

        return [
            AttendanceRecordShort(
                id=r.id,
                employee_id=r.employee_id,
                person_name=r.person_name,
                iin=r.iin,
                person_type=r.person_type,
                access_datetime=r.access_datetime,
                access_date=r.access_date,
                access_time=r.access_time,
                direction=r.direction,
                device_name=r.device_name,
            )
            for r in records
        ]

    async def get_latest(self, limit: int = 10) -> list[AttendanceRecordShort]:
        """
        Получить последние записи

        Args:
            limit: Количество записей

        Returns:
            Список AttendanceRecordShort
        """
        records = await self.repo.get_latest(limit)

        return [
            AttendanceRecordShort(
                id=r.id,
                employee_id=r.employee_id,
                person_name=r.person_name,
                iin=r.iin,
                person_type=r.person_type,
                access_datetime=r.access_datetime,
                access_date=r.access_date,
                access_time=r.access_time,
                direction=r.direction,
                device_name=r.device_name,
            )
            for r in records
        ]

    # ==========================================
    # ПРИВАТНЫЕ МЕТОДЫ КЭШИРОВАНИЯ
    # ==========================================

    async def _get_cached(self, key: str) -> Optional[dict]:
        """
        Получить данные из кэша

        Args:
            key: Ключ кэша

        Returns:
            dict с данными или None
        """
        try:
            cached = await self.redis.get(key)
            if cached:
                return json.loads(cached)
        except Exception:
            # Игнорируем ошибки кэша
            pass
        return None

    async def _set_cache(self, key: str, data: dict, ttl: int):
        """
        Сохранить данные в кэш

        Args:
            key: Ключ кэша
            data: Данные для сохранения
            ttl: Время жизни в секундах
        """
        try:
            await self.redis.setex(key, ttl, json.dumps(data))
        except Exception:
            # Игнорируем ошибки кэша
            pass

    async def invalidate_cache(self, pattern: str = "*"):
        """
        Инвалидировать кэш по паттерну

        Args:
            pattern: Паттерн ключей (например "stats:*")
        """
        try:
            keys = await self.redis.keys(pattern)
            if keys:
                await self.redis.delete(*keys)
        except Exception:
            # Игнорируем ошибки кэша
            pass

    # ==========================================
    # ВАЛИДАЦИЯ
    # ==========================================

    def _validate_date(self, date_str: str):
        """
        Валидация даты

        Args:
            date_str: Дата в формате YYYY-MM-DD

        Raises:
            ValueError: Если формат даты неверный или дата в будущем
        """
        try:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            raise ValueError(f"Invalid date format: {date_str}. Expected YYYY-MM-DD")

        # Проверка что дата не в будущем
        if date_obj > date.today():
            raise ValueError(f"Date {date_str} is in the future")

    def _validate_date_range(self, date_from: Optional[str], date_to: Optional[str]):
        """
        Валидация периода дат

        Args:
            date_from: Дата начала
            date_to: Дата окончания

        Raises:
            ValueError: Если период некорректный
        """
        if date_from:
            self._validate_date(date_from)

        if date_to:
            self._validate_date(date_to)

        # Проверка что date_from <= date_to
        if date_from and date_to:
            from_obj = datetime.strptime(date_from, "%Y-%m-%d").date()
            to_obj = datetime.strptime(date_to, "%Y-%m-%d").date()

            if from_obj > to_obj:
                raise ValueError(f"date_from ({date_from}) must be <= date_to ({date_to})")

    def _build_cache_key(self, prefix: str, params: dict) -> str:
        """
        Построить ключ кэша из параметров

        Args:
            prefix: Префикс ключа
            params: Параметры запроса

        Returns:
            Ключ кэша
        """
        # Сортируем параметры и убираем None
        filtered = {k: v for k, v in sorted(params.items()) if v is not None}
        params_str = ":".join(f"{k}={v}" for k, v in filtered.items())
        return f"{prefix}:{params_str}" if params_str else prefix
