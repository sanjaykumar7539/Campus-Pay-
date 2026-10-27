"""Tenant context and defence-in-depth tenant filtering (ADR-0001, ARCHITECTURE.md AC-004).

Two layers protect tenant isolation:

1. PRIMARY: every module service takes an explicit ``institution_id`` and every
   query filters on it. Institution context is derived from the authenticated
   principal (or the registered device) — never from "the first institution".
2. BACKSTOP: a session bound to a tenant (``session.info["tenant_id"]``)
   transparently appends ``institution_id = :tenant`` to every ORM SELECT of a
   `TenantScoped` entity, so a forgotten filter cannot leak another tenant's rows.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import event
from sqlalchemy.orm import Session, with_loader_criteria


class TenantScoped:
    """Marker mixin: the mapped class has an ``institution_id`` column."""


@dataclass(frozen=True)
class Principal:
    """The authenticated actor and the tenant it operates in."""

    user_id: str
    institution_id: str
    role: str
    username: str
    token_version: int = 0


TENANT_INFO_KEY = "tenant_id"


def bind_session_to_tenant(db: Session, institution_id: str) -> Session:
    db.info[TENANT_INFO_KEY] = institution_id
    return db


def _tenant_scoped_classes() -> list[type]:
    from core.database import Base  # local import: keeps this module importable early

    return [m.class_ for m in Base.registry.mappers if issubclass(m.class_, TenantScoped)]


@event.listens_for(Session, "do_orm_execute")
def _apply_tenant_filter(state):  # pragma: no cover - exercised via tests
    tenant_id = state.session.info.get(TENANT_INFO_KEY)
    if tenant_id is None or not state.is_select or state.is_column_load or state.is_relationship_load:
        return
    state.statement = state.statement.options(*[
        with_loader_criteria(cls, lambda c: c.institution_id == tenant_id, include_aliases=True)
        for cls in _tenant_scoped_classes()
    ])
