"""
Request ID Middleware для трейсинга запросов
"""

import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from contextvars import ContextVar

# ContextVar для хранения request_id в текущем контексте
request_id_var: ContextVar[str] = ContextVar("request_id", default=None)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Middleware для добавления уникального Request ID к каждому запросу

    Проверяет наличие X-Request-ID в headers, если нет - генерирует новый UUID.
    Добавляет X-Request-ID в response headers.
    Сохраняет в ContextVar для использования в логах.
    """

    async def dispatch(self, request: Request, call_next):
        # Получить или создать request ID
        request_id = request.headers.get("X-Request-ID")

        if not request_id:
            request_id = str(uuid.uuid4())

        # Сохранить в ContextVar
        request_id_var.set(request_id)

        # Сохранить в request state для доступа в handlers
        request.state.request_id = request_id

        # Обработать запрос
        response: Response = await call_next(request)

        # Добавить request ID в response headers
        response.headers["X-Request-ID"] = request_id

        return response


def get_request_id() -> str | None:
    """
    Получить текущий request ID из context

    Returns:
        Request ID или None
    """
    return request_id_var.get()
