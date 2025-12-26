from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "HR Attendance API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # Database
    DB_USER: str
    DB_PASSWORD: str
    DB_NAME: str
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_RECYCLE: int = 1800
    DB_ECHO: bool = False

    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str | None = None
    REDIS_POOL_SIZE: int = 10

    # HikCentral API
    HIKVISION_BASE_URL: str = ""
    HIKVISION_USERNAME: str = ""
    HIKVISION_PASSWORD: str = ""
    HIKVISION_TIMEOUT: int = 30
    HIKVISION_MAX_RETRIES: int = 3
    HIKVISION_PAGE_SIZE: int = 500
    HIKVISION_VERIFY_SSL: bool = True

    # Sync Settings
    SYNC_INTERVAL_MINUTES: int = 15
    SYNC_BATCH_SIZE: int = 500
    SYNC_PARALLEL_REQUESTS: int = 3
    SYNC_FULL_SYNC_HOUR: int = 2  # 2:00 AM
    SYNC_PERSON_SYNC_HOUR: int = 3  # 3:00 AM
    SYNC_RETENTION_DAYS: int = 365  # Хранить данные 1 год

    # Cache TTL (seconds)
    CACHE_DAILY_TTL: int = 300  # 5 минут
    CACHE_EMPLOYEE_TTL: int = 900  # 15 минут
    CACHE_SUMMARY_TTL: int = 600  # 10 минут
    CACHE_PERSONS_TTL: int = 86400  # 24 часа

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: list[str] = ["*"]
    CORS_ALLOW_HEADERS: list[str] = ["*"]

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    def db_url(self, async_mode: bool = True) -> str:
        driver = "postgresql+asyncpg" if async_mode else "postgresql+psycopg2"
        return f"{driver}://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    def redis_url(self) -> str:
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"


settings = Settings()
