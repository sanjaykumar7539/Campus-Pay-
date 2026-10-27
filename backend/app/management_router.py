"""Administrative orchestration for merchant onboarding and staff assignment."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from core.security import require_roles, tenant_db
from core.errors import ok, ValidationFailure
from modules.merchants import service as merchants
from modules.users import service as users
from modules.auth import service as auth
from modules.devices import service as devices
from modules.devices.router import KioskCreate

router = APIRouter(prefix="/api/v1", tags=["management"])


@router.post("/devices", status_code=201)
def register_station(body: KioskCreate, p=Depends(require_roles("ADMIN")), db=Depends(tenant_db)):
    merchants.get_merchant(db, institution_id=p.institution_id, merchant_id=body.merchant_id)
    d = devices.register_kiosk(db, institution_id=p.institution_id, name=body.name, merchant_id=body.merchant_id,
        actor_id=p.user_id, actor_role=p.role)
    db.commit()
    return ok({"id": d.id, "name": d.name, "merchant_id": d.merchant_id, "status": d.status, "type": d.device_type})


class MerchantCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    category: str = Field(default="Canteen", min_length=1, max_length=100)
    staff_name: str = Field(min_length=1, max_length=200)
    staff_identifier: str = Field(min_length=1, max_length=64)
    username: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._@-]+$")
    password: str = Field(min_length=12, max_length=72)


class CategoryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    merchant_id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    display_order: int = 0


class Availability(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str = Field(pattern="^(ACTIVE|INACTIVE)$")


@router.post("/merchants", status_code=201)
def create(body: MerchantCreate, p=Depends(require_roles("ADMIN")), db=Depends(tenant_db)):
    if len(body.password.encode("utf-8")) > 72:
        raise ValidationFailure("Password must be at most 72 UTF-8 bytes")
    m = merchants.create_merchant(db, institution_id=p.institution_id, name=body.name, category=body.category,
        actor_id=p.user_id, actor_role=p.role)
    u = users.create_user(db, institution_id=p.institution_id, name=body.staff_name,
        role="MERCHANT_STAFF", unique_identifier=body.staff_identifier, actor_id=p.user_id, actor_role=p.role)
    auth.create_credential(db, institution_id=p.institution_id, campus_user_id=u.id, username=body.username,
        password=body.password, actor_id=p.user_id, actor_role=p.role)
    merchants.assign_staff(db, institution_id=p.institution_id, campus_user_id=u.id, merchant_id=m.id)
    cat = merchants.create_category(db, institution_id=p.institution_id, merchant_id=m.id, name="Menu",
        display_order=0, actor_user_id=p.user_id, actor_role=p.role)
    db.commit()
    return ok({"id": m.id, "name": m.name, "category_id": cat["id"], "staff_username": body.username})


@router.post("/categories", status_code=201)
def category(body: CategoryCreate, p=Depends(require_roles("ADMIN", "MERCHANT_STAFF")), db=Depends(tenant_db)):
    result = merchants.create_category(db, institution_id=p.institution_id, actor_user_id=p.user_id,
        actor_role=p.role, **body.model_dump())
    db.commit()
    return ok(result)


@router.patch("/merchant/availability")
def availability(body: Availability, p=Depends(require_roles("MERCHANT_STAFF")), db=Depends(tenant_db)):
    own = merchants.staff_merchant_id(db, institution_id=p.institution_id, campus_user_id=p.user_id)
    merchants.require_merchant_scope(db, institution_id=p.institution_id, actor_user_id=p.user_id, actor_role=p.role, merchant_id=own or "")
    m = merchants.set_accepting_orders(db, institution_id=p.institution_id, merchant_id=own,
        actor_id=p.user_id, accepting=body.status == "ACTIVE")
    db.commit()
    return ok({"id": m.id, "status": m.status, "accepting_orders": m.accepting_orders})
