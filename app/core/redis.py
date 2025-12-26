"""
Redis connection setup
"""

from typing import Optional
from redis.asyncio import Redis, ConnectionPool
from app.core.config import settings

# Глобальная переменная для Redis клиента
_redis_client: Optional[Redis] = None
_redis_pool: Optional[ConnectionPool] = None


async def get_redis() -> Redis:
    """
    Получить Redis клиент (singleton)

    Returns:
        Redis клиент
    """
    global _redis_client, _redis_pool

    if _redis_client is None:
        # Создать connection pool
        _redis_pool = ConnectionPool.from_url(
            settings.redis_url(),
            max_connections=settings.REDIS_POOL_SIZE,
            decode_responses=True,  # Автоматически декодировать bytes в str
        )

        # Создать клиент
        _redis_client = Redis(connection_pool=_redis_pool)

    return _redis_client


async def close_redis():
    """
    Закрыть Redis connection и pool
    """
    global _redis_client, _redis_pool

    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None

    if _redis_pool is not None:
        await _redis_pool.aclose()
        _redis_pool = None


async def ping_redis() -> bool:
    """
    Проверить соединение с Redis

    Returns:
        True если соединение работает, False в противном случае
    """
    try:
        redis = await get_redis()
        response = await redis.ping()
        return response is True
    except Exception:
        return False
