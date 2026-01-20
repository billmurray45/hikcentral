"""
Employees API endpoints - получение списка сотрудников кто проходит турникет
Данные берутся из кеша platonus_employees (синхронизация раз в неделю)
"""

from typing import Optional
from fastapi import APIRouter, Query, Depends
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas import EmployeeBase, EmployeeListResponse
from app.models import PlatonusEmployee
from app.api.dependencies import get_db
from app.services.platonus_sync import PlatonusSyncService

router = APIRouter(prefix="/employees", tags=["Employees"])


@router.get(
    "",
    response_model=EmployeeListResponse,
    summary="Получить список сотрудников",
    description="""
    Получить список сотрудников которые проходят турникет.

    **Источник данных:**
    - Список IIN из HikCentral (attendance_records, person_type != 'student')
    - Данные обогащены из Platonus (должность, кафедра, факультет)
    - Данные кешируются в таблице platonus_employees
    - Синхронизация: раз в неделю

    **Параметры:**
    - `position_type`: Фильтр по типу должности (Преподаватель/Руководитель/Специалист/и т.д.)
    - `faculty_id`: Фильтр по ID факультета
    - `search`: Поиск по ФИО или IIN

    **Включает:**
    - ИИН
    - ФИО
    - Должность и тип должности
    - Кафедра и факультет
    - Контакты (email, телефон)
    """,
)
async def get_employees(
    position_type: Optional[str] = Query(None, description="Тип должности"),
    faculty_id: Optional[int] = Query(None, description="ID факультета"),
    search: Optional[str] = Query(None, description="Поиск по ФИО или IIN"),
    db: AsyncSession = Depends(get_db),
):
    """
    Получить список сотрудников из кеша
    """

    # Построить запрос
    query = select(PlatonusEmployee)

    # Фильтры
    if position_type:
        query = query.where(PlatonusEmployee.position_type == position_type)

    if faculty_id is not None:
        query = query.where(PlatonusEmployee.faculty_id == faculty_id)

    if search:
        search_pattern = f"%{search}%"
        query = query.where(
            or_(
                PlatonusEmployee.firstname.ilike(search_pattern),
                PlatonusEmployee.lastname.ilike(search_pattern),
                PlatonusEmployee.patronymic.ilike(search_pattern),
                PlatonusEmployee.iin.ilike(search_pattern),
            )
        )

    # Сортировка
    query = query.order_by(PlatonusEmployee.lastname, PlatonusEmployee.firstname)

    # Выполнить запрос
    result = await db.execute(query)
    employees_db = result.scalars().all()

    # Преобразовать в схемы
    employees = [
        EmployeeBase(
            tutor_id=emp.tutor_id,
            iin=emp.iin,
            firstname=emp.firstname,
            lastname=emp.lastname,
            patronymic=emp.patronymic,
            position=emp.position,
            position_type=emp.position_type,
            cafedra=emp.cafedra_name,
            faculty=emp.faculty_name,
            faculty_id=emp.faculty_id,
            email=emp.email,
            phone=emp.phone,
        )
        for emp in employees_db
    ]

    return EmployeeListResponse(total=len(employees), items=employees)


@router.post(
    "/sync",
    summary="Синхронизировать данные сотрудников",
    description="""
    Запустить синхронизацию данных сотрудников из Platonus.

    **Процесс:**
    1. Получить всех уникальных пользователей с IIN из HikCentral (не студентов)
    2. Для каждого IIN получить данные из Platonus (должность, кафедра, факультет)
    3. Сохранить/обновить в таблице platonus_employees

    **Примечание:** Обычно запускается автоматически раз в неделю
    """,
)
async def sync_employees(db: AsyncSession = Depends(get_db)):
    """
    Синхронизировать данные сотрудников из Platonus
    """
    service = PlatonusSyncService(db)
    result = await service.sync_employees()
    return result


@router.get(
    "/sync/stats",
    summary="Статистика синхронизации",
    description="""
    Получить статистику последней синхронизации.

    **Включает:**
    - Всего сотрудников в кеше
    - Дата последней синхронизации
    - Распределение по типам должностей
    - Распределение по факультетам
    """,
)
async def get_sync_stats(db: AsyncSession = Depends(get_db)):
    """
    Получить статистику синхронизации
    """
    service = PlatonusSyncService(db)
    stats = await service.get_sync_stats()
    return stats
