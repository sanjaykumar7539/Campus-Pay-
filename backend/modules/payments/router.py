from typing import Optional

from fastapi import APIRouter, Depends, Header, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from core.errors import ok
from core.security import require_roles, tenant_db
from core.tenancy import Principal
from modules.merchants import service as merchants
from modules.payments import service
from modules.users.service import IdentitySignal

router = APIRouter(prefix="/api/v1", tags=["payments"])
STAFF = ("ADMIN", "MERCHANT_STAFF")
PAYERS = ("ADMIN", "MERCHANT_STAFF", "STUDENT")


class IdentityIn(BaseModel):
    kind: str = Field(default="CAMPUS_ID", max_length=32)
    value: str = Field(min_length=1, max_length=128)


def order_out(o: merchants.OrderView) -> dict:
    return {"id": o.id, "reference": o.reference, "status": o.status, "merchant_id": o.merchant_id,
            "customer_id": o.customer_id, "total_cu": o.total_cu,
            "items": [{"name": i.name, "unit_price_cu": i.unit_price_cu, "quantity": i.quantity,
                       "line_total_cu": i.line_total_cu} for i in o.items],
            "fulfillment": None if o.fulfillment is None else {"status": o.fulfillment.status}}


class PayRequest(BaseModel):
    """Payment authorisation. There is deliberately NO amount field: the server pays the order total."""
    model_config = ConfigDict(extra="forbid")
    identity: IdentityIn
    pin: str = Field(pattern=r"^\d{4}$", description="4-digit payment-authorisation PIN")


class LegacyManualPayment(BaseModel):
    """DEPRECATED MVP shape (amount in paise). Requires the PIN and the deprecated-endpoint flag."""
    model_config = ConfigDict(extra="forbid")
    campus_id: str = Field(min_length=1, max_length=128)
    merchant_id: str
    amount_minor: int = Field(gt=0)
    item_description: Optional[str] = Field(default=None, max_length=200)
    reference: str = Field(min_length=8, max_length=128)
    pin: str = Field(pattern=r"^\d{4}$")


def _payment(p: service.PaymentView) -> dict:
    return {"id": p.id, "reference": p.reference, "order_id": p.order_id, "kind": p.kind, "amount_cu": p.amount_cu,
            "status": p.status, "failure_reason": p.failure_reason, "created_at": p.created_at.isoformat(),
            "completed_at": p.completed_at.isoformat() if p.completed_at else None}


def _receipt(r: Optional[service.ReceiptView]) -> Optional[dict]:
    if r is None:
        return None
    return {"id": r.id, "receipt_number": r.receipt_number, "status": r.status, "issued_at": r.issued_at.isoformat(),
            "payment_id": r.payment_id, "order_id": r.order_id, **r.snapshot}


def _outcome(o: service.PaymentOutcome) -> dict:
    return {"payment": _payment(o.payment), "order": order_out(o.order) if o.order else None,
            "receipt": _receipt(o.receipt), "receipt_status": "ISSUED" if o.receipt else "NOT_ISSUED",
            "balance_before_cu": o.balance_before_cu, "balance_after_cu": o.balance_after_cu, "replayed": o.replayed}


@router.post("/orders/{order_id}/pay")
def pay_order(order_id: str, body: PayRequest, idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
              x_device_id: Optional[str] = Header(default=None),
              principal: Principal = Depends(require_roles(*PAYERS)), db: Session = Depends(tenant_db)):
    """Canonical commerce payment: Order -> customer identification -> 4-digit PIN -> PURCHASE -> Ledger -> Wallet."""
    identity = IdentitySignal("CAMPUS_ID", principal.username) if principal.role == "STUDENT" else IdentitySignal(body.identity.kind, body.identity.value)
    out = service.pay_order(db, institution_id=principal.institution_id, actor_user_id=principal.user_id,
                            actor_role=principal.role, order_id=order_id, identity=identity, pin=body.pin,
                            idempotency_key=idempotency_key or "", device_id=x_device_id)
    return ok(_outcome(out), "Payment completed" if not out.replayed else "Payment already completed (replayed)")


@router.get("/orders/{order_id}/payment")
def order_payment(order_id: str, principal: Principal = Depends(require_roles(*STAFF)), db: Session = Depends(tenant_db)):
    p = service.get_payment_for_order(db, institution_id=principal.institution_id, order_id=order_id,
                                      actor_user_id=principal.user_id, actor_role=principal.role)
    return ok(_payment(p) if p else None)


@router.get("/payments")
def list_payments(limit: int = 50, principal: Principal = Depends(require_roles("ADMIN")), db: Session = Depends(tenant_db)):
    return ok(service.list_payments(db, institution_id=principal.institution_id, limit=limit))


@router.get("/receipts/{receipt_id}")
def get_receipt(receipt_id: str, principal: Principal = Depends(require_roles(*STAFF)), db: Session = Depends(tenant_db)):
    return ok(_receipt(service.get_receipt(db, institution_id=principal.institution_id, receipt_id=receipt_id,
                                           actor_user_id=principal.user_id, actor_role=principal.role)))


@router.get("/payments/{payment_id}/receipt")
def payment_receipt(payment_id: str, principal: Principal = Depends(require_roles(*STAFF)), db: Session = Depends(tenant_db)):
    return ok(_receipt(service.get_receipt_for_payment(db, institution_id=principal.institution_id, payment_id=payment_id,
                                                       actor_user_id=principal.user_id, actor_role=principal.role)))


@router.post("/payments", deprecated=True)
def legacy_manual_payment(body: LegacyManualPayment, response: Response,
                          principal: Principal = Depends(require_roles(*STAFF)), db: Session = Depends(tenant_db)):
    """DEPRECATED / DEMO COMPATIBILITY ONLY. Manual amount-driven payment; the canonical flow is order-driven
    (POST /api/v1/orders then POST /api/v1/orders/{id}/pay)."""
    response.headers["Deprecation"] = "true"
    response.headers["Link"] = '</api/v1/orders>; rel="successor-version"'
    out = service.legacy_manual_payment(
        db, institution_id=principal.institution_id, actor_user_id=principal.user_id, actor_role=principal.role,
        identity=IdentitySignal("CAMPUS_ID", body.campus_id), merchant_id=body.merchant_id,
        amount_minor=body.amount_minor, pin=body.pin, reference=body.reference, item_description=body.item_description)
    data = _outcome(out)
    data["amount_minor"] = out.payment.amount_cu * 100
    data["new_balance_minor"] = out.balance_after_cu * 100
    return ok(data, "DEPRECATED endpoint: payment completed")


class AdminRefund(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=1, max_length=500)

@router.get("/admin/refund-payments")
def admin_refund_payments(p=Depends(require_roles("ADMIN")), db=Depends(tenant_db)):
    return ok(service.list_refund_payments(db,institution_id=p.institution_id))

@router.post("/admin/payments/{payment_id}/refund")
def admin_refund(payment_id: str, body: AdminRefund,
        p=Depends(require_roles("ADMIN")), db=Depends(tenant_db)):
    return ok(service.refund_payment(db,institution_id=p.institution_id,payment_id=payment_id,
        reason=body.reason,actor_id=p.user_id,actor_role=p.role), "Full payment refunded to the original wallet")
