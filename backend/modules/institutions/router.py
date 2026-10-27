from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from core.errors import ok
from core.security import get_principal, tenant_db
from core.tenancy import Principal
from modules.institutions import service

router = APIRouter(prefix="/api/v1/institutions", tags=["institutions"])


@router.get("")
def list_institutions(principal: Principal = Depends(get_principal), db: Session = Depends(tenant_db)):
    """A tenant can only ever see itself (the MVP returned every institution)."""
    inst = service.get_institution(db, principal.institution_id)
    return ok([{"id": inst.id, "code": inst.code, "name": inst.name, "status": inst.status}])
