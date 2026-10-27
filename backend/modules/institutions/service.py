"""Institution module — published interface. Institution is the tenant root."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.errors import ConflictError, NotFoundError
from modules.institutions.models import Institution

ACTIVE = "ACTIVE"


@dataclass(frozen=True)
class InstitutionView:
    id: str
    code: str
    name: str
    status: str


def _view(row: Institution) -> InstitutionView:
    return InstitutionView(row.id, row.code, row.name, row.status)


def normalise_code(code: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "-", code.strip().upper()).strip("-")


def create_institution(db: Session, *, name: str, code: str) -> InstitutionView:
    row = Institution(name=name.strip(), code=normalise_code(code), status=ACTIVE)
    db.add(row)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("Institution code already in use", code="INSTITUTION_CODE_TAKEN") from exc
    return _view(row)


def get_institution(db: Session, institution_id: str) -> InstitutionView:
    row = db.get(Institution, institution_id)
    if row is None:
        raise NotFoundError("Institution not found", code="INSTITUTION_NOT_FOUND")
    return _view(row)


def find_by_code(db: Session, code: str) -> Optional[InstitutionView]:
    row = db.execute(select(Institution).where(Institution.code == normalise_code(code))).scalar_one_or_none()
    return _view(row) if row else None
