"""WebAuthn signatures are verified server-side; no browser success flags accepted."""
import os, json, base64
from datetime import timedelta
from urllib.parse import urlparse
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from webauthn import generate_registration_options, generate_authentication_options, verify_registration_response, verify_authentication_response
from webauthn.helpers import options_to_json, base64url_to_bytes
from webauthn.helpers.structs import AuthenticatorSelectionCriteria, AuthenticatorAttachment, ResidentKeyRequirement, UserVerificationRequirement, PublicKeyCredentialDescriptor
from modules.auth.kiosk_models import MobileCredential, MobileCeremony
from modules.users import service as users
from modules.merchants import service as merchants
from modules.audit import service as audit
from core.errors import ForbiddenError, ConflictError
from shared.clock import utcnow
from app import kiosk_service as kiosk

def encode(value):
    return base64.urlsafe_b64encode(value).decode().rstrip("=")

def settings(request):
    origin = os.getenv("CAMPUSPAY_WEBAUTHN_ORIGIN", "http://localhost:8002").rstrip("/")
    parsed = urlparse(origin)
    rp = os.getenv("CAMPUSPAY_WEBAUTHN_RP_ID", parsed.hostname or "")
    if (parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname == "localhost")) or not rp or parsed.path:
        raise ForbiddenError("Configure the HTTPS WebAuthn origin and RP ID before mobile authentication")
    if request.headers.get("origin") != origin:
        raise ForbiddenError("Mobile authentication requires the configured HTTPS address", code="WEBAUTHN_ORIGIN")
    return origin, rp

def options(db, inst, owner, target, purpose, opts):
    db.execute(update(MobileCeremony).where(MobileCeremony.institution_id == inst,
        MobileCeremony.owner_id == owner, MobileCeremony.target_id == target,
        MobileCeremony.purpose == purpose, MobileCeremony.used == 0).values(used=1))
    row = MobileCeremony(institution_id=inst, owner_id=owner, target_id=target,
        purpose=purpose, challenge=encode(opts.challenge), expires_at=utcnow()+timedelta(seconds=90))
    db.add(row); db.commit()
    return {"ceremony_id": row.id, "options": json.loads(options_to_json(opts))}

def ceremony(db, inst, owner, target, purpose, cid):
    row = db.execute(select(MobileCeremony).where(MobileCeremony.id == cid,
        MobileCeremony.institution_id == inst).with_for_update()).scalar_one_or_none()
    if not row or row.owner_id != owner or row.target_id != target or row.purpose != purpose or row.used or row.expires_at <= utcnow():
        raise ForbiddenError("Authentication prompt expired or was already used")
    # Atomic claim also rejects concurrent SQLite verifications.
    result = db.execute(update(MobileCeremony).where(MobileCeremony.id == row.id,
        MobileCeremony.used == 0).values(used=1))
    if result.rowcount != 1:
        raise ForbiddenError("Authentication prompt was already used")
    return row

def enroll_options(db, principal, student_id, consent, request):
    origin, rp = settings(request)
    if not consent:
        raise ForbiddenError("Confirm informed consent before enrollment")
    user = users.require_active_customer(db, institution_id=principal.institution_id, user_id=student_id)
    existing = db.execute(select(MobileCredential).where(MobileCredential.institution_id == principal.institution_id,
        MobileCredential.campus_user_id == student_id)).scalars().all()
    if len(existing) >= 5:
        raise ConflictError("Enrollment limit reached; contact the operator")
    opts = generate_registration_options(rp_id=rp, rp_name="CampusPay", user_id=user.id.encode(),
        user_name=user.id, user_display_name=user.name,
        exclude_credentials=[PublicKeyCredentialDescriptor(id=base64url_to_bytes(r.credential_id)) for r in existing],
        authenticator_selection=AuthenticatorSelectionCriteria(authenticator_attachment=AuthenticatorAttachment.PLATFORM,
            resident_key=ResidentKeyRequirement.REQUIRED, user_verification=UserVerificationRequirement.REQUIRED))
    return options(db, principal.institution_id, principal.user_id, student_id, "ENROLL", opts)

def enroll_verify(db, principal, student_id, body, request):
    origin, rp = settings(request)
    users.require_active_customer(db, institution_id=principal.institution_id, user_id=student_id)
    row = ceremony(db, principal.institution_id, principal.user_id, student_id, "ENROLL", body.ceremony_id)
    try:
        result = verify_registration_response(credential=body.credential, expected_challenge=base64url_to_bytes(row.challenge),
            expected_rp_id=rp, expected_origin=origin, require_user_verification=True)
    except Exception as exc:
        raise ForbiddenError("Mobile enrollment verification failed") from exc
    credential = MobileCredential(institution_id=principal.institution_id, campus_user_id=student_id,
        credential_id=encode(result.credential_id), public_key=encode(result.credential_public_key), sign_count=result.sign_count)
    db.add(credential)
    audit.record_event(db, institution_id=principal.institution_id, actor_id=principal.user_id, actor_role="ADMIN",
        event_type="MOBILE_PASSKEY_ENROLLED", entity_type="CampusUser", entity_id=student_id)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback(); raise ConflictError("This passkey is already enrolled") from exc
    return {"status": "ENROLLED"}

def auth_options(db, session, cid, request):
    origin, rp = settings(request)
    kiosk.active_device(db, session.institution_id, session.device_id)
    c = kiosk.kiosk_challenge(db, session, cid)
    if c.auth_method != "MOBILE" or c.status not in ("FIRST_SCAN", "SECOND_SCAN") or c.expires_at <= utcnow():
        raise ForbiddenError("Checkout authorization has ended")
    allowed = []
    if c.status == "SECOND_SCAN":
        cred = db.get(MobileCredential, c.finger_ref)
        if not cred or cred.status != "ACTIVE":
            raise ForbiddenError("Mobile passkey revoked")
        allowed = [PublicKeyCredentialDescriptor(id=base64url_to_bytes(cred.credential_id))]
    opts = generate_authentication_options(rp_id=rp, allow_credentials=allowed,
        user_verification=UserVerificationRequirement.REQUIRED)
    return options(db, session.institution_id, session.id, c.id, c.status, opts)

def auth_verify(db, session, cid, body, request):
    origin, rp = settings(request)
    kiosk.active_device(db, session.institution_id, session.device_id)
    c = kiosk.kiosk_challenge(db, session, cid)
    if c.auth_method != "MOBILE" or c.status not in ("FIRST_SCAN", "SECOND_SCAN") or c.expires_at <= utcnow():
        raise ForbiddenError("Checkout authorization has ended")
    row = ceremony(db, session.institution_id, session.id, c.id, c.status, body.ceremony_id)
    cred = db.execute(select(MobileCredential).where(MobileCredential.credential_id == body.credential.get("id"),
        MobileCredential.institution_id == session.institution_id, MobileCredential.status == "ACTIVE").with_for_update()).scalar_one_or_none()
    if not cred or (c.status == "SECOND_SCAN" and cred.id != c.finger_ref):
        raise ForbiddenError("Use the same enrolled mobile passkey for both confirmations")
    try:
        result = verify_authentication_response(credential=body.credential, expected_challenge=base64url_to_bytes(row.challenge),
            expected_rp_id=rp, expected_origin=origin, credential_public_key=base64url_to_bytes(cred.public_key),
            credential_current_sign_count=cred.sign_count, require_user_verification=True)
    except Exception as exc:
        raise ForbiddenError("Mobile authentication verification failed") from exc
    handle = body.credential.get("response", {}).get("userHandle")
    if handle is not None and base64url_to_bytes(handle) != cred.campus_user_id.encode():
        raise ForbiddenError("Passkey account does not match enrollment")
    customer = users.require_active_customer(db, institution_id=session.institution_id, user_id=cred.campus_user_id)
    cred.sign_count = result.new_sign_count
    if c.status == "FIRST_SCAN":
        order, _ = merchants.create_order(db, institution_id=session.institution_id, merchant_id=c.cart["merchant_id"],
            customer_id=customer.id, items=[(i["product_id"], i["quantity"]) for i in c.cart["items"]],
            actor_user_id=customer.id, actor_role="STUDENT", device_id=session.device_id, client_request_key="kiosk-"+c.id)
        if order.total_cu != c.cart["total_cu"] or any(next(i["price_cu"] for i in c.cart["items"] if i["product_id"] == line.product_id) != line.unit_price_cu for line in order.items):
            raise ConflictError("Menu price changed. Start a new checkout.")
        c.student_id, c.order_id, c.finger_ref, c.status = customer.id, order.id, cred.id, "SECOND_SCAN"
        c.expires_at = utcnow()+timedelta(seconds=90)
    else:
        c.status = "READY"
    audit.record_event(db, institution_id=session.institution_id, actor_id=customer.id, actor_role="STUDENT",
        event_type="MOBILE_"+c.status, entity_type="FingerprintChallenge", entity_id=c.id)
    db.commit()
    return kiosk.view(c)
