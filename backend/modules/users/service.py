"""Campus User module — published interface."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.errors import ConflictError, ForbiddenError, NotFoundError, ValidationFailure
from modules.audit import service as audit
from modules.users import identity
from modules.users.identity import IdentitySignal
from modules.users.models import CampusUser

STUDENT = "STUDENT"
MERCHANT_STAFF = "MERCHANT_STAFF"
ADMIN = "ADMIN"
ROLES = frozenset({STUDENT, MERCHANT_STAFF, ADMIN})
# Roles that are Customers for campus commerce (Operating Model §5.1). Faculty
# wallet policy is not yet specified, so only STUDENT is a customer in P1.
CUSTOMER_ROLES = frozenset({STUDENT})
ACTIVE = "ACTIVE"

__all__ = ["IdentitySignal", "UserView", "create_user", "get_user", "list_users", "count_users",
           "resolve_customer", "require_active_customer", "STUDENT", "MERCHANT_STAFF", "ADMIN",
           "CUSTOMER_ROLES", "ACTIVE", "supported_identity_kinds"]


@dataclass(frozen=True)
class UserView:
    id: str
    institution_id: str
    name: str
    role: str
    unique_identifier: str
    status: str

    @property
    def is_customer(self) -> bool:
        return self.role in CUSTOMER_ROLES


def _view(row: CampusUser) -> UserView:
    return UserView(row.id, row.institution_id, row.name, row.role, row.unique_identifier, row.status)


def create_user(db: Session, *, institution_id: str, name: str, role: str, unique_identifier: str,
                actor_id: Optional[str] = None, actor_role: Optional[str] = None) -> UserView:
    if role not in ROLES:
        raise ValidationFailure(f"Unknown role {role}", code="INVALID_ROLE")
    name, unique_identifier = name.strip(), unique_identifier.strip()
    if not name or not unique_identifier:
        raise ValidationFailure("Name and campus identifier are required", code="INVALID_USER")
    row = CampusUser(institution_id=institution_id, name=name, role=role,
                     unique_identifier=unique_identifier, status=ACTIVE)
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError as exc:
        raise ConflictError("Campus ID already in use in this institution", code="CAMPUS_ID_TAKEN") from exc
    audit.record_event(
        db, institution_id=institution_id, actor_id=actor_id or "system", actor_role=actor_role,
        event_type="STUDENT_REGISTERED" if role == STUDENT else "USER_REGISTERED",
        entity_type="CampusUser", entity_id=row.id,
        new={"role": role, "unique_identifier": unique_identifier})
    return _view(row)


def get_user(db: Session, *, institution_id: str, user_id: str) -> UserView:
    row = db.execute(select(CampusUser).where(CampusUser.institution_id == institution_id,
                                              CampusUser.id == user_id)).scalar_one_or_none()
    if row is None:
        raise NotFoundError("Campus User not found", code="USER_NOT_FOUND")
    return _view(row)


def list_users(db: Session, *, institution_id: str, role: Optional[str] = None) -> list[UserView]:
    stmt = select(CampusUser).where(CampusUser.institution_id == institution_id)
    if role:
        stmt = stmt.where(CampusUser.role == role)
    return [_view(r) for r in db.execute(stmt.order_by(CampusUser.unique_identifier)).scalars()]


def count_users(db: Session, *, institution_id: str, role: str) -> int:
    return int(db.execute(select(func.count()).select_from(CampusUser).where(
        CampusUser.institution_id == institution_id, CampusUser.role == role)).scalar_one())


def supported_identity_kinds() -> list[str]:
    return identity.supported_kinds()


def resolve_customer(db: Session, *, institution_id: str, signal: IdentitySignal) -> UserView:
    """Identify a Customer inside ONE institution from an identity signal.

    Unknown identifiers and non-customer identities produce the same error.
    """
    row = identity.resolve(db, institution_id, signal)
    if row is None or row.role not in CUSTOMER_ROLES:
        raise NotFoundError("Customer could not be identified", code="CUSTOMER_NOT_IDENTIFIED")
    return _view(row)


def require_active_customer(db: Session, *, institution_id: str, user_id: str) -> UserView:
    user = get_user(db, institution_id=institution_id, user_id=user_id)
    if not user.is_customer:
        raise NotFoundError("Customer could not be identified", code="CUSTOMER_NOT_IDENTIFIED")
    if user.status != ACTIVE:
        raise ForbiddenError("Customer is not active", code="CUSTOMER_INACTIVE")
    return user
