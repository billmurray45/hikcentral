"""
FastAPI Dependencies для Dependency Injection
"""

from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis

from app.core.database import async_session
from app.core.redis import get_redis
from app.services import AttendanceService


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency для получения database session

    Yields:
        AsyncSession
    """
    async with async_session() as session:
        yield session


async def get_redis_client() -> Redis:
    """
    Dependency для получения Redis client

    Returns:
        Redis client
    """
    return await get_redis()


async def get_attendance_service(
    db: AsyncSession = None, redis: Redis = None
) -> AttendanceService:
    """
    Dependency для получения AttendanceService

    Args:
        db: Database session (будет инжектирован FastAPI)
        redis: Redis client (будет инжектирован FastAPI)

    Returns:
        AttendanceService
    """
    if db is None:
        async with async_session() as session:
            if redis is None:
                redis = await get_redis()
            return AttendanceService(session, redis)
    else:
        if redis is None:
            redis = await get_redis()
        return AttendanceService(db, redis)
