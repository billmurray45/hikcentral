"""
API v1 Router
"""

from fastapi import APIRouter
from .attendance import router as attendance_router
from .persons import router as persons_router

# Создать главный роутер для v1
api_v1_router = APIRouter(prefix="/v1")

# Подключить роутеры
api_v1_router.include_router(attendance_router)
api_v1_router.include_router(persons_router)

__all__ = ["api_v1_router"]
