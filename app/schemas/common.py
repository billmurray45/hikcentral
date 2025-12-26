"""
Общие Pydantic схемы для всего API
"""

from typing import Generic, TypeVar, Optional
from pydantic import BaseModel, Field


# Generic type для данных
T = TypeVar("T")


class PaginationParams(BaseModel):
    """Параметры пагинации"""

    page: int = Field(1, ge=1, description="Номер страницы")
    page_size: int = Field(50, ge=1, le=500, description="Размер страницы")


class PaginatedResponse(BaseModel, Generic[T]):
    """
    Универсальный ответ с пагинацией
    Можно использовать для любых моделей
    """

    total: int = Field(..., description="Общее количество записей")
    page: int = Field(..., description="Текущая страница")
    page_size: int = Field(..., description="Размер страницы")
    pages: int = Field(..., description="Всего страниц")
    items: list[T] = Field(default_factory=list, description="Список записей")


class SuccessResponse(BaseModel):
    """Успешный ответ"""

    success: bool = True
    message: str = "Operation completed successfully"


class ErrorResponse(BaseModel):
    """Ответ с ошибкой"""

    success: bool = False
    error: str
    detail: Optional[str] = None


class HealthCheckResponse(BaseModel):
    """Ответ healthcheck"""

    status: str = "healthy"
    database: str = "ok"
    redis: Optional[str] = None
    timestamp: str
