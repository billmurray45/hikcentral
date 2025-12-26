"""
Logging Middleware для логирования всех HTTP requests
"""

import time
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging_config import log_request, log_error
from .request_id import get_request_id


class LoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware для логирования всех HTTP requests/responses
    """

    async def dispatch(self, request: Request, call_next):
        # Начало обработки
        start_time = time.time()

        request_id = get_request_id()

        # Логировать incoming request
        # log_info(
        #     f"Incoming request: {request.method} {request.url.path}",
        #     correlation_id=request_id,
        #     http_method=request.method,
        #     http_path=str(request.url.path),
        #     http_query=str(request.url.query) if request.url.query else None,
        # )

        try:
            # Обработать запрос
            response: Response = await call_next(request)

            # Вычислить длительность
            duration_ms = (time.time() - start_time) * 1000

            # Логировать response
            log_request(
                method=request.method,
                path=str(request.url.path),
                status_code=response.status_code,
                duration_ms=duration_ms,
                correlation_id=request_id,
                query_params=str(request.url.query) if request.url.query else None,
            )

            return response

        except Exception as e:
            # Вычислить длительность
            duration_ms = (time.time() - start_time) * 1000

            # Логировать ошибку
            log_error(
                f"Request failed: {request.method} {request.url.path}",
                error=e,
                correlation_id=request_id,
                http_method=request.method,
                http_path=str(request.url.path),
                duration_ms=duration_ms,
            )

            # Пробросить ошибку дальше
            raise
