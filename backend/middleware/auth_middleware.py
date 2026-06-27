import asyncio
import time
from typing import Any, Callable, Dict, Optional
from urllib.parse import parse_qs

from fastapi import HTTPException, Request, status
from fastapi.security import HTTPBearer
from jose import JWTError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from config import settings
from utils.security import extract_bearer_token, get_client_ip, get_websocket_token, verify_jwt_token


class AuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, exempt_paths: Optional[tuple[str, ...]] = None, max_requests: int = 120, window_seconds: int = 60) -> None:
        super().__init__(app)
        self.exempt_paths = exempt_paths or (
            "/health",
            "/api/auth/token",
            "/api/auth/register",
            "/docs",
            "/openapi.json",
        )
        self.security = HTTPBearer(auto_error=False)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.rate_limits: Dict[str, Dict[str, Any]] = {}
        self.lock = asyncio.Lock()

    async def dispatch(self, request: StarletteRequest, call_next: Callable) -> Any:
        if self._is_exempt(request.url.path):
            return await call_next(request)

        token = extract_bearer_token(request.headers.get("authorization"))
        if not token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authorization token missing")

        try:
            payload = verify_jwt_token(token)
        except JWTError as error:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token") from error

        request.state.user = payload

        if await self._is_rate_limited(request):
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Rate limit exceeded")

        response = await call_next(request)
        return response

    def _is_exempt(self, path: str) -> bool:
        return any(path.startswith(route) for route in self.exempt_paths)

    async def _is_rate_limited(self, request: StarletteRequest) -> bool:
        key = f"{get_client_ip(request.scope)}:{request.url.path}"
        async with self.lock:
            entry = self.rate_limits.get(key)
            now = time.monotonic()
            if entry is None or entry["expires_at"] <= now:
                self.rate_limits[key] = {"count": 1, "expires_at": now + self.window_seconds}
                return False
            if entry["count"] >= self.max_requests:
                return True
            entry["count"] += 1
            return False


class WebSocketAuthMiddleware:
    def __init__(self, app: ASGIApp, exempt_paths: Optional[tuple[str, ...]] = None) -> None:
        self.app = app
        self.exempt_paths = exempt_paths or ("/api/ws/conversation",)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "websocket" or self._is_exempt(scope.get("path", "")):
            await self.app(scope, receive, send)
            return

        query_string = scope.get("query_string", b"").decode("utf-8")
        params = parse_qs(query_string)
        token = get_websocket_token(params)

        if not token:
            await self._close_websocket(send, code=status.WS_1008_POLICY_VIOLATION, reason="Missing websocket token")
            return

        try:
            verify_jwt_token(token)
        except JWTError:
            await self._close_websocket(send, code=status.WS_1008_POLICY_VIOLATION, reason="Invalid websocket token")
            return

        await self.app(scope, receive, send)

    def _is_exempt(self, path: str) -> bool:
        return any(path.startswith(route) for route in self.exempt_paths)

    @staticmethod
    async def _close_websocket(send: Send, code: int, reason: str) -> None:
        await send({"type": "websocket.close", "code": code, "reason": reason})
