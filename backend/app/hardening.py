"""HTTP policy and deployment checks. OS lockdown is configured separately."""
import os
import uuid
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware
from core.config import ConfigurationError
from core.errors import error_body


def install(application, settings):
    production = settings.environment not in ("local", "test", "demo")
    if production:
        if not settings.database_url.startswith("postgresql"):
            raise ConfigurationError("Production requires PostgreSQL; SQLite is for local evaluation only")
        if len(settings.jwt_secret) < 32 or settings.jwt_secret.lower().startswith(("change", "demo", "test", "replace", "your-")):
            raise ConfigurationError("Use a randomly generated SECRET_KEY of at least 32 characters")
        if settings.demo_funding_enabled or settings.legacy_manual_payment_enabled:
            raise ConfigurationError("Demo funding and legacy payments must be disabled in production")
        if os.getenv("CAMPUSPAY_PAYMENT_AUTH", "fingerprint") != "fingerprint":
            raise ConfigurationError("Production kiosk payments require fingerprint authorization")
        if int(os.getenv("CAMPUSPAY_BCRYPT_ROUNDS", "12")) < 12:
            raise ConfigurationError("Production password hashing requires bcrypt cost 12 or higher")
        hosts = [h.strip() for h in os.getenv("CAMPUSPAY_ALLOWED_HOSTS", "").split(",") if h.strip()]
        if not hosts or "*" in hosts:
            raise ConfigurationError("Set CAMPUSPAY_ALLOWED_HOSTS to the deployment hostnames")
        application.add_middleware(TrustedHostMiddleware, allowed_hosts=hosts)

    @application.middleware("http")
    async def security_headers(request, call_next):
        path = request.url.path
        if request.cookies.get("cp_kiosk") and (path == "/" or path.endswith(".html")) and path != "/kiosk.html":
            response = RedirectResponse("/kiosk.html", status_code=303)
        elif os.getenv("CAMPUSPAY_PAYMENT_AUTH", "fingerprint") != "pin" and (
            path in ("/api/v1/auth/student-login", "/api/v1/auth/payment-pin", "/api/v1/admin/students/reset-pin")):
            response = JSONResponse(status_code=403, content=error_body("FINGERPRINT_REQUIRED", "Use fingerprint enrollment and the dedicated kiosk"))
        else:
            response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["X-Request-Id"] = str(uuid.uuid4())
        response.headers["Cache-Control"] = "no-store"
        # Legacy admin markup still uses inline click handlers; kiosk scripts are external.
        script_policy = "'self'" if path == "/kiosk.html" else "'self' 'unsafe-inline'"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'self'; "
            "form-action 'self'; img-src 'self' data: https://upload.wikimedia.org https://thumb.wikimedia.org; style-src 'self' 'unsafe-inline'; script-src " + script_policy)
        if production:
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        return response
