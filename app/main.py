from contextlib import asynccontextmanager
import asyncio
import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings
from app.core.redis import close_redis, ping_redis
from app.core.database import engine
from app.api import api_v1_router

logger = logging.getLogger(__name__)


class CancelledRequestMiddleware(BaseHTTPMiddleware):
    """
    Middleware для обработки отмененных запросов (CancelledError)
    Предотвращает логирование ошибок, когда клиент отменяет запрос
    """

    async def dispatch(self, request: Request, call_next):
        try:
            response = await call_next(request)
            return response
        except asyncio.CancelledError:
            # Клиент отменил запрос (закрыл страницу, таймаут на фронте и т.д.)
            logger.info(f"Request cancelled by client: {request.method} {request.url.path}")
            return JSONResponse(
                status_code=499,  # Nginx Client Closed Request
                content={"detail": "Request cancelled by client"},
            )
        except Exception as e:
            # Остальные ошибки обрабатываются стандартным образом
            logger.error(f"Unhandled error in {request.method} {request.url.path}: {e}")
            raise


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan events для FastAPI приложения
    """
    # Startup
    print("=" * 80)
    print(f"🚀 Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    print("=" * 80)

    # Проверка Redis
    redis_ok = await ping_redis()
    if redis_ok:
        print("✅ Redis: Connected")
    else:
        print("⚠️  Redis: Not available (caching disabled)")

    # Проверка Database
    try:
        async with engine.connect() as conn:
            await conn.execute("SELECT 1")
        print("✅ Database: Connected")
    except Exception as e:
        print(f"❌ Database: Connection failed - {e}")

    print("=" * 80)

    yield

    # Shutdown
    print("\n" + "=" * 80)
    print("🛑 Shutting down...")
    print("=" * 80)

    # Закрыть Redis
    await close_redis()
    print("✅ Redis: Closed")

    # Закрыть Database
    await engine.dispose()
    print("✅ Database: Closed")

    print("=" * 80)


# Создать FastAPI приложение
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="""
    # HR Attendance API

    REST API для работы с данными посещаемости из HikCentral и Platonus.

    ## Основные возможности

    ###  Employees (Сотрудники)
    - Список сотрудников из Platonus
    - Посещаемость сотрудников за день
    - Опоздавшие сотрудники
    - Статистика опозданий за период
    - Справочники факультетов и подразделений

    ## Источники данных

    - **HikCentral**: Данные о проходах через турникеты
    - **Platonus**: Данные о сотрудниках (должности, факультеты, подразделения)
    """,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# Middleware для обработки отмененных запросов
app.add_middleware(CancelledRequestMiddleware)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=settings.CORS_ALLOW_METHODS,
    allow_headers=settings.CORS_ALLOW_HEADERS,
)

# Подключить API роутеры
app.include_router(api_v1_router, prefix="/api")


# Health check endpoint
@app.get(
    "/health",
    tags=["Health"],
    summary="Health Check",
    description="Проверка работоспособности API и подключений к БД и Redis",
)
async def health_check():
    """Health check endpoint"""
    # Проверка Redis
    redis_status = "ok" if await ping_redis() else "unavailable"

    # Проверка Database
    db_status = "ok"
    try:
        async with engine.connect() as conn:
            await conn.execute("SELECT 1")
    except Exception:
        db_status = "error"

    return JSONResponse(
        content={
            "status": "healthy" if db_status == "ok" else "degraded",
            "database": db_status,
            "redis": redis_status,
            "version": settings.APP_VERSION,
        }
    )


# Root endpoint
@app.get("/", tags=["Root"], summary="API Root", description="API информация")
async def root():
    """Root endpoint"""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "redoc": "/redoc",
        "openapi": "/openapi.json",
        "health": "/health",
        "api": {
            "v1": {
                "employees": "/api/v1/employees",
            }
        },
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
