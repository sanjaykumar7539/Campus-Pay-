from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.errors import ValidationFailure, ok
from core.security import require_roles, tenant_db
from core.tenancy import Principal
from modules.auth import service as auth_service
from modules.users import service as user_service
from modules.users.service import IdentitySignal, UserView
from modules.wallets import service as wallet_service
from shared.ids import new_id
from app.kiosk_service import enrollment_status
from typing import Optional
from core.errors import NotFoundError

router = APIRouter(prefix="/api/v1/admin/students", tags=["admin-students"])


class AdminStudentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    unique_identifier: str = Field(min_length=1, max_length=64, description="Student / Campus ID")
    pin: Optional[str] = Field(default=None, pattern=r"^\d{4}$")
    confirm_pin: Optional[str] = Field(default=None, pattern=r"^\d{4}$")
    initial_amount_cu: int = Field(default=0, ge=0, description="Initial wallet amount; ₹1 = 1 CU")


class AdminPinReset(BaseModel):
    campus_id: str = Field(min_length=1, max_length=64)
    new_pin: str = Field(pattern=r"^\d{4}$")
    confirm_pin: str = Field(pattern=r"^\d{4}$")


def _out(u: UserView) -> dict:
    return {"id": u.id, "name": u.name, "role": u.role, "unique_identifier": u.unique_identifier, "status": u.status}


def _row(db: Session, institution_id: str, u: UserView) -> dict:
    try:
        wallet = wallet_service.get_wallet(db, institution_id=institution_id, campus_user_id=u.id)
        balance = wallet.available_cu
        wallet_status = wallet.status
    except NotFoundError:
        balance = 0
        wallet_status = "NOT_CREATED"
    return {**_out(u), "campus_id": u.unique_identifier,
            "fingerprint_status": enrollment_status(db, institution_id, u.id),
            "pin_configured": auth_service.payment_pin_configured(db, institution_id=institution_id, campus_user_id=u.id),
            "available_cu": balance, "wallet_status": wallet_status}


@router.get("")
def list_students(principal: Principal = Depends(require_roles("ADMIN")), db: Session = Depends(tenant_db)):
    rows = user_service.list_users(db, institution_id=principal.institution_id, role=user_service.STUDENT)
    return ok([_row(db, principal.institution_id, u) for u in rows])


@router.post("", status_code=201)
def create_student(body: AdminStudentCreate, principal: Principal = Depends(require_roles("ADMIN")),
                   db: Session = Depends(tenant_db)):
    if body.pin != body.confirm_pin:
        raise ValidationFailure("PIN and confirm PIN do not match", code="PIN_MISMATCH")
    user = user_service.create_user(db, institution_id=principal.institution_id, name=body.name,
                                    role=user_service.STUDENT, unique_identifier=body.unique_identifier,
                                    actor_id=principal.user_id, actor_role=principal.role)
    wallet_service.create_wallet(db, institution_id=principal.institution_id, campus_user_id=user.id,
                                 actor_id=principal.user_id, actor_role=principal.role)
    if body.pin:
        auth_service.set_payment_pin(db, institution_id=principal.institution_id, campus_user_id=user.id,
                                     pin=body.pin, actor_id=principal.user_id, actor_role=principal.role)
    if body.initial_amount_cu > 0:
        wallet_service.credit_demo_funding(
            db, institution_id=principal.institution_id, campus_user_id=user.id,
            amount_cu=body.initial_amount_cu, reference=f"student-create-{new_id()}",
            actor_id=principal.user_id, actor_role=principal.role)
    db.commit()
    return ok(_row(db, principal.institution_id, user), "Student created")


@router.get("/verify/{campus_id}")
def verify_student(campus_id: str, principal: Principal = Depends(require_roles("ADMIN")),
                   db: Session = Depends(tenant_db)):
    user = user_service.resolve_customer(db, institution_id=principal.institution_id,
                                         signal=IdentitySignal("CAMPUS_ID", campus_id))
    return ok(_row(db, principal.institution_id, user))


@router.post("/reset-pin")
def reset_student_pin(body: AdminPinReset, principal: Principal = Depends(require_roles("ADMIN")),
                      db: Session = Depends(tenant_db)):
    if body.new_pin != body.confirm_pin:
        raise ValidationFailure("New PIN and confirm PIN do not match", code="PIN_MISMATCH")
    user = user_service.resolve_customer(db, institution_id=principal.institution_id,
                                         signal=IdentitySignal("CAMPUS_ID", body.campus_id))
    event = auth_service.reset_payment_pin(db, institution_id=principal.institution_id, campus_user_id=user.id,
                                           pin=body.new_pin, actor_id=principal.user_id, actor_role=principal.role)
    db.commit()
    return ok({"event": event, "campus_id": user.unique_identifier, "name": user.name,
               "pin_configured": True}, "Student PIN reset")
