"""HTTP security: admin bearer auth, rate limits, body-size cap, security headers, request ids, safe errors.

* Admin routes require `Authorization: Bearer <ADMIN_TOKEN>` compared in constant time. No token configured
  ⇒ every admin request is refused (fail closed).
* Token-bucket rate limits per client IP, tighter for quotes and LLM-backed routes; 429 + Retry-After.
* 64 KB request-body cap; strict CSP (self only, no inline script); nosniff, no-referrer, DENY framing.
* Errors are {error_code, message, request_id}; details go to the server log only.
"""
from __future__ import annotations

import hmac
import logging
import secrets
import threading
import time
from collections import defaultdict

from fastapi import Header, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import get_settings
from app.services.errors import AppError

log = logging.getLogger("pixelminds")
MAX_BODY_BYTES = 64 * 1024

CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
       "font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'; object-src 'none'")
SECURITY_HEADERS = {
    "Content-Security-Policy": CSP,
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cache-Control": "no-store",
}


def require_admin(authorization: str | None = Header(default=None)) -> str:
    """FastAPI dependency. Returns the actor name for the audit log."""
    expected = get_settings().admin_token
    if not expected or len(expected) < 32:
        raise AppError("unauthorized", "admin access is not configured", 401)
    if not authorization or not authorization.startswith("Bearer "):
        raise AppError("unauthorized", "missing bearer token", 401)
    given = authorization[len("Bearer "):].strip()
    if not hmac.compare_digest(given.encode("utf-8"), expected.encode("utf-8")):
        raise AppError("unauthorized", "invalid token", 401)
    return "revenue_manager"


class TokenBucket:
    def __init__(self, rate_per_min: float, burst: int):
        self.rate = rate_per_min / 60.0
        self.burst = burst
        self.state: dict[str, tuple[float, float]] = defaultdict(lambda: (float(burst), time.monotonic()))
        self.lock = threading.Lock()

    def take(self, key: str) -> float:
        """Returns 0 if allowed, else seconds to wait."""
        with self.lock:
            tokens, last = self.state[key]
            now = time.monotonic()
            tokens = min(self.burst, tokens + (now - last) * self.rate)
            if tokens >= 1:
                self.state[key] = (tokens - 1, now)
                return 0.0
            self.state[key] = (tokens, now)
            return (1 - tokens) / self.rate


LIMITS = {
    "quote": TokenBucket(rate_per_min=60, burst=20),
    "llm": TokenBucket(rate_per_min=12, burst=4),
    "admin": TokenBucket(rate_per_min=240, burst=60),
    "default": TokenBucket(rate_per_min=300, burst=100),
}


def bucket_for(path: str) -> str:
    if path.startswith("/v1/quote"):
        return "quote"
    if path.startswith(("/v1/whatif", "/v1/event-signals/extract", "/v1/narrate")):
        return "llm"
    if path.startswith("/v1/") and not path.startswith(("/v1/health", "/v1/catalog")):
        return "admin"
    return "default"


class SecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        rid = secrets.token_hex(8)
        request.state.request_id = rid
        client = request.client.host if request.client else "unknown"
        wait = LIMITS[bucket_for(request.url.path)].take(f"{bucket_for(request.url.path)}:{client}")
        if wait > 0:
            resp = JSONResponse({"error_code": "rate_limited", "message": "too many requests", "request_id": rid}, 429)
            resp.headers["Retry-After"] = str(int(wait) + 1)
        else:
            try:
                resp = await call_next(request)
            except Exception:  # noqa: BLE001 - never leak internals
                log.exception("unhandled error request_id=%s path=%s", rid, request.url.path)
                resp = JSONResponse({"error_code": "internal_error", "message": "something went wrong",
                                     "request_id": rid}, 500)
        for k, v in SECURITY_HEADERS.items():
            resp.headers.setdefault(k, v)
        resp.headers["X-Request-ID"] = rid
        return resp


class BodyLimitMiddleware:
    """Pure ASGI middleware: rejects bodies over MAX_BODY_BYTES even without a Content-Length header."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers") or [])
        cl = headers.get(b"content-length")
        if cl is not None and (not cl.isdigit() or int(cl) > MAX_BODY_BYTES):
            await _too_large(send)
            return
        seen = 0

        async def limited() -> Message:
            nonlocal seen
            msg = await receive()
            if msg["type"] == "http.request":
                seen += len(msg.get("body", b""))
                if seen > MAX_BODY_BYTES:
                    raise _BodyTooLarge()
            return msg

        try:
            await self.app(scope, limited, send)
        except _BodyTooLarge:
            await _too_large(send)


class _BodyTooLarge(Exception):
    pass


async def _too_large(send: Send) -> None:
    body = b'{"error_code":"payload_too_large","message":"request body exceeds 64 KB"}'
    await send({"type": "http.response.start", "status": 413,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
    await send({"type": "http.response.body", "body": body})


def app_error_response(request: Request, exc: AppError) -> JSONResponse:
    rid = getattr(request.state, "request_id", None)
    if exc.status >= 500:
        log.error("app error %s request_id=%s", exc.error_code, rid)
    return JSONResponse({"error_code": exc.error_code, "message": exc.message, "request_id": rid}, exc.status)
