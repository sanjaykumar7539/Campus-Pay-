from fastapi import APIRouter, Depends, Request, Response, Header
from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, Literal
from core.config import get_settings
from core.security import get_db, require_roles, tenant_db, decode_access_token
from core.errors import ok, ForbiddenError
from app import kiosk_service as service
from app import kiosk_credentials
from modules.auth import service as auth
from modules.payments.router import _outcome

router = APIRouter(prefix="/api/v1", tags=["fingerprint-kiosk"])


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Setup(Strict):
    institution_code: str = Field(min_length=1, max_length=64)
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=72)
    device_id: str = Field(min_length=1, max_length=64)
    authentication_mode: Literal["AUTO","SCANNER","MOBILE"] = "AUTO"
    receipt_mode: Literal["BROWSER","THERMAL"] = "BROWSER"


class Unlock(Strict):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=72)


class Line(Strict):
    product_id: str = Field(min_length=1, max_length=64)
    quantity: int = Field(ge=1, le=100, strict=True)


class Cart(Strict):
    items: list[Line] = Field(min_length=1, max_length=50)


class Enroll(Strict):
    device_id: str = Field(min_length=1, max_length=64)
    consent_confirmed: bool


class Capture(Strict):
    nonce: str = Field(min_length=64, max_length=64)
    capture_id: str = Field(min_length=16, max_length=128)
    matched: bool
    finger_ref: Optional[str] = Field(default=None, min_length=1, max_length=128)


def kiosk(request: Request, db=Depends(get_db)):
    # Custom header + Strict cookie prevents cross-origin form/credential attacks.
    if request.method != "GET" and request.headers.get("X-Kiosk-Request") != "1":
        raise ForbiddenError("Kiosk request header required")
    return service.session(db, request.cookies.get(service.COOKIE))


def scanner(x_scanner_token: str = Header(default=""), db=Depends(get_db)):
    return service.agent(db, x_scanner_token)


@router.post("/kiosk/setup")
def setup(body: Setup, response: Response, db=Depends(get_db)):
    if get_settings().environment in ("local", "demo", "test") and kiosk_credentials.HASH_FILE.is_file():
        principal = kiosk_credentials.verify_kiosk_login(db, body.institution_code, body.username, body.password)
    else:
        result = auth.login(db, institution_code=body.institution_code, username=body.username, password=body.password)
        if result.role != "ADMIN":
            raise ForbiddenError("Administrator credentials required")
        principal = decode_access_token(result.access_token)
    token = service.setup(db, principal, body.device_id, body.authentication_mode, body.receipt_mode)
    response.set_cookie(service.COOKIE, token, httponly=True, samesite="strict",
        secure=get_settings().environment not in ("local", "test", "demo"), max_age=service.SESSION_SECONDS, path="/")
    return ok({"configured": True})


@router.post("/kiosk/logout")
def logout(body: Unlock, request: Request, response: Response, db=Depends(get_db)):
    if request.headers.get("X-Kiosk-Request") != "1":
        raise ForbiddenError("Kiosk request header required")
    s = service.logout_session(db, request.cookies.get(service.COOKIE))
    service.logout(db, s, body.username, body.password)
    response.delete_cookie(service.COOKIE, path="/")
    return ok({"unlocked": True})


@router.get("/kiosk/menu")
def menu(s=Depends(kiosk), db=Depends(get_db)):
    return ok(service.menu(db, s))


@router.post("/kiosk/checkouts", status_code=201)
def checkout(body: Cart, s=Depends(kiosk), db=Depends(get_db)):
    if s.authentication_mode == "MOBILE":
        raise ForbiddenError("This session uses mobile passkey authentication")
    return ok(service.checkout(db, s, body.items))


@router.get("/kiosk/checkouts/{cid}")
def status(cid: str, s=Depends(kiosk), db=Depends(get_db)):
    return ok(service.view(service.kiosk_challenge(db, s, cid)))


@router.post("/kiosk/checkouts/{cid}/cancel")
def cancel(cid: str, s=Depends(kiosk), db=Depends(get_db)):
    return ok(service.cancel(db, service.kiosk_challenge(db, s, cid)))


@router.post("/kiosk/checkouts/{cid}/pay")
def pay(cid: str, s=Depends(kiosk), db=Depends(get_db)):
    return ok(_outcome(service.pay(db, s, cid)))


@router.post("/kiosk/checkouts/{cid}/finish")
def finish(cid: str, s=Depends(kiosk), db=Depends(get_db)):
    c = service.kiosk_challenge(db, s, cid)
    if c.status == "CONSUMED":
        c.status = "FINISHED"
        db.commit()
    elif c.status != "FINISHED":
        service.cancel(db, c)
    return ok({"finished": True})


@router.post("/admin/devices/{device_id}/scanner-key")
def provision(device_id: str, p=Depends(require_roles("ADMIN")), db=Depends(tenant_db)):
    return ok(service.provision_agent(db, p, device_id))


@router.post("/admin/students/{student_id}/fingerprint")
def enroll(student_id: str, body: Enroll, p=Depends(require_roles("ADMIN")), db=Depends(tenant_db)):
    return ok(service.enrollment(db, p, student_id, body.device_id, body.consent_confirmed))


@router.delete("/admin/students/{student_id}/fingerprint")
def revoke(student_id: str, p=Depends(require_roles("ADMIN")), db=Depends(tenant_db)):
    service.revoke_enrollment(db, p, student_id)
    return ok({"status": "REVOKED"})


@router.get("/admin/fingerprint/{cid}")
def enroll_status(cid: str, p=Depends(require_roles("ADMIN")), db=Depends(tenant_db)):
    return ok(service.view(service.get_challenge(db, cid, p.institution_id)))


@router.post("/admin/fingerprint/{cid}/cancel")
def enroll_cancel(cid: str, p=Depends(require_roles("ADMIN")), db=Depends(tenant_db)):
    return ok(service.cancel(db, service.get_challenge(db, cid, p.institution_id)))


@router.get("/scanner/jobs")
def jobs(a=Depends(scanner), db=Depends(get_db)):
    return ok(service.jobs(db, a))


@router.post("/scanner/jobs/{cid}/capture")
def capture(cid: str, body: Capture, a=Depends(scanner), db=Depends(get_db)):
    return ok(service.capture(db, a, cid, body))


from app import mobile_auth

class MobileConsent(Strict):
    consent_confirmed: bool

class MobileProof(Strict):
    ceremony_id: str = Field(min_length=1, max_length=64)
    credential: dict

@router.post("/admin/students/{student_id}/mobile/options")
def mobile_enroll_options(student_id: str, body: MobileConsent, request: Request,
        p=Depends(require_roles("ADMIN")), db=Depends(tenant_db)):
    return ok(mobile_auth.enroll_options(db, p, student_id, body.consent_confirmed, request))

@router.post("/admin/students/{student_id}/mobile/verify")
def mobile_enroll_verify(student_id: str, body: MobileProof, request: Request,
        p=Depends(require_roles("ADMIN")), db=Depends(tenant_db)):
    return ok(mobile_auth.enroll_verify(db, p, student_id, body, request))

@router.post("/kiosk/mobile/checkouts", status_code=201)
def mobile_checkout(body: Cart, s=Depends(kiosk), db=Depends(get_db)):
    if s.authentication_mode == "SCANNER":
        raise ForbiddenError("This kiosk uses the integrated fingerprint reader")
    return ok(service.checkout(db, s, body.items, auth_method="MOBILE"))

@router.post("/kiosk/checkouts/{cid}/mobile/options")
def mobile_options(cid: str, request: Request, s=Depends(kiosk), db=Depends(get_db)):
    return ok(mobile_auth.auth_options(db, s, cid, request))

@router.post("/kiosk/checkouts/{cid}/mobile/verify")
def mobile_verify(cid: str, body: MobileProof, request: Request, s=Depends(kiosk), db=Depends(get_db)):
    return ok(mobile_auth.auth_verify(db, s, cid, body, request))
