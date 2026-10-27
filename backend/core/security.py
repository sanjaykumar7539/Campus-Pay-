"""Security primitives: token issue/verify, password/PIN hashing, RBAC dependencies.

No business rules live here. Whether a *user account is still valid* is decided
by the Authentication module and injected through ``app.state.principal_validator``
so that `core` never imports a business module.
"""
from __future__ import annotations

import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

import bcrypt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import jwt
from jwt import InvalidTokenError
from sqlalchemy.orm import Session

from core.config import get_settings
from core.errors import ForbiddenError, UnauthorizedError
from core.tenancy import Principal, bind_session_to_tenant

ALGORITHM = "HS256"
_bearer = HTTPBearer(auto_error=False)


# -- hashing ---------------------------------------------------------------

def _bcrypt_rounds() -> int:
    # Cost factor is configuration (tests lower it for speed; production keeps the default).
    return max(4, min(15, int(os.getenv("CAMPUSPAY_BCRYPT_ROUNDS", "12"))))


def hash_secret(secret: str, *, pepper: Optional[str] = None) -> str:
    """Slow salted hash (bcrypt). An optional server-side pepper is HMAC-mixed first."""
    material = _pepper(secret, pepper)
    return bcrypt.hashpw(material, bcrypt.gensalt(rounds=_bcrypt_rounds())).decode("ascii")


def verify_secret(secret: str, hashed: str, *, pepper: Optional[str] = None) -> bool:
    if not pepper and len(secret.encode("utf-8")) > 72:
        return False
    try:
        return bcrypt.checkpw(_pepper(secret, pepper), hashed.encode("ascii"))
    except ValueError:  # malformed hash
        return False


def _pepper(secret: str, pepper: Optional[str]) -> bytes:
    raw = secret.encode("utf-8")
    if pepper:
        # HMAC keeps the bcrypt input at a fixed length (bcrypt truncates at 72 bytes).
        return hmac.new(pepper.encode("utf-8"), raw, hashlib.sha256).hexdigest().encode("ascii")
    return raw


# -- tokens ----------------------------------------------------------------

def create_access_token(principal: Principal) -> str:
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_minutes)
    claims = {
        "sub": principal.user_id,
        "inst": principal.institution_id,
        "role": principal.role,
        "usr": principal.username,
        "ver": principal.token_version,
        "exp": expire,
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm=ALGORITHM)


def decode_access_token(token: str) -> Principal:
    try:
        payload = jwt.decode(token, get_settings().jwt_secret, algorithms=[ALGORITHM],
                             options={"require": ["exp", "sub", "inst", "role", "ver"]})
        return Principal(
            user_id=payload["sub"],
            institution_id=payload["inst"],
            role=payload["role"],
            username=payload.get("usr", ""),
            token_version=payload.get("ver", 0),
        )
    except (InvalidTokenError, KeyError, TypeError) as exc:
        raise UnauthorizedError("Could not validate credentials", code="INVALID_TOKEN") from exc


# -- FastAPI dependencies ----------------------------------------------------

def get_db(request: Request):
    """Yield a request-scoped session. The session factory lives on ``app.state``."""
    db: Session = request.app.state.session_factory()
    try:
        yield db
    finally:
        db.close()


PrincipalValidator = Callable[[Session, Principal], None]


def get_principal(
    request: Request,
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    db: Session = Depends(get_db),
) -> Principal:
    if creds is None:
        raise UnauthorizedError("Authentication required", code="AUTH_REQUIRED")
    principal = decode_access_token(creds.credentials)
    validator: Optional[PrincipalValidator] = getattr(request.app.state, "principal_validator", None)
    if validator is not None:
        validator(db, principal)
    return principal


def tenant_db(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)) -> Session:
    """Session bound to the principal's tenant (backstop tenant filter active)."""
    return bind_session_to_tenant(db, principal.institution_id)


def require_roles(*roles: str):
    allowed = frozenset(roles)

    def checker(principal: Principal = Depends(get_principal)) -> Principal:
        if principal.role not in allowed:
            raise ForbiddenError("Insufficient role for this operation", code="ROLE_NOT_PERMITTED")
        return principal

    return checker
