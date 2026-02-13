from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from .config import settings

DATABASE_URL = settings.db_url(async_mode=True)

engine = create_async_engine(
    DATABASE_URL,
    echo=settings.DB_ECHO and settings.DEBUG,  # echo only in debug mode
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_recycle=settings.DB_POOL_RECYCLE,
    pool_pre_ping=True,  # проверка живых connections
    pool_timeout=30,  # timeout для получения connection из pool
    connect_args={
        "timeout": 15,  # увеличен timeout для подключения к БД
        "command_timeout": 120,  # увеличен timeout для выполнения команд
        "server_settings": {
            "application_name": "hikcentral_api",  # идентификация в pg_stat_activity
        },
    },
)
async_session = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_session():
    async with async_session() as session:
        yield session
