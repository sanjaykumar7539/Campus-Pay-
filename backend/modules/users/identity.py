"""Customer identity abstraction (Campus Operating Model v0.2 §4.2, MG-02 OPEN).

Identity is an *input signal* that resolves to a Campus User. It is separate
from authentication and from payment authorisation (the 4-digit PIN).

The final identity mechanism (RFID / face / other) is an OPEN management
decision, so nothing here assumes any hardware. A mechanism is a resolver
registered under a ``kind``; P1 registers only ``CAMPUS_ID`` (the campus
identifier typed/pasted in the demo). Adding another mechanism means adding a
resolver — payment logic never changes.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from modules.users.models import CampusUser


@dataclass(frozen=True)
class IdentitySignal:
    kind: str
    value: str


IdentityResolver = Callable[[Session, str, str], Optional[CampusUser]]


def _resolve_campus_id(db: Session, institution_id: str, value: str) -> Optional[CampusUser]:
    return db.execute(
        select(CampusUser).where(CampusUser.institution_id == institution_id,
                                 CampusUser.unique_identifier == value.strip())
    ).scalar_one_or_none()


_RESOLVERS: dict[str, IdentityResolver] = {"CAMPUS_ID": _resolve_campus_id}


def supported_kinds() -> list[str]:
    return sorted(_RESOLVERS)


def register_identity_mechanism(kind: str, resolver: IdentityResolver) -> None:
    """Extension point for a future approved identity mechanism (MG-02)."""
    _RESOLVERS[kind.upper()] = resolver


def resolve(db: Session, institution_id: str, signal: IdentitySignal) -> Optional[CampusUser]:
    resolver = _RESOLVERS.get(signal.kind.upper())
    if resolver is None:
        return None
    return resolver(db, institution_id, signal.value)
