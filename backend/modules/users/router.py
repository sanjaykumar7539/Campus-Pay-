from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.errors import ok
from core.security import require_roles, tenant_db
from core.tenancy import Principal
from modules.users import service
from modules.users.service import IdentitySignal, UserView

router = APIRouter(prefix="/api/v1", tags=["campus-users"])


class StudentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    unique_identifier: str = Field(min_length=1, max_length=64, description="Campus ID (unique within the institution)")


class IdentifyRequest(BaseModel):
    kind: str = Field(default="CAMPUS_ID", max_length=32)
    value: str = Field(min_length=1, max_length=128)


def _out(u: UserView) -> dict:
    return {"id": u.id, "name": u.name, "role": u.role, "unique_identifier": u.unique_identifier, "status": u.status}


@router.get("/student/me")
def student_me(principal: Principal = Depends(require_roles("STUDENT")), db: Session = Depends(tenant_db)):
    user = service.get_user(db, institution_id=principal.institution_id, user_id=principal.user_id)
    return ok({"id": user.id, "name": user.name, "campus_id": user.unique_identifier, "status": user.status})


@router.get("/students")
def list_students(principal: Principal = Depends(require_roles("ADMIN")), db: Session = Depends(tenant_db)):
    return ok([_out(u) for u in service.list_users(db, institution_id=principal.institution_id, role=service.STUDENT)])


@router.post("/students", status_code=201)
def register_student(body: StudentCreate, principal: Principal = Depends(require_roles("ADMIN")),
                     db: Session = Depends(tenant_db)):
    """Registers a Student only. Wallet creation and funding are separate concerns
    (POST /api/v1/wallets; demo funding is not part of registration)."""
    user = service.create_user(db, institution_id=principal.institution_id, name=body.name,
                               role=service.STUDENT, unique_identifier=body.unique_identifier,
                               actor_id=principal.user_id, actor_role=principal.role)
    db.commit()
    return ok(_out(user), "Student registered")


@router.post("/customers/identify")
def identify_customer(body: IdentifyRequest, principal: Principal = Depends(require_roles("ADMIN", "MERCHANT_STAFF")),
                      db: Session = Depends(tenant_db)):
    """Customer identification (identity signal → Campus User). Not authentication and not payment authorisation."""
    user = service.resolve_customer(db, institution_id=principal.institution_id,
                                    signal=IdentitySignal(body.kind, body.value))
    return ok({"customer_id": user.id, "display_name": user.name, "campus_id": user.unique_identifier,
               "status": user.status, "supported_identity_kinds": service.supported_identity_kinds()})
