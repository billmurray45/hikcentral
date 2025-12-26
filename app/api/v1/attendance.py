"""
API endpoints для работы с attendance records
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis

from app.api.dependencies import get_db, get_redis_client
from app.services import AttendanceService
from app.schemas import (
    AttendanceFilter,
    AttendanceListResponse,
    AttendanceRecordResponse,
    AttendanceRecordShort,
    AttendanceStatsResponse,
    DailyAttendanceSummary,
)

router = APIRouter(prefix="/attendance", tags=["Attendance"])


def get_service(
    db: AsyncSession = Depends(get_db), redis: Redis = Depends(get_redis_client)
) -> AttendanceService:
    """Dependency для получения AttendanceService"""
    return AttendanceService(db, redis)


@router.get(
    "",
    response_model=AttendanceListResponse,
    summary="Получить список записей посещаемости",
    description="""
    Получить список attendance records с фильтрацией и пагинацией.

    **Фильтры:**
    - По дате: `date`, `date_from`, `date_to`
    - По времени: `time_from`, `time_to`
    - По типу: `person_type` (student_yu, student_yc, teacher, employee, bachelor, master)
    - По направлению: `direction` (Вход, Выход)
    - По персоне: `employee_id`, `iin`
    - Поиск: `search` (по имени, ИИН, карте)

    **Пагинация:**
    - `page` - номер страницы (default: 1)
    - `page_size` - размер страницы (default: 50, max: 500)

    **Сортировка:**
    - `sort_by` - поле для сортировки (default: id)
    - `sort_order` - порядок: asc или desc (default: desc)
    """,
)
async def get_attendance_list(
    # Фильтры по дате
    date: str | None = Query(None, description="Дата (YYYY-MM-DD)"),
    date_from: str | None = Query(None, description="Дата от (YYYY-MM-DD)"),
    date_to: str | None = Query(None, description="Дата до (YYYY-MM-DD)"),
    # Фильтры по времени
    time_from: str | None = Query(None, description="Время от (HH:MM:SS)"),
    time_to: str | None = Query(None, description="Время до (HH:MM:SS)"),
    # Фильтры по типу
    person_type: str | None = Query(
        None, description="Тип: student_yu, student_yc, teacher, employee, bachelor, master"
    ),
    # Фильтры по направлению
    direction: str | None = Query(None, description="Направление: Вход или Выход"),
    # Фильтры по организации
    position: str | None = Query(None, description="Поиск по должности"),
    person_group: str | None = Query(None, description="Поиск по группе"),
    # Фильтр по конкретному человеку
    employee_id: str | None = Query(None, description="ID конкретного сотрудника"),
    iin: str | None = Query(None, description="ИИН"),
    # Поиск
    search: str | None = Query(None, description="Поиск по имени, ИИН, карте"),
    # Устройство
    device_name: str | None = Query(None, description="Название устройства"),
    # Пагинация
    page: int = Query(1, ge=1, description="Номер страницы"),
    page_size: int = Query(50, ge=1, le=500, description="Размер страницы"),
    # Сортировка
    sort_by: str = Query("id", description="Поле для сортировки"),
    sort_order: str = Query("desc", description="Порядок: asc или desc"),
    # Dependencies
    service: AttendanceService = Depends(get_service),
) -> AttendanceListResponse:
    """Получить список attendance records"""
    try:
        filters = AttendanceFilter(
            date=date,
            date_from=date_from,
            date_to=date_to,
            time_from=time_from,
            time_to=time_to,
            person_type=person_type,
            direction=direction,
            position=position,
            person_group=person_group,
            employee_id=employee_id,
            iin=iin,
            search=search,
            device_name=device_name,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        return await service.get_list(filters)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get(
    "/stats",
    response_model=AttendanceStatsResponse,
    summary="Получить статистику посещаемости",
    description="""
    Получить общую статистику по посещаемости.

    **Параметры:**
    - `date_from` - дата начала периода (опционально)
    - `date_to` - дата окончания периода (опционально)

    Если не указаны даты, возвращается статистика за все время.

    **Кэширование:** 5 минут
    """,
)
async def get_attendance_stats(
    date_from: str | None = Query(None, description="Дата начала (YYYY-MM-DD)"),
    date_to: str | None = Query(None, description="Дата окончания (YYYY-MM-DD)"),
    service: AttendanceService = Depends(get_service),
) -> AttendanceStatsResponse:
    """Получить статистику посещаемости"""
    try:
        return await service.get_stats(date_from=date_from, date_to=date_to)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get(
    "/daily-summary",
    response_model=DailyAttendanceSummary,
    summary="Получить дневную сводку",
    description="""
    Получить детальную сводку посещаемости за конкретный день.

    **Включает:**
    - Общее количество входов и выходов
    - Количество уникальных персон
    - Разбивка по типам (студенты YU, YC, преподаватели, сотрудники)
    - Час пик

    **Кэширование:** 5 минут
    """,
)
async def get_daily_summary(
    date: str = Query(..., description="Дата (YYYY-MM-DD)"),
    service: AttendanceService = Depends(get_service),
) -> DailyAttendanceSummary:
    """Получить дневную сводку"""
    try:
        return await service.get_daily_summary(date)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get(
    "/search",
    response_model=list[AttendanceRecordShort],
    summary="Быстрый поиск записей",
    description="""
    Быстрый поиск attendance records по имени, ИИН или employee_id.

    **Параметры:**
    - `q` - поисковый запрос
    - `limit` - максимальное количество результатов (default: 20)
    """,
)
async def search_attendance(
    q: str = Query(..., min_length=2, description="Поисковый запрос"),
    limit: int = Query(20, ge=1, le=100, description="Максимальное количество результатов"),
    service: AttendanceService = Depends(get_service),
) -> list[AttendanceRecordShort]:
    """Быстрый поиск записей"""
    try:
        return await service.search(q, limit=limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get(
    "/latest",
    response_model=list[AttendanceRecordShort],
    summary="Получить последние записи",
    description="""
    Получить последние attendance records (реального времени).

    **Параметры:**
    - `limit` - количество записей (default: 10, max: 100)
    """,
)
async def get_latest_attendance(
    limit: int = Query(10, ge=1, le=100, description="Количество записей"),
    service: AttendanceService = Depends(get_service),
) -> list[AttendanceRecordShort]:
    """Получить последние записи"""
    try:
        return await service.get_latest(limit=limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get(
    "/{record_id}",
    response_model=AttendanceRecordResponse,
    summary="Получить одну запись по ID",
    description="""
    Получить полную информацию о конкретной attendance record.

    **Включает:**
    - Все поля записи
    - Вычисленные поля (person_type, faculty, department, group_name)
    - Флаги is_entry, is_exit
    """,
)
async def get_attendance_by_id(
    record_id: int,
    service: AttendanceService = Depends(get_service),
) -> AttendanceRecordResponse:
    """Получить одну запись по ID"""
    try:
        return await service.get_by_id(record_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")
