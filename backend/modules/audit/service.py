"""Audit module — published interface.

Every business-critical action across every module writes through
`record_event`; no module constructs an AuditLog directly (Campus Operating
Model v0.2 §4.3: attributable actor, role, action, target, previous/new value,
reason, result, reference and source/device).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import event, select
from sqlalchemy.orm import Session

from core.errors import DomainError
from modules.audit.models import AuditLog


@dataclass(frozen=True)
class AuditEventView:
    id: str
    institution_id: Optional[str]
    actor_id: Optional[str]
    event_type: str
    entity_type: str
    entity_id: str
    metadata: Optional[dict]
    created_at: datetime


def _view(row: AuditLog) -> AuditEventView:
    return AuditEventView(row.id, row.institution_id, row.actor_id, row.event_type, row.entity_type,
                          row.entity_id, row.metadata_json, row.created_at)


def record_event(
    db: Session,
    *,
    institution_id: Optional[str],
    actor_id: Optional[str],
    event_type: str,
    entity_type: str,
    entity_id: str,
    actor_role: Optional[str] = None,
    source_device_id: Optional[str] = None,
    previous: Optional[Any] = None,
    new: Optional[Any] = None,
    reason: Optional[str] = None,
    result: str = "SUCCESS",
    reference: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> AuditEventView:
    """Append one audit record. Never include secrets (PINs, passwords, tokens)."""
    payload: dict[str, Any] = dict(metadata or {})
    payload.update({
        "actor_role": actor_role,
        "source_device_id": source_device_id,
        "previous": previous,
        "new": new,
        "reason": reason,
        "result": result,
        "reference": reference,
    })
    payload = {k: v for k, v in payload.items() if v is not None}
    row = AuditLog(institution_id=institution_id, actor_id=actor_id, event_type=event_type,
                   entity_type=entity_type, entity_id=str(entity_id), metadata_json=payload)
    db.add(row)
    db.flush()
    return _view(row)


def list_events(db: Session, *, institution_id: str, limit: int = 50,
                event_type: Optional[str] = None, entity_id: Optional[str] = None) -> list[AuditEventView]:
    stmt = select(AuditLog).where(AuditLog.institution_id == institution_id)
    if event_type:
        stmt = stmt.where(AuditLog.event_type == event_type)
    if entity_id:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    stmt = stmt.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(min(max(limit, 1), 500))
    return [_view(r) for r in db.execute(stmt).scalars()]


def count_events(db: Session, *, institution_id: str, event_type: str, entity_id: Optional[str] = None) -> int:
    from sqlalchemy import func
    stmt = select(func.count()).select_from(AuditLog).where(
        AuditLog.institution_id == institution_id, AuditLog.event_type == event_type)
    if entity_id:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    return int(db.execute(stmt).scalar_one())


class ImmutableRecordError(DomainError):
    status_code = 409
    code = "IMMUTABLE_RECORD"


@event.listens_for(AuditLog, "before_update")
def _audit_no_update(*_):
    raise ImmutableRecordError("Audit records are immutable")


@event.listens_for(AuditLog, "before_delete")
def _audit_no_delete(*_):
    raise ImmutableRecordError("Audit records cannot be deleted")
