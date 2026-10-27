"""Authentication module — published interface.

Owns: login credentials and the payment-authorisation PIN credential.
Does NOT own customer identity (Campus User), wallets, payments or orders.
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from datetime import timedelta
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.config import get_settings
from core.demo_defaults import DEMO_PASSWORD
from core.errors import ConflictError, NotFoundError, UnauthorizedError, ValidationFailure
from core.security import create_access_token, hash_secret, verify_secret
from core.tenancy import Principal
from modules.audit import service as audit
from modules.auth.models import Credential, PaymentPinCredential
from modules.institutions import service as institutions
from modules.users import service as users
from shared.clock import utcnow

log = logging.getLogger("campuspay.auth")
_PIN_RE = re.compile(r"^\d{4}$")
_DUMMY_HASH = hash_secret("not-a-real-password")  # equalises timing for unknown usernames

PIN_OK, PIN_INVALID, PIN_LOCKED, PIN_NOT_SET = "OK", "INVALID", "LOCKED", "NOT_SET"


@dataclass(frozen=True)
class LoginResult:
    access_token: str
    user_id: str
    institution_id: str
    role: str
    username: str


@dataclass(frozen=True)
class PinCheck:
    status: str  # OK | INVALID | LOCKED | NOT_SET

    @property
    def ok(self) -> bool:
        return self.status == PIN_OK


def _bad_login() -> UnauthorizedError:
    return UnauthorizedError("Invalid credentials", code="INVALID_CREDENTIALS")


def login(db: Session, *, institution_code: str, username: str, password: str) -> LoginResult:
    if get_settings().environment not in ("local", "test", "demo") and password == DEMO_PASSWORD:
        raise UnauthorizedError("The public demo password is disabled in production. Change it in the local demo before deployment.", code="DEMO_PASSWORD_DISABLED")
    inst = institutions.find_by_code(db, institution_code)
    if inst is None or inst.status != "ACTIVE":
        verify_secret(password, _DUMMY_HASH)
        raise _bad_login()
    cred = db.execute(select(Credential).where(Credential.institution_id == inst.id,
                                               Credential.username == username.strip())).scalar_one_or_none()
    ok = verify_secret(password, cred.password_hash if cred else _DUMMY_HASH)
    if not cred or not ok or cred.status != "ACTIVE":
        audit.record_event(db, institution_id=inst.id, actor_id=username.strip()[:64], event_type="LOGIN_FAILED",
                           entity_type="Credential", entity_id=cred.id if cred else "unknown", result="FAILURE")
        db.commit()
        raise _bad_login()
    user = users.get_user(db, institution_id=inst.id, user_id=cred.campus_user_id)
    if user.status != users.ACTIVE:
        raise _bad_login()
    principal = Principal(user_id=user.id, institution_id=inst.id, role=user.role, username=cred.username,
                          token_version=cred.token_version)
    audit.record_event(db, institution_id=inst.id, actor_id=user.id, actor_role=user.role,
                       event_type="LOGIN_SUCCEEDED", entity_type="Credential", entity_id=cred.id)
    db.commit()
    return LoginResult(create_access_token(principal), user.id, inst.id, user.role, cred.username)


def student_login(db: Session, *, institution_code: str, campus_id: str) -> LoginResult:
    if os.getenv("CAMPUSPAY_PAYMENT_AUTH", "fingerprint") != "pin":
        raise UnauthorizedError("Use the staff-configured kiosk. Student ID login is disabled.", code="KIOSK_REQUIRED")
    inst = institutions.find_by_code(db, institution_code)
    if inst is None or inst.status != "ACTIVE":
        raise _bad_login()
    try:
        user = users.resolve_customer(db, institution_id=inst.id, signal=users.IdentitySignal("CAMPUS_ID", campus_id.strip()))
    except NotFoundError as exc:
        raise _bad_login() from exc
    if user.role != users.STUDENT or user.status != users.ACTIVE:
        raise _bad_login()
    principal = Principal(user_id=user.id, institution_id=inst.id, role=user.role, username=user.unique_identifier, token_version=0)
    audit.record_event(db, institution_id=inst.id, actor_id=user.id, actor_role=user.role,
                       event_type="STUDENT_SESSION_STARTED", entity_type="CampusUser", entity_id=user.id)
    db.commit()
    return LoginResult(create_access_token(principal), user.id, inst.id, user.role, user.unique_identifier)


def validate_principal(db: Session, principal: Principal) -> None:
    """Per-request validity check (installed as app.state.principal_validator)."""
    inst = institutions.get_institution(db, principal.institution_id) if _inst_exists(db, principal) else None
    if inst is None or inst.status != "ACTIVE":
        raise UnauthorizedError("Session no longer valid", code="SESSION_INVALID")
    try:
        user = users.get_user(db, institution_id=principal.institution_id, user_id=principal.user_id)
    except NotFoundError as exc:
        raise UnauthorizedError("Session no longer valid", code="SESSION_INVALID") from exc
    if user.status != users.ACTIVE or user.role != principal.role:
        raise UnauthorizedError("Session no longer valid", code="SESSION_INVALID")
    if principal.role == users.STUDENT and principal.username == user.unique_identifier and principal.token_version == 0:
        return
    cred = db.execute(select(Credential).where(
        Credential.institution_id == principal.institution_id,
        Credential.campus_user_id == principal.user_id)).scalar_one_or_none()
    if (cred is None or cred.status != "ACTIVE" or cred.username != principal.username
            or cred.token_version != principal.token_version):
        raise UnauthorizedError("Session no longer valid. Please sign in again.", code="SESSION_INVALID")


def update_own_credentials(db: Session, *, principal: Principal, current_password: str,
                           username: Optional[str] = None, new_password: Optional[str] = None) -> dict:
    """Change only the authenticated account, after verifying its current password.

    The version check also protects a request waiting for a concurrent change's lock.
    Secrets are never included in the audit metadata or returned to the caller.
    """
    cred = db.execute(select(Credential).where(
        Credential.institution_id == principal.institution_id,
        Credential.campus_user_id == principal.user_id).with_for_update()
        .execution_options(populate_existing=True)).scalar_one_or_none()
    if cred is None or cred.status != "ACTIVE" or cred.token_version != principal.token_version:
        raise UnauthorizedError("Session no longer valid. Please sign in again.", code="SESSION_INVALID")
    if not verify_secret(current_password, cred.password_hash):
        audit.record_event(db, institution_id=principal.institution_id, actor_id=principal.user_id,
                           actor_role=principal.role, event_type="CREDENTIAL_CHANGE_FAILED",
                           entity_type="Credential", entity_id=cred.id, result="FAILURE",
                           reason="current password did not match")
        db.commit()
        raise ValidationFailure("Current password is incorrect", code="CURRENT_PASSWORD_INVALID")
    target_username = cred.username if username is None else username.strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._@-]{2,127}", target_username):
        raise ValidationFailure("Login ID must be 3–128 characters: letters, numbers, dot, _, @ or -",
                                code="INVALID_USERNAME")
    if new_password is not None:
        if get_settings().environment not in ("local", "test", "demo") and new_password == DEMO_PASSWORD:
            raise ValidationFailure("The public demo password cannot be used in production", code="DEMO_PASSWORD_DISABLED")
        if len(new_password) < 8 or len(new_password.encode("utf-8")) > 72:
            raise ValidationFailure("New password must have at least 8 characters and at most 72 UTF-8 bytes",
                                    code="WEAK_PASSWORD")
        if verify_secret(new_password, cred.password_hash):
            raise ValidationFailure("Choose a password different from your current password", code="PASSWORD_UNCHANGED")
    username_changed = target_username != cred.username
    if not username_changed and new_password is None:
        raise ValidationFailure("Enter a new login ID or a new password", code="NO_CHANGES")
    try:
        with db.begin_nested():
            values = {"username": target_username, "token_version": Credential.token_version + 1}
            if new_password is not None:
                values["password_hash"] = hash_secret(new_password)
            changed = db.execute(update(Credential).where(
                Credential.id == cred.id, Credential.institution_id == principal.institution_id,
                Credential.token_version == principal.token_version).values(**values)
                .execution_options(synchronize_session=False))
            if changed.rowcount != 1:
                raise UnauthorizedError("Account changed in another session. Please sign in again.",
                                        code="SESSION_INVALID")
    except IntegrityError as exc:
        raise ConflictError("That login ID is already used in your institution", code="USERNAME_TAKEN") from exc
    audit.record_event(db, institution_id=principal.institution_id, actor_id=principal.user_id,
                       actor_role=principal.role, event_type="CREDENTIAL_UPDATED", entity_type="Credential",
                       entity_id=cred.id, metadata={"username_changed": username_changed,
                                                  "password_changed": new_password is not None})
    return {"username": target_username, "sign_in_required": True}


def _inst_exists(db: Session, principal: Principal) -> bool:
    try:
        institutions.get_institution(db, principal.institution_id)
        return True
    except NotFoundError:
        return False


def create_credential(db: Session, *, institution_id: str, campus_user_id: str, username: str, password: str,
                      actor_id: Optional[str] = None, actor_role: Optional[str] = None) -> None:
    if get_settings().environment not in ("local", "test", "demo") and password == DEMO_PASSWORD:
        raise ValidationFailure("The public demo password cannot be used in production", code="DEMO_PASSWORD_DISABLED")
    if len(password) < 8:
        raise ValidationFailure("Password must be at least 8 characters", code="WEAK_PASSWORD")
    users.get_user(db, institution_id=institution_id, user_id=campus_user_id)
    row = Credential(institution_id=institution_id, campus_user_id=campus_user_id, username=username.strip(),
                     password_hash=hash_secret(password), status="ACTIVE")
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError as exc:
        raise ConflictError("Username or credential already exists", code="CREDENTIAL_EXISTS") from exc
    audit.record_event(db, institution_id=institution_id, actor_id=actor_id or "system", actor_role=actor_role,
                       event_type="CREDENTIAL_CREATED", entity_type="Credential", entity_id=row.id)


# -- payment PIN -------------------------------------------------------------------

def set_payment_pin(db: Session, *, institution_id: str, campus_user_id: str, pin: str,
                    actor_id: Optional[str], actor_role: Optional[str] = None) -> str:
    """Provision or change a customer's PIN (controlled, audited; provisioning/reset authority is MG-01 OPEN,
    so this is a provisional admin/demo mechanism). Does NOT clear a lock: unlock authority is OPEN."""
    if not isinstance(pin, str) or not _PIN_RE.match(pin):
        raise ValidationFailure("PIN must be exactly 4 digits", code="INVALID_PIN_FORMAT")
    users.require_active_customer(db, institution_id=institution_id, user_id=campus_user_id)
    hashed = hash_secret(pin, pepper=get_settings().pin_pepper)
    row = db.execute(select(PaymentPinCredential).where(
        PaymentPinCredential.institution_id == institution_id,
        PaymentPinCredential.campus_user_id == campus_user_id)).scalar_one_or_none()
    if row is None:
        row = PaymentPinCredential(institution_id=institution_id, campus_user_id=campus_user_id, pin_hash=hashed)
        db.add(row)
        event_type = "PIN_CREATED"
    else:
        row.pin_hash = hashed
        row.pin_set_at = utcnow()
        event_type = "PIN_CHANGED"
    db.flush()
    audit.record_event(db, institution_id=institution_id, actor_id=actor_id, actor_role=actor_role,
                       event_type=event_type, entity_type="PaymentPinCredential", entity_id=row.id,
                       reason="provisional admin/demo provisioning (MG-01 open)")
    return event_type


def reset_payment_pin(db: Session, *, institution_id: str, campus_user_id: str, pin: str,
                      actor_id: Optional[str], actor_role: Optional[str] = None) -> str:
    """Administrative PIN reset for a verified Campus User.

    The old PIN is never recoverable because only a salted hash is stored. A reset
    replaces that hash and clears failed-attempt / lock state so the new PIN can be
    used immediately. Every reset is audit logged.
    """
    if not isinstance(pin, str) or not _PIN_RE.match(pin):
        raise ValidationFailure("PIN must be exactly 4 digits", code="INVALID_PIN_FORMAT")
    users.require_active_customer(db, institution_id=institution_id, user_id=campus_user_id)
    hashed = hash_secret(pin, pepper=get_settings().pin_pepper)
    row = db.execute(select(PaymentPinCredential).where(
        PaymentPinCredential.institution_id == institution_id,
        PaymentPinCredential.campus_user_id == campus_user_id).with_for_update()).scalar_one_or_none()
    if row is None:
        row = PaymentPinCredential(institution_id=institution_id, campus_user_id=campus_user_id, pin_hash=hashed)
        db.add(row)
    else:
        row.pin_hash = hashed
        row.pin_set_at = utcnow()
        row.failed_attempts = 0
        row.locked_until = None
        row.last_failed_at = None
        row.status = "ACTIVE"
    db.flush()
    audit.record_event(db, institution_id=institution_id, actor_id=actor_id or "system", actor_role=actor_role,
                       event_type="PIN_RESET", entity_type="PaymentPinCredential", entity_id=row.id,
                       reason="Admin reset after Student ID verification")
    return "PIN_RESET"


def verify_payment_pin(db: Session, *, institution_id: str, campus_user_id: str, pin: str,
                       source_device_id: Optional[str] = None) -> PinCheck:
    """Check a PIN. Expected failures are RETURNED (never raised) after updating counters and audit rows
    (flushed, not committed): the caller commits them and refuses the operation.

    Lockout is mechanism-only: with CAMPUSPAY_PIN_MAX_FAILED_ATTEMPTS/LOCK_DURATION_SECONDS unset (MG-01 OPEN)
    failures are counted and audited but nothing is locked. Threshold, duration, reset and unlock authority
    are configuration/extension points, not hard-coded policy.
    """
    settings = get_settings()
    row = db.execute(select(PaymentPinCredential).where(
        PaymentPinCredential.institution_id == institution_id,
        PaymentPinCredential.campus_user_id == campus_user_id).with_for_update()).scalar_one_or_none()
    now = utcnow()

    def _audit(event_type: str, reason: Optional[str] = None, result: str = "FAILURE"):
        audit.record_event(db, institution_id=institution_id, actor_id=campus_user_id, event_type=event_type,
                           entity_type="PaymentPinCredential", entity_id=row.id if row else campus_user_id,
                           source_device_id=source_device_id, reason=reason, result=result)

    if row is None or row.status != "ACTIVE":
        _audit("PIN_FAILED", "PIN_NOT_SET")
        return PinCheck(PIN_NOT_SET)
    if row.locked_until and row.locked_until > now:
        _audit("PIN_FAILED", "LOCKED")
        return PinCheck(PIN_LOCKED)
    if not isinstance(pin, str) or not _PIN_RE.match(pin):
        return PinCheck(PIN_INVALID)  # malformed input: no attempt counted (validated upstream as 422)

    if verify_secret(pin, row.pin_hash, pepper=settings.pin_pepper):
        row.failed_attempts = 0
        row.locked_until = None
        db.flush()
        return PinCheck(PIN_OK)

    row.failed_attempts += 1
    row.last_failed_at = now
    _audit("PIN_FAILED", "INVALID")
    max_attempts, duration = settings.pin_max_failed_attempts, settings.pin_lock_duration_seconds
    if max_attempts is not None and duration is not None and row.failed_attempts >= max_attempts:
        row.locked_until = now + timedelta(seconds=duration)
        row.failed_attempts = 0
        _audit("PIN_LOCKED", f"threshold reached ({max_attempts})")
    db.flush()
    return PinCheck(PIN_INVALID)


def payment_pin_configured(db: Session, *, institution_id: str, campus_user_id: str) -> bool:
    return db.execute(select(PaymentPinCredential.id).where(
        PaymentPinCredential.institution_id == institution_id,
        PaymentPinCredential.campus_user_id == campus_user_id)).first() is not None


def consume_fingerprint_authorization(db, *, institution_id, authorization_id, order_id, student_id, device_id):
    """Called inside the payment transaction; a browser cannot manufacture a grant."""
    from modules.auth.kiosk_models import FingerprintChallenge, FingerprintEnrollment, KioskSession
    from core.errors import ForbiddenError
    c = db.execute(select(FingerprintChallenge).where(FingerprintChallenge.id == authorization_id,
        FingerprintChallenge.institution_id == institution_id).with_for_update()).scalar_one_or_none()
    if (not c or c.purpose != "PAY" or c.status != "READY" or c.expires_at <= utcnow()
            or c.order_id != order_id or c.student_id != student_id or c.device_id != device_id):
        raise ForbiddenError("Fresh two-scan authorization required", code="FINGERPRINT_AUTH_REQUIRED")
    s = db.get(KioskSession, c.session_id)
    enrolled = db.execute(select(FingerprintEnrollment).where(FingerprintEnrollment.institution_id == institution_id,
        FingerprintEnrollment.campus_user_id == student_id, FingerprintEnrollment.finger_ref == c.finger_ref,
        FingerprintEnrollment.status == "ACTIVE").with_for_update()).scalar_one_or_none()
    if c.auth_method == "MOBILE":
        from modules.auth.kiosk_models import MobileCredential
        enrolled = db.execute(select(MobileCredential).where(MobileCredential.id == c.finger_ref,
            MobileCredential.institution_id == institution_id, MobileCredential.campus_user_id == student_id,
            MobileCredential.status == "ACTIVE").with_for_update()).scalar_one_or_none()
    if not s or s.revoked or s.expires_at <= utcnow() or not enrolled:
        raise ForbiddenError("Fingerprint or kiosk session has been revoked", code="FINGERPRINT_REVOKED")
    c.status = "CONSUMED"
    db.flush()
