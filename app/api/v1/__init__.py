"""
API v1 Router
"""

from fastapi import APIRouter
from .employees import router as employees_router
from .work_schedule import router as work_schedule_router
from .teacher_schedule import router as teacher_schedule_router

# Создать главный роутер для v1
api_v1_router = APIRouter(prefix="/v1")

# Подключить роутеры
api_v1_router.include_router(employees_router)
api_v1_router.include_router(work_schedule_router)
api_v1_router.include_router(teacher_schedule_router)

__all__ = ["api_v1_router"]
