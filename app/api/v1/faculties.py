"""
Faculty API endpoints
"""

from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis

from app.api.dependencies import get_db, get_redis_client
from app.services.attendance import AttendanceService
from app.schemas import (
    FacultyListResponse,
    FacultyStats,
    DepartmentListResponse,
    PersonListResponse,
    PersonFilter,
    AttendanceListResponse,
    AttendanceFilter,
    get_faculty_name,
)


router = APIRouter(prefix="/faculties", tags=["Faculties"])


def get_service(
    db: AsyncSession = Depends(get_db), redis: Redis = Depends(get_redis_client)
) -> AttendanceService:
    """Dependency для получения AttendanceService"""
    return AttendanceService(db, redis)


@router.get(
    "",
    response_model=FacultyListResponse,
    summary="Получить список факультетов",
    description="""
    Получить список всех факультетов с базовой или детальной статистикой.

    **Параметры:**
    - `include_stats`: Включить детальную статистику (студенты, преподаватели, и т.д.)
    - `person_type`: Фильтр по типу пользователя (student, teacher, employee, other)
    - `date`: Дата для статистики (YYYY-MM-DD)
    - `sort_by`: Поле для сортировки (name, total_records)
    - `sort_order`: Порядок сортировки (asc, desc)

    **Кэширование:**
    - Базовый список: 24 часа
    - С детальной статистикой: 5 минут
    """,
)
async def get_faculties(
    include_stats: bool = Query(False, description="Включить детальную статистику"),
    person_type: Optional[str] = Query(None, description="Фильтр по типу пользователя"),
    date: Optional[str] = Query(None, description="Дата для статистики (YYYY-MM-DD)"),
    sort_by: str = Query("name", description="Поле для сортировки"),
    sort_order: str = Query("asc", description="Порядок: asc или desc"),
    service: AttendanceService = Depends(get_service),
):
    """
    Получить список всех факультетов
    """
    return await service.get_faculties(
        include_stats=include_stats,
        person_type=person_type,
        date=date,
        sort_by=sort_by,
        sort_order=sort_order,
    )


@router.get(
    "/{faculty_id}/stats",
    response_model=FacultyStats,
    summary="Получить детальную статистику факультета",
    description="""
    Получить детальную статистику для конкретного факультета.

    **URL параметры:**
    - `faculty_id`: Slug факультета (engineering, tourism, science, и т.д.)

    **Query параметры:**
    - `date_from`: Начало периода (YYYY-MM-DD)
    - `date_to`: Конец периода (YYYY-MM-DD)

    **Статистика включает:**
    - Общее количество входов/выходов
    - Уникальных персон
    - Распределение по типам пользователей
    - Распределение по дням
    - Час пик
    - Средние значения

    **Кэширование:** 5 минут
    """,
)
async def get_faculty_stats(
    faculty_id: str,
    date_from: Optional[str] = Query(None, description="Начало периода (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="Конец периода (YYYY-MM-DD)"),
    service: AttendanceService = Depends(get_service),
):
    """
    Получить детальную статистику факультета
    """
    # Проверить, что faculty_id валидный
    faculty_name = get_faculty_name(faculty_id)
    if not faculty_name:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Faculty with id '{faculty_id}' not found",
        )

    return await service.get_faculty_stats(
        faculty_slug=faculty_id,
        date_from=date_from,
        date_to=date_to,
    )


@router.get(
    "/{faculty_id}/persons",
    response_model=PersonListResponse,
    summary="Получить список персон факультета",
    description="""
    Получить список уникальных персон, принадлежащих к факультету.

    **URL параметры:**
    - `faculty_id`: Slug факультета

    **Query параметры:**
    - `person_type`: Фильтр по типу (student, teacher, employee, other)
    - `search`: Поиск по имени или IIN
    - `page`: Номер страницы (начиная с 1)
    - `page_size`: Размер страницы (10-100)
    - `sort_by`: Поле для сортировки
    - `sort_order`: Порядок сортировки (asc, desc)
    """,
)
async def get_faculty_persons(
    faculty_id: str,
    person_type: Optional[str] = Query(None, description="Фильтр по типу пользователя"),
    search: Optional[str] = Query(None, description="Поиск по имени или IIN"),
    page: int = Query(1, ge=1, description="Номер страницы"),
    page_size: int = Query(20, ge=10, le=100, description="Размер страницы"),
    sort_by: str = Query("person_name", description="Поле для сортировки"),
    sort_order: str = Query("asc", description="Порядок: asc или desc"),
    service: AttendanceService = Depends(get_service),
):
    """
    Получить список персон факультета
    """
    # Проверить, что faculty_id валидный
    faculty_name = get_faculty_name(faculty_id)
    if not faculty_name:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Faculty with id '{faculty_id}' not found",
        )

    # Создать фильтр с faculty (пагинация внутри фильтра)
    filters = PersonFilter(
        person_type=person_type,
        search=search,
        faculty=faculty_name,  # Используем полное название
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
    )

    return await service.get_unique_persons(filters)


@router.get(
    "/{faculty_id}/attendance",
    response_model=AttendanceListResponse,
    summary="Получить записи посещаемости факультета",
    description="""
    Получить записи посещаемости для конкретного факультета.

    **URL параметры:**
    - `faculty_id`: Slug факультета

    **Query параметры:**
    - `date_from`: Начало периода (YYYY-MM-DD)
    - `date_to`: Конец периода (YYYY-MM-DD)
    - `person_type`: Фильтр по типу пользователя
    - `direction`: Фильтр по направлению (entry/exit)
    - `search`: Поиск по имени или IIN
    - `page`: Номер страницы
    - `page_size`: Размер страницы (10-100)
    - `sort_by`: Поле для сортировки
    - `sort_order`: Порядок сортировки (asc, desc)
    """,
)
async def get_faculty_attendance(
    faculty_id: str,
    date_from: Optional[str] = Query(None, description="Начало периода (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="Конец периода (YYYY-MM-DD)"),
    person_type: Optional[str] = Query(None, description="Фильтр по типу пользователя"),
    direction: Optional[str] = Query(None, description="Направление: entry или exit"),
    search: Optional[str] = Query(None, description="Поиск по имени или IIN"),
    page: int = Query(1, ge=1, description="Номер страницы"),
    page_size: int = Query(20, ge=10, le=100, description="Размер страницы"),
    sort_by: str = Query("access_datetime", description="Поле для сортировки"),
    sort_order: str = Query("desc", description="Порядок: asc или desc"),
    service: AttendanceService = Depends(get_service),
):
    """
    Получить записи посещаемости факультета
    """
    # Проверить, что faculty_id валидный
    faculty_name = get_faculty_name(faculty_id)
    if not faculty_name:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Faculty with id '{faculty_id}' not found",
        )

    # Создать фильтр с faculty (пагинация внутри фильтра)
    filters = AttendanceFilter(
        date_from=date_from,
        date_to=date_to,
        person_type=person_type,
        direction=direction,
        search=search,
        faculty=faculty_name,  # Используем полное название
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
    )

    return await service.get_list(filters)


@router.get(
    "/departments/list",
    response_model=DepartmentListResponse,
    summary="Получить список подразделений",
    description="""
    Получить список подразделений для записей, не принадлежащих к факультетам.

    Подразделения автоматически категоризируются:
    - `college`: Колледжи
    - `marine`: Морская академия
    - `administrative`: Административные подразделения
    - `other`: Прочие

    **Кэширование:** 24 часа
    """,
)
async def get_departments(
    service: AttendanceService = Depends(get_service),
):
    """
    Получить список подразделений (для записей без факультета)
    """
    return await service.get_departments()
