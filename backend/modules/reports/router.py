from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from core.errors import ok
from core.security import require_roles, tenant_db
from core.tenancy import Principal
from modules.reports import service

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])


@router.get("/dashboard")
def dashboard(principal: Principal = Depends(require_roles("ADMIN")), db: Session = Depends(tenant_db)):
    return ok(service.dashboard(db, institution_id=principal.institution_id))


@router.get("/reconciliation")
def reconciliation(principal: Principal = Depends(require_roles("ADMIN")), db: Session = Depends(tenant_db)):
    return ok(service.reconciliation(db, institution_id=principal.institution_id))
