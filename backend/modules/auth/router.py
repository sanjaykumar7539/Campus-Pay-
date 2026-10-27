from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from typing import Optional
from sqlalchemy.orm import Session

from core.errors import ok
from core.security import get_db, get_principal, require_roles, tenant_db
from core.tenancy import Principal
from modules.auth import service

router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])


class LoginRequest(BaseModel):
    institution_code: str = Field(min_length=1, max_length=64, description="Tenant code, e.g. EGS-ENGG")
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=256)


class StudentLoginRequest(BaseModel):
    institution_code: str = Field(min_length=1, max_length=64)
    campus_id: str = Field(min_length=1, max_length=128)


class PinRequest(BaseModel):
    campus_user_id: str = Field(min_length=1, max_length=64)
    pin: str = Field(pattern=r"^\d{4}$", description="Exactly four digits")


class CredentialUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_password: str = Field(min_length=1, max_length=256)
    username: Optional[str] = Field(default=None, min_length=1, max_length=128)
    new_password: Optional[str] = Field(default=None, min_length=8, max_length=72)


@router.post("/login")
def login(body: LoginRequest, db: Session = Depends(get_db)):
    r = service.login(db, institution_code=body.institution_code, username=body.username, password=body.password)
    return ok({"access_token": r.access_token, "token_type": "bearer", "role": r.role,
               "institution_id": r.institution_id, "user_id": r.user_id, "username": r.username})


@router.post("/student-login")
def student_login(body: StudentLoginRequest, db: Session = Depends(get_db)):
    r = service.student_login(db, institution_code=body.institution_code, campus_id=body.campus_id)
    return ok({"access_token": r.access_token, "token_type": "bearer", "role": r.role,
               "institution_id": r.institution_id, "user_id": r.user_id, "username": r.username})


@router.get("/me")
def me(principal: Principal = Depends(get_principal)):
    return ok({"user_id": principal.user_id, "institution_id": principal.institution_id,
               "role": principal.role, "username": principal.username})


@router.patch("/credentials")
def change_own_credentials(body: CredentialUpdate,
                           principal: Principal = Depends(require_roles("ADMIN", "MERCHANT_STAFF")),
                           db: Session = Depends(tenant_db)):
    result = service.update_own_credentials(db, principal=principal, **body.model_dump())
    db.commit()
    return ok(result, "Account updated. Please sign in again with your updated credentials.")


@router.post("/payment-pin")
def provision_payment_pin(body: PinRequest, principal: Principal = Depends(require_roles("ADMIN")),
                          db: Session = Depends(tenant_db)):
    """Provisional admin/demo PIN provisioning (production reset/unlock policy is MG-01 OPEN)."""
    event = service.set_payment_pin(db, institution_id=principal.institution_id, campus_user_id=body.campus_user_id,
                                    pin=body.pin, actor_id=principal.user_id, actor_role=principal.role)
    db.commit()
    return ok({"event": event}, "Payment PIN set")
