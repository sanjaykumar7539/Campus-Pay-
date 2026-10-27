from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.errors import ok
from core.security import require_roles, tenant_db
from core.tenancy import Principal
from modules.devices import service

router = APIRouter(prefix="/api/v1/devices", tags=["devices"])


class KioskCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    merchant_id: str = Field(min_length=1, max_length=64)


class DeviceStatusUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    status: Optional[str] = Field(default=None, pattern="^(ACTIVE|INACTIVE)$")


def _out(d: service.DeviceView) -> dict:
    return {"id": d.id, "type": d.device_type, "name": d.name, "merchant_id": d.merchant_id, "status": d.status}


@router.get("")
def list_devices(merchant_id: Optional[str] = None, principal: Principal = Depends(require_roles("ADMIN")),
                 db: Session = Depends(tenant_db)):
    return ok([_out(d) for d in service.list_devices(db, institution_id=principal.institution_id, merchant_id=merchant_id)])


@router.patch("/{device_id}")
def update_device(device_id: str, body: DeviceStatusUpdate, principal: Principal = Depends(require_roles("ADMIN")),
                  db: Session = Depends(tenant_db)):
    d = service.update_device(db, institution_id=principal.institution_id, device_id=device_id, name=body.name, status=body.status,
                              actor_id=principal.user_id, actor_role=principal.role)
    db.commit()
    return ok(_out(d))
