"""
API endpoints для работы с персонами (уникальные пользователи)
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis

from app.api.dependencies import get_db, get_redis_client
from app.services import AttendanceService
from app.schemas import PersonFilter, PersonListResponse, PersonInfo, PersonHistoryResponse

router = APIRouter(prefix="/persons", tags=["Persons"])


def get_service(
    db: AsyncSession = Depends(get_db), redis: Redis = Depends(get_redis_client)
) -> AttendanceService:
    """Dependency для получения AttendanceService"""
    return AttendanceService(db, redis)


@router.get(
    "",
    response_model=PersonListResponse,
    summary="Получить список уникальных персон",
    description="""
    Получить список всех уникальных персон из attendance records.

    **Фильтры:**
    - `person_type` - тип пользователя (student_yu, student_yc, teacher, employee, etc.)
    - `position` - должность
    - `person_group` - группа
    - `search` - поиск по имени или ИИН

    **Пагинация:**
    - `page` - номер страницы (default: 1)
    - `page_size` - размер страницы (default: 50, max: 500)

    **Сортировка:**
    - `sort_by` - поле для сортировки (default: person_name)
    - `sort_order` - порядок: asc или desc (default: asc)

    **Кэширование:** 10 минут
    """,
)
async def get_persons_list(
    # Фильтры
    person_type: str | None = Query(None, description="Тип пользователя"),
    position: str | None = Query(None, description="Должность"),
    person_group: str | None = Query(None, description="Группа"),
    search: str | None = Query(None, description="Поиск по имени, ИИН"),
    # Пагинация
    page: int = Query(1, ge=1, description="Номер страницы"),
    page_size: int = Query(50, ge=1, le=500, description="Размер страницы"),
    # Сортировка
    sort_by: str = Query("person_name", description="Поле для сортировки"),
    sort_order: str = Query("asc", description="Порядок: asc или desc"),
    # Dependencies
    service: AttendanceService = Depends(get_service),
) -> PersonListResponse:
    """Получить список персон"""
    try:
        filters = PersonFilter(
            person_type=person_type,
            position=position,
            person_group=person_group,
            search=search,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        return await service.get_unique_persons(filters)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get(
    "/{employee_id}",
    response_model=PersonInfo,
    summary="Получить информацию о персоне",
    description="""
    Получить полную информацию о конкретной персоне по employee_id.

    **Включает:**
    - ФИО и личные данные
    - Тип (student_yu, student_yc, teacher, employee, etc.)
    - Должность и группа
    - Факультет, отдел, группа студента (если применимо)
    - Общее количество визитов
    - Дата последнего визита

    **Кэширование:** 15 минут
    """,
)
async def get_person_by_id(
    employee_id: str,
    service: AttendanceService = Depends(get_service),
) -> PersonInfo:
    """Получить информацию о персоне"""
    try:
        return await service.get_person_by_id(employee_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get(
    "/{employee_id}/history",
    response_model=PersonHistoryResponse,
    summary="Получить историю проходов персоны",
    description="""
    Получить историю всех проходов конкретной персоны с пагинацией.

    **Параметры:**
    - `page` - номер страницы (default: 1)
    - `page_size` - размер страницы (default: 50, max: 500)

    **Возвращает:**
    - Информацию о персоне
    - Список всех проходов (отсортировано по дате, сначала новые)
    - Общее количество записей
    - Информация о пагинации

    **Без кэша** - всегда актуальные данные
    """,
)
async def get_person_history(
    employee_id: str,
    page: int = Query(1, ge=1, description="Номер страницы"),
    page_size: int = Query(50, ge=1, le=500, description="Размер страницы"),
    service: AttendanceService = Depends(get_service),
) -> PersonHistoryResponse:
    """Получить историю персоны"""
    try:
        return await service.get_person_history(employee_id, page=page, page_size=page_size)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")
