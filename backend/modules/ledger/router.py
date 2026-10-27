from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from core.errors import ok
from core.security import require_roles, tenant_db
from core.tenancy import Principal
from modules.ledger import service

router = APIRouter(prefix="/api/v1/ledger", tags=["ledger"])


@router.get("/entries")
def list_entries(campus_user_id: Optional[str] = None, limit: int = 100,
                 principal: Principal = Depends(require_roles("ADMIN")), db: Session = Depends(tenant_db)):
    """Read-only view of the Institution Ledger. There is deliberately no write, update or delete endpoint."""
    rows = service.list_entries(db, institution_id=principal.institution_id, campus_user_id=campus_user_id, limit=limit)
    return ok([{"id": e.id, "campus_user_id": e.campus_user_id, "sequence": e.customer_sequence,
                "event_type": e.event_type, "direction": e.direction, "amount_cu": e.amount_cu,
                "position_before_cu": e.position_before_cu, "position_after_cu": e.position_after_cu,
                "origin": e.origin, "reference_type": e.reference_type, "reference_id": e.reference_id,
                "created_at": e.created_at.isoformat()} for e in rows])
