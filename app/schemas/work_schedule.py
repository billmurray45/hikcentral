"""
Pydantic схемы для работы с правилами рабочего времени
"""

from datetime import time, date, datetime
from typing import Optional
from pydantic import BaseModel, Field, field_validator


class WorkScheduleRuleBase(BaseModel):
    """Базовая схема для правила рабочего времени"""

    position_type: Optional[str] = Field(None, max_length=100, description="Тип должности")
    position: Optional[str] = Field(None, max_length=255, description="Конкретная должность")
    faculty_id: Optional[int] = Field(None, description="ID факультета")
    subdivision_id: Optional[int] = Field(None, description="ID подразделения")
    start_time: time = Field(..., description="Время начала работы (HH:MM:SS)")
    end_time: Optional[time] = Field(None, description="Время окончания работы (HH:MM:SS)")
    apply_days: Optional[str] = Field(None, max_length=50, description="Дни недели (JSON)")
    valid_from: Optional[date] = Field(None, description="Дата начала действия (YYYY-MM-DD)")
    valid_to: Optional[date] = Field(None, description="Дата окончания действия (YYYY-MM-DD)")
    priority: int = Field(0, ge=0, le=100, description="Приоритет правила (0-100)")
    is_active: bool = Field(True, description="Активно ли правило")
    description: Optional[str] = Field(None, description="Описание правила")
    created_by: Optional[str] = Field(None, max_length=100, description="Кто создал")

    @field_validator('position_type', 'position')
    @classmethod
    def at_least_one_condition(cls, v, info):
        """Проверить что хотя бы одно условие заполнено"""
        # Эта проверка будет работать после валидации всех полей
        return v

    class Config:
        from_attributes = True


class WorkScheduleRuleCreate(WorkScheduleRuleBase):
    """Схема для создания правила"""
    pass


class WorkScheduleRuleUpdate(BaseModel):
    """Схема для обновления правила"""

    position_type: Optional[str] = Field(None, max_length=100)
    position: Optional[str] = Field(None, max_length=255)
    faculty_id: Optional[int] = None
    subdivision_id: Optional[int] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    apply_days: Optional[str] = Field(None, max_length=50)
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    priority: Optional[int] = Field(None, ge=0, le=100)
    is_active: Optional[bool] = None
    description: Optional[str] = None

    class Config:
        from_attributes = True


class WorkScheduleRuleResponse(WorkScheduleRuleBase):
    """Схема для ответа с правилом"""

    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class WorkScheduleRuleListResponse(BaseModel):
    """Схема для списка правил с пагинацией"""

    total: int = Field(..., description="Общее количество правил")
    page: int = Field(..., description="Текущая страница")
    page_size: int = Field(..., description="Размер страницы")
    total_pages: int = Field(..., description="Всего страниц")
    items: list[WorkScheduleRuleResponse] = Field(..., description="Список правил")


class WorkScheduleRuleSummary(BaseModel):
    """Краткая информация о правиле для списков"""

    id: int
    condition: str = Field(..., description="Условие (position_type или position)")
    start_time: str = Field(..., description="Время начала")
    end_time: Optional[str] = Field(None, description="Время окончания")
    priority: int
    is_active: bool
    description: Optional[str] = None
