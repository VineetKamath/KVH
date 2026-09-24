"""FastAPI application. Production = ONE process on ONE port: the API under /v1 and the built UI at /.

    uvicorn app.main:app --app-dir backend/src --port 8000
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import admin, public
from app.api.security import BodyLimitMiddleware, SecurityMiddleware, app_error_response
from app.config import FRONTEND_DIST, get_settings
from app.core.clock import wall_now_iso
from app.db.conn import connect
from app.services.errors import AppError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("pixelminds")


def _startup_recovery() -> None:
    """A cycle left 'running' by a crash is marked failed (its transaction never committed); stale holds released."""
    settings = get_settings()
    if not settings.db_path.exists():
        log.error("database missing at %s: run `python -m scripts.seed`", settings.db_path)
        return
    conn = connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("UPDATE dp_cycle SET status = 'failed', updated_at = ? WHERE status = 'running'", (wall_now_iso(),))
        conn.execute("COMMIT")
        from app.services.quotes import expire_stale

        expire_stale(conn)
        if not settings.admin_token or len(settings.admin_token) < 32:
            log.warning("ADMIN_TOKEN not configured: admin console is locked (fail closed)")
    finally:
        conn.close()


def _scheduler():
    minutes = get_settings().auto_reprice_minutes
    if minutes <= 0:
        return None
    from apscheduler.schedulers.background import BackgroundScheduler

    from app.services import control

    def job():
        conn = connect()
        try:
            control.reprice(conn, "scheduler", "scheduled micro-batch reprice")
        except Exception:  # noqa: BLE001
            log.exception("scheduled reprice failed")
        finally:
            conn.close()

    s = BackgroundScheduler(daemon=True)
    s.add_job(job, "interval", minutes=minutes, max_instances=1, coalesce=True)
    s.start()
    return s


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _startup_recovery()
    sched = _scheduler()
    yield
    if sched is not None:
        sched.shutdown(wait=False)


app = FastAPI(title="PixelMinds Dynamic Pricing", version="1.0.0", lifespan=lifespan,
              docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(SecurityMiddleware)
settings = get_settings()
if settings.web_origin:
    app.add_middleware(CORSMiddleware, allow_origins=[settings.web_origin], allow_credentials=False,
                       allow_methods=["GET", "POST", "PUT"], allow_headers=["Authorization", "Content-Type"], max_age=600)
app.add_middleware(BodyLimitMiddleware)


@app.exception_handler(AppError)
async def _app_error(request: Request, exc: AppError):
    return app_error_response(request, exc)


@app.exception_handler(RequestValidationError)
async def _validation(request: Request, exc: RequestValidationError):
    fields = sorted({".".join(str(x) for x in e.get("loc", [])[1:]) or "body" for e in exc.errors()})
    return JSONResponse({"error_code": "invalid_request", "message": "request failed validation",
                         "fields": fields[:10], "request_id": getattr(request.state, "request_id", None)}, 422)


@app.exception_handler(StarletteHTTPException)
async def _http(request: Request, exc: StarletteHTTPException):
    code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
    return JSONResponse({"error_code": code, "message": str(exc.detail) if exc.status_code < 500 else "error",
                         "request_id": getattr(request.state, "request_id", None)}, exc.status_code)


app.include_router(public)
app.include_router(admin)

# ---- the built UI (single origin in production). Only files under frontend/dist are ever served. ----
DIST = Path(FRONTEND_DIST).resolve()


@app.get("/{path:path}", include_in_schema=False)
async def spa(path: str):
    if path.startswith("v1/") or path == "v1":
        return JSONResponse({"error_code": "not_found", "message": "unknown API route"}, 404)
    if not DIST.exists():
        return JSONResponse({"error_code": "not_found", "message": "UI not built: cd frontend && npm run build"}, 404)
    candidate = (DIST / path).resolve()
    if path and candidate.is_file() and DIST in candidate.parents:
        headers = {"Cache-Control": "public, max-age=31536000, immutable"} if "/assets/" in f"/{path}" else {}
        return FileResponse(candidate, headers=headers)
    return FileResponse(DIST / "index.html")


def export_openapi() -> dict:
    from fastapi.openapi.utils import get_openapi

    return get_openapi(title=app.title, version=app.version, routes=app.routes)
