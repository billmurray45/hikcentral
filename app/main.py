"""
HR Attendance API - Main Application
FastAPI приложение для работы с attendance records
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.redis import close_redis, ping_redis
from app.core.database import engine
from app.api import api_v1_router


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

    REST API для работы с данными посещаемости из HikCentral.

    ## Основные возможности

    ###  Attendance (Посещаемость)
    - Получение списка записей с фильтрацией
    - Детальная информация о конкретной записи
    - Статистика по периодам
    - Дневная сводка с разбивкой по типам
    - Быстрый поиск
    - Последние записи (реального времени)

    ###  Persons (Персоны)
    - Список уникальных персон
    - Информация о конкретной персоне
    - История проходов персоны

    ## Фильтрация

    ### По типу пользователя
    - `student_yu` - Студенты Yessenov University
    - `student_yc` - Студенты Yessenov College
    - `bachelor` - Бакалавры
    - `master` - Магистранты
    - `teacher` - Преподаватели
    - `employee` - Сотрудники
    - `other` - Прочие

    ### По направлению
    - `Вход` - входы в здание
    - `Выход` - выходы из здания

    ## Кэширование

    Некоторые endpoints кэшируются в Redis для улучшения производительности:
    - Статистика: 5 минут
    - Дневная сводка: 5 минут
    - Список персон: 10 минут
    - Информация о персоне: 15 минут

    Список записей и история всегда актуальны (без кэша).
    """,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

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
                "attendance": "/api/v1/attendance",
                "persons": "/api/v1/persons",
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
