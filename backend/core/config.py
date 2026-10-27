"""Environment-driven configuration (Configuration over Customisation).

No secrets or business policy are hard-coded here. Values that correspond to
OPEN Management Guidance items (Campus Operating Model v0.2 §15) have NO
default: they are either unset (mechanism inactive / explicitly deferred) or
provided by the deployment.
"""
from __future__ import annotations

import logging
import os
import secrets
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger("campuspay.config")

_EPHEMERAL_JWT_SECRET: Optional[str] = None
_LOCAL_ENVIRONMENTS = {"local", "test", "demo"}


class ConfigurationError(RuntimeError):
    pass


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str) -> Optional[int]:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return None
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer") from exc
    if value <= 0:
        raise ConfigurationError(f"{name} must be a positive integer")
    return value


@dataclass(frozen=True)
class Settings:
    environment: str
    database_url: str
    jwt_secret: str
    access_token_minutes: int
    pin_pepper: Optional[str]
    # MG-01 (OPEN): failure threshold / lock duration. Both-or-neither.
    pin_max_failed_attempts: Optional[int]
    pin_lock_duration_seconds: Optional[int]
    # Deprecated MVP manual-amount payment path (off unless explicitly enabled).
    legacy_manual_payment_enabled: bool
    # Demo/seed wallet funding (NOT production recharge — MG-03 OPEN).
    demo_funding_enabled: bool
    # MG-08 (OPEN): who may change menu prices/availability. Provisional set.
    menu_manage_roles: frozenset[str]
    cors_origins: tuple[str, ...]


def _jwt_secret(environment: str) -> str:
    global _EPHEMERAL_JWT_SECRET
    secret = os.getenv("SECRET_KEY")
    if secret:
        return secret
    if environment not in _LOCAL_ENVIRONMENTS:
        raise ConfigurationError("SECRET_KEY must be set outside local/test/demo environments")
    if _EPHEMERAL_JWT_SECRET is None:
        _EPHEMERAL_JWT_SECRET = secrets.token_urlsafe(48)
        log.warning("SECRET_KEY not set: using an ephemeral per-process signing key (tokens die on restart)")
    return _EPHEMERAL_JWT_SECRET


def get_settings() -> Settings:
    environment = os.getenv("ENVIRONMENT", "local").strip().lower()
    max_attempts = _env_int("CAMPUSPAY_PIN_MAX_FAILED_ATTEMPTS")
    lock_seconds = _env_int("CAMPUSPAY_PIN_LOCK_DURATION_SECONDS")
    if (max_attempts is None) != (lock_seconds is None):
        raise ConfigurationError(
            "CAMPUSPAY_PIN_MAX_FAILED_ATTEMPTS and CAMPUSPAY_PIN_LOCK_DURATION_SECONDS "
            "must be configured together (MG-01 policy is OPEN; no default is assumed)"
        )
    roles = os.getenv("CAMPUSPAY_MENU_MANAGE_ROLES", "ADMIN,MERCHANT_STAFF")
    origins = os.getenv("CAMPUSPAY_CORS_ORIGINS", "")
    return Settings(
        environment=environment,
        database_url=os.getenv("DATABASE_URL", "sqlite:///./campuspay_demo.db"),
        jwt_secret=_jwt_secret(environment),
        access_token_minutes=int(os.getenv("CAMPUSPAY_ACCESS_TOKEN_MINUTES", "120")),
        pin_pepper=os.getenv("CAMPUSPAY_PIN_PEPPER") or None,
        pin_max_failed_attempts=max_attempts,
        pin_lock_duration_seconds=lock_seconds,
        legacy_manual_payment_enabled=_env_bool("CAMPUSPAY_LEGACY_MANUAL_PAYMENT"),
        demo_funding_enabled=_env_bool("CAMPUSPAY_DEMO_FUNDING"),
        menu_manage_roles=frozenset(r.strip().upper() for r in roles.split(",") if r.strip()),
        cors_origins=tuple(o.strip() for o in origins.split(",") if o.strip()),
    )
