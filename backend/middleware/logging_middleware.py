import logging
import time
from typing import Callable

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from starlette.types import ASGIApp

logger = logging.getLogger("backend.middleware.logging")


class LoggingMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.monotonic()
        user_identifier = getattr(getattr(request, "state", None), "user", None)
        user_repr = user_identifier.get("sub") if isinstance(user_identifier, dict) else None

        logger.info(
            "Incoming request %s %s user=%s ip=%s",
            request.method,
            request.url.path,
            user_repr,
            request.client.host if request.client else "unknown",
        )

        try:
            response = await call_next(request)
        except Exception as error:
            elapsed = round((time.monotonic() - start_time) * 1000, 2)
            logger.exception(
                "Unhandled exception for %s %s user=%s elapsed=%sms",
                request.method,
                request.url.path,
                user_repr,
                elapsed,
            )
            raise

        elapsed = round((time.monotonic() - start_time) * 1000, 2)
        logger.info(
            "Completed request %s %s status=%s elapsed=%sms user=%s",
            request.method,
            request.url.path,
            response.status_code,
            elapsed,
            user_repr,
        )
        response.headers["X-Process-Time-ms"] = str(elapsed)
        return response
