"""
API endpoints для управления правилами рабочего времени
"""

from typing import Optional
from fastapi import APIRouter, Query, Depends, HTTPException
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas import (
    WorkScheduleRuleCreate,
    WorkScheduleRuleUpdate,
    WorkScheduleRuleResponse,
    WorkScheduleRuleListResponse,
)
from app.models import WorkScheduleRule
from app.api.dependencies import get_db

router = APIRouter(prefix="/work-schedule-rules", tags=["Work Schedule Rules"])


@router.get(
    "",
    response_model=WorkScheduleRuleListResponse,
    summary="Получить список правил рабочего времени",
    description="""
    Получить список всех правил рабочего времени с фильтрацией и пагинацией.

    **Фильтры:**
    - `is_active`: Только активные правила (true/false)
    - `position_type`: Фильтр по типу должности
    - `position`: Фильтр по конкретной должности
    - `faculty_id`: Фильтр по ID факультета
    - `subdivision_id`: Фильтр по ID подразделения
    - `search`: Поиск по описанию, типу или должности

    **Пагинация:**
    - `page`: Номер страницы (default: 1)
    - `page_size`: Размер страницы (default: 20, max: 100)

    **Сортировка:**
    - По приоритету (от высокого к низкому), затем по ID
    """,
)
async def get_work_schedule_rules(
    is_active: Optional[bool] = Query(None, description="Только активные"),
    position_type: Optional[str] = Query(None, description="Тип должности"),
    position: Optional[str] = Query(None, description="Конкретная должность"),
    faculty_id: Optional[int] = Query(None, description="ID факультета"),
    subdivision_id: Optional[int] = Query(None, description="ID подразделения"),
    search: Optional[str] = Query(None, description="Поиск"),
    page: int = Query(1, ge=1, description="Номер страницы"),
    page_size: int = Query(20, ge=1, le=100, description="Размер страницы"),
    db: AsyncSession = Depends(get_db),
):
    """
    Получить список правил рабочего времени
    """

    # Построить базовый запрос
    query = select(WorkScheduleRule)
    count_query = select(func.count()).select_from(WorkScheduleRule)

    # Применить фильтры
    if is_active is not None:
        query = query.where(WorkScheduleRule.is_active == is_active)
        count_query = count_query.where(WorkScheduleRule.is_active == is_active)

    if position_type:
        query = query.where(WorkScheduleRule.position_type == position_type)
        count_query = count_query.where(WorkScheduleRule.position_type == position_type)

    if position:
        query = query.where(WorkScheduleRule.position.ilike(f"%{position}%"))
        count_query = count_query.where(WorkScheduleRule.position.ilike(f"%{position}%"))

    if faculty_id is not None:
        query = query.where(WorkScheduleRule.faculty_id == faculty_id)
        count_query = count_query.where(WorkScheduleRule.faculty_id == faculty_id)

    if subdivision_id is not None:
        query = query.where(WorkScheduleRule.subdivision_id == subdivision_id)
        count_query = count_query.where(WorkScheduleRule.subdivision_id == subdivision_id)

    if search:
        search_pattern = f"%{search}%"
        search_filter = or_(
            WorkScheduleRule.description.ilike(search_pattern),
            WorkScheduleRule.position_type.ilike(search_pattern),
            WorkScheduleRule.position.ilike(search_pattern),
        )
        query = query.where(search_filter)
        count_query = count_query.where(search_filter)

    # Подсчитать общее количество
    total_count = await db.scalar(count_query)
    total_count = total_count or 0

    # Сортировка по приоритету (DESC) и ID
    query = query.order_by(WorkScheduleRule.priority.desc(), WorkScheduleRule.id)

    # Пагинация
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)

    # Выполнить запрос
    result = await db.execute(query)
    rules = result.scalars().all()

    # Преобразовать в схемы
    rules_response = [WorkScheduleRuleResponse.model_validate(rule) for rule in rules]

    # Вычислить количество страниц
    total_pages = (total_count + page_size - 1) // page_size

    return WorkScheduleRuleListResponse(
        total=total_count,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        items=rules_response,
    )


@router.get(
    "/{rule_id}",
    response_model=WorkScheduleRuleResponse,
    summary="Получить правило по ID",
    description="Получить конкретное правило рабочего времени по его ID",
)
async def get_work_schedule_rule(
    rule_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Получить правило по ID
    """
    query = select(WorkScheduleRule).where(WorkScheduleRule.id == rule_id)
    result = await db.execute(query)
    rule = result.scalar_one_or_none()

    if not rule:
        raise HTTPException(status_code=404, detail=f"Правило с ID {rule_id} не найдено")

    return WorkScheduleRuleResponse.model_validate(rule)


@router.post(
    "",
    response_model=WorkScheduleRuleResponse,
    status_code=201,
    summary="Создать новое правило",
    description="""
    Создать новое правило рабочего времени.

    **Обязательные поля:**
    - `start_time`: Время начала работы (HH:MM:SS)
    - Хотя бы одно из: `position_type` или `position`

    **Опциональные поля:**
    - `end_time`: Время окончания работы
    - `faculty_id`, `subdivision_id`: Дополнительные фильтры
    - `priority`: Приоритет правила (0-100, default: 0)
    - `is_active`: Активно ли правило (default: true)
    - `description`: Описание правила
    - `valid_from`, `valid_to`: Период действия
    - `apply_days`: Дни недели (JSON)
    """,
)
async def create_work_schedule_rule(
    rule: WorkScheduleRuleCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    Создать новое правило рабочего времени
    """

    # Проверить что хотя бы одно условие заполнено
    if not rule.position_type and not rule.position:
        raise HTTPException(
            status_code=400,
            detail="Необходимо указать хотя бы одно условие: position_type или position"
        )

    # Создать новое правило
    new_rule = WorkScheduleRule(**rule.model_dump())

    db.add(new_rule)
    await db.commit()
    await db.refresh(new_rule)

    return WorkScheduleRuleResponse.model_validate(new_rule)


@router.put(
    "/{rule_id}",
    response_model=WorkScheduleRuleResponse,
    summary="Обновить правило",
    description="""
    Обновить существующее правило рабочего времени.

    Все поля опциональные - обновляются только переданные поля.
    """,
)
async def update_work_schedule_rule(
    rule_id: int,
    rule_update: WorkScheduleRuleUpdate,
    db: AsyncSession = Depends(get_db),
):
    """
    Обновить правило рабочего времени
    """

    # Найти правило
    query = select(WorkScheduleRule).where(WorkScheduleRule.id == rule_id)
    result = await db.execute(query)
    existing_rule = result.scalar_one_or_none()

    if not existing_rule:
        raise HTTPException(status_code=404, detail=f"Правило с ID {rule_id} не найдено")

    # Обновить только переданные поля
    update_data = rule_update.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(existing_rule, field, value)

    await db.commit()
    await db.refresh(existing_rule)

    return WorkScheduleRuleResponse.model_validate(existing_rule)


@router.patch(
    "/{rule_id}/toggle",
    response_model=WorkScheduleRuleResponse,
    summary="Включить/выключить правило",
    description="Переключить статус активности правила (is_active)",
)
async def toggle_work_schedule_rule(
    rule_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Переключить активность правила
    """

    # Найти правило
    query = select(WorkScheduleRule).where(WorkScheduleRule.id == rule_id)
    result = await db.execute(query)
    rule = result.scalar_one_or_none()

    if not rule:
        raise HTTPException(status_code=404, detail=f"Правило с ID {rule_id} не найдено")

    # Переключить статус
    rule.is_active = not rule.is_active

    await db.commit()
    await db.refresh(rule)

    return WorkScheduleRuleResponse.model_validate(rule)


@router.delete(
    "/{rule_id}",
    status_code=204,
    summary="Удалить правило",
    description="""
    Удалить правило рабочего времени.

    **Внимание:** Удаление правила необратимо!
    Рекомендуется вместо удаления использовать деактивацию (PATCH /{rule_id}/toggle).
    """,
)
async def delete_work_schedule_rule(
    rule_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Удалить правило рабочего времени
    """

    # Найти правило
    query = select(WorkScheduleRule).where(WorkScheduleRule.id == rule_id)
    result = await db.execute(query)
    rule = result.scalar_one_or_none()

    if not rule:
        raise HTTPException(status_code=404, detail=f"Правило с ID {rule_id} не найдено")

    # Удалить правило
    await db.delete(rule)
    await db.commit()

    return None


@router.get(
    "/active/summary",
    summary="Краткая сводка активных правил",
    description="""
    Получить краткую сводку всех активных правил для быстрого обзора.

    Возвращает упрощенный список без пагинации.
    """,
)
async def get_active_rules_summary(
    db: AsyncSession = Depends(get_db),
):
    """
    Получить краткую сводку активных правил
    """

    query = (
        select(WorkScheduleRule)
        .where(WorkScheduleRule.is_active == True)
        .order_by(WorkScheduleRule.priority.desc(), WorkScheduleRule.id)
    )

    result = await db.execute(query)
    rules = result.scalars().all()

    # Преобразовать в упрощенный формат
    summary = []
    for rule in rules:
        condition = rule.position_type or rule.position or "Unknown"
        summary.append({
            "id": rule.id,
            "condition": condition,
            "start_time": rule.start_time.strftime("%H:%M:%S") if rule.start_time else None,
            "end_time": rule.end_time.strftime("%H:%M:%S") if rule.end_time else None,
            "priority": rule.priority,
            "description": rule.description,
        })

    return {
        "total": len(summary),
        "rules": summary,
    }
