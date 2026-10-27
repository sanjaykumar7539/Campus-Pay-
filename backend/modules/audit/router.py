from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from core.errors import ok
from core.security import require_roles, tenant_db
from core.tenancy import Principal
from modules.audit import service

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])


@router.get("")
def list_audit_events(limit: int = 50, event_type: Optional[str] = None,
                      principal: Principal = Depends(require_roles("ADMIN")),
                      db: Session = Depends(tenant_db)):
    rows = service.list_events(db, institution_id=principal.institution_id, limit=limit, event_type=event_type)
    return ok([{"id": r.id, "event_type": r.event_type, "entity_type": r.entity_type,
                "entity_id": r.entity_id, "actor_id": r.actor_id, "metadata": r.metadata,
                "created_at": r.created_at.isoformat()} for r in rows])
