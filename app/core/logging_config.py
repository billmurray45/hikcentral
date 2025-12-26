"""
Structured Logging Configuration
"""

import logging
import sys
import json
from datetime import datetime
from typing import Any
from pythonjsonlogger import jsonlogger

from app.core.config import settings


class CustomJsonFormatter(jsonlogger.JsonFormatter):
    """
    Custom JSON formatter для structured logging
    """

    def add_fields(self, log_record: dict[str, Any], record: logging.LogRecord, message_dict: dict[str, Any]):
        super().add_fields(log_record, record, message_dict)

        # Добавить timestamp в ISO format
        log_record["timestamp"] = datetime.utcnow().isoformat() + "Z"

        # Добавить level name
        log_record["level"] = record.levelname

        # Добавить logger name
        log_record["logger"] = record.name

        # Добавить service info
        log_record["service"] = settings.APP_NAME
        log_record["version"] = settings.APP_VERSION

        # Добавить correlation_id если есть
        if hasattr(record, "correlation_id"):
            log_record["correlation_id"] = record.correlation_id

        # Добавить user_id если есть
        if hasattr(record, "user_id"):
            log_record["user_id"] = record.user_id


def setup_logging():
    """
    Настроить structured logging для приложения
    """
    # Создать root logger
    root_logger = logging.getLogger()

    # Очистить существующие handlers
    root_logger.handlers.clear()

    # Уровень логирования
    log_level = logging.DEBUG if settings.DEBUG else logging.INFO
    root_logger.setLevel(log_level)

    # Console handler с JSON форматом
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)

    # JSON formatter
    formatter = CustomJsonFormatter(
        "%(timestamp)s %(level)s %(logger)s %(message)s",
        rename_fields={
            "levelname": "level",
            "name": "logger",
        }
    )
    console_handler.setFormatter(formatter)

    root_logger.addHandler(console_handler)

    # Отключить uvicorn access logs (будем логировать через middleware)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    # Уменьшить verbosity для сторонних библиотек
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("asyncpg").setLevel(logging.WARNING)

    return root_logger


# Создать logger instance
logger = logging.getLogger("hr_attendance")


# Helper функции для structured logging
def log_error(
    message: str,
    error: Exception | None = None,
    correlation_id: str | None = None,
    **kwargs
):
    """
    Логировать ошибку с контекстом

    Args:
        message: Сообщение об ошибке
        error: Exception объект
        correlation_id: Request correlation ID
        **kwargs: Дополнительные поля
    """
    extra = kwargs.copy()

    if correlation_id:
        extra["correlation_id"] = correlation_id

    if error:
        extra["error_type"] = type(error).__name__
        extra["error_message"] = str(error)

        # Добавить traceback если есть
        if hasattr(error, "__traceback__"):
            import traceback
            extra["traceback"] = "".join(traceback.format_tb(error.__traceback__))

    logger.error(message, extra=extra, exc_info=error is not None)


def log_info(message: str, correlation_id: str | None = None, **kwargs):
    """
    Логировать информацию

    Args:
        message: Информационное сообщение
        correlation_id: Request correlation ID
        **kwargs: Дополнительные поля
    """
    extra = kwargs.copy()

    if correlation_id:
        extra["correlation_id"] = correlation_id

    logger.info(message, extra=extra)


def log_warning(message: str, correlation_id: str | None = None, **kwargs):
    """
    Логировать предупреждение

    Args:
        message: Сообщение-предупреждение
        correlation_id: Request correlation ID
        **kwargs: Дополнительные поля
    """
    extra = kwargs.copy()

    if correlation_id:
        extra["correlation_id"] = correlation_id

    logger.warning(message, extra=extra)


def log_request(
    method: str,
    path: str,
    status_code: int,
    duration_ms: float,
    correlation_id: str | None = None,
    **kwargs
):
    """
    Логировать HTTP request

    Args:
        method: HTTP метод
        path: URL path
        status_code: HTTP status code
        duration_ms: Длительность в миллисекундах
        correlation_id: Request correlation ID
        **kwargs: Дополнительные поля
    """
    extra = {
        "http_method": method,
        "http_path": path,
        "http_status": status_code,
        "duration_ms": round(duration_ms, 2),
        **kwargs
    }

    if correlation_id:
        extra["correlation_id"] = correlation_id

    # Логировать errors как ERROR, остальное как INFO
    if status_code >= 500:
        logger.error(f"{method} {path} {status_code} ({duration_ms:.2f}ms)", extra=extra)
    elif status_code >= 400:
        logger.warning(f"{method} {path} {status_code} ({duration_ms:.2f}ms)", extra=extra)
    else:
        logger.info(f"{method} {path} {status_code} ({duration_ms:.2f}ms)", extra=extra)
