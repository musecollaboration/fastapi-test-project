# middleware.py
import time
from uuid import uuid4

from fastapi import HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from logger import get_logger

logger = get_logger(__name__)


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Получаем или генерируем request_id
        request_id = request.headers.get("X-Request-ID") or str(uuid4())

        # Привязываем request_id к контексту structlog
        import structlog
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        # Логируем начало запроса (опционально)
        start_time = time.time()

        response = await call_next(request)

        # Логируем окончание запроса
        duration = time.time() - start_time
        logger.info(
            "Request processed",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=round(duration * 1000, 2),
        )

        # Добавляем request_id в заголовок ответа
        response.headers["X-Request-ID"] = request_id
        return response


class LimitRequestBodyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_size: int = 10 * 1024 * 1024):
        super().__init__(app)
        self.max_size = max_size

    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > self.max_size:
            raise HTTPException(status_code=413, detail="Payload Too Large")
        return await call_next(request)
