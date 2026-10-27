"""Composition root: wires configuration, database, routers and error handling. No business logic."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

import app.models_registry  # noqa: F401  (register all models)
from core.config import get_settings
from core.database import make_engine, make_session_factory
from core.errors import DomainError, error_body, ok
from core.rate_limit import rate_limit_middleware
from app.admin_students_router import router as admin_students_router
from app.kiosk_router import router as kiosk_router
from app.management_router import router as management_router
from app.hardening import install as install_hardening
from modules.audit.router import router as audit_router
from modules.auth import service as auth_service
from modules.auth.router import router as auth_router
from modules.devices.router import router as devices_router
from modules.institutions.router import router as institutions_router
from modules.ledger.router import router as ledger_router
from modules.merchants.router import router as merchants_router
from modules.payments.router import router as payments_router
from modules.reports.router import router as reports_router
from modules.users.router import router as users_router
from modules.wallets.router import router as wallets_router

log = logging.getLogger("campuspay")
FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend" / "demo"


def create_app(database_url: Optional[str] = None) -> FastAPI:
    settings = get_settings()
    engine = make_engine(database_url or settings.database_url)
    application = FastAPI(title="CampusPay API", version="0.2.0-p1",
                          description="Campus Financial Operating System — P1 campus-commerce slice")
    application.state.engine = engine
    install_hardening(application, settings)
    application.state.session_factory = make_session_factory(engine)
    application.state.principal_validator = auth_service.validate_principal
    application.middleware("http")(rate_limit_middleware)

    if settings.cors_origins:
        application.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins), allow_credentials=False,
                                   allow_methods=["*"], allow_headers=["*"])

    @application.exception_handler(DomainError)
    async def _domain(_: Request, exc: DomainError):
        return JSONResponse(status_code=exc.status_code, content=error_body(exc.code, exc.message, exc.details))

    @application.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        details = [{"field": ".".join(str(p) for p in e["loc"][1:]), "message": e["msg"]} for e in exc.errors()]
        return JSONResponse(status_code=422, content=error_body("VALIDATION_ERROR", "Request validation failed",
                                                                {"errors": details}))

    @application.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException):
        return JSONResponse(status_code=exc.status_code, content=error_body("HTTP_ERROR", str(exc.detail)))

    @application.get("/api/v1/health", tags=["system"])
    def health():
        version = None
        try:
            with engine.connect() as conn:
                version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        except Exception:  # schema not migrated
            pass
        s = get_settings()
        return ok({"status": "ok", "schema_revision": version,
                   "pin_lockout": "CONFIGURED" if s.pin_max_failed_attempts else "UNSET (MG-01 policy OPEN; failures counted, not locked)",
                   "legacy_manual_payment": "ENABLED (deprecated)" if s.legacy_manual_payment_enabled else "disabled",
                   "demo_funding": "ENABLED (demo only, not production recharge)" if s.demo_funding_enabled else "disabled"})

    @application.get("/api/v1/ready", tags=["system"])
    def ready():
        try:
            with engine.connect() as conn:
                revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
            if revision != "0007_android_printing":
                raise RuntimeError("Migration required")
            return ok({"ready": True})
        except Exception:
            return JSONResponse(status_code=503, content={"success": False, "error": {"code": "NOT_READY", "message": "Database or schema unavailable"}})

    from app.printing import router as printing_router
    for r in (printing_router, management_router, kiosk_router, auth_router, institutions_router, users_router, admin_students_router, wallets_router, merchants_router, payments_router,
              devices_router, reports_router, audit_router, ledger_router):
        application.include_router(r)

    if FRONTEND_DIR.is_dir():
        application.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="demo-frontend")
    return application


app = create_app()
