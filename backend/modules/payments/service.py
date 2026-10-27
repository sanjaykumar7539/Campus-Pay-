"""Payments module — published interface (ADR-0006).

Payments COORDINATES the purchase workflow; it never touches wallet balances or
the ledger directly — it delegates to the Wallet module, which records the PURCHASE
Financial Event in the Institution Ledger first.

Canonical flow (`pay_order`), one database transaction:

  lock Order -> idempotency check -> validate customer/merchant/order
  -> verify 4-digit PIN (failure counters committed on their own)
  -> Payment INITIATED -> Wallet.debit_for_purchase (Ledger PURCHASE, wallet value,
     wallet movement) -> Merchant.mark_order_paid (+ Fulfillment PAID)
  -> Payment COMPLETED -> audit -> COMMIT
  -> then (separate transaction) issue the digital Receipt.

Refusals raised before any write (insufficient balance, inactive wallet/merchant,
ledger/wallet discrepancy) roll back the savepoint and are recorded as a FAILED
payment; the wallet is untouched. Order, Payment, Receipt and Fulfillment keep
separate states.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from datetime import datetime
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.config import get_settings
from core.errors import (ConflictError, DomainError, ForbiddenError, NotFoundError, PaymentRequiredError,
                         ValidationFailure)
from modules.audit import service as audit
from modules.auth import service as auth
from modules.merchants import service as merchants
from modules.payments import receipts
from modules.payments.models import Payment, Receipt
from modules.users import service as users
from modules.users.service import IdentitySignal
from modules.wallets import service as wallets
from shared.campus_units import CampusUnitError, legacy_paise_to_cu, validate_cu
from shared.clock import utcnow
from shared.ids import new_id

INITIATED, COMPLETED, FAILED = "INITIATED", "COMPLETED", "FAILED"
KIND_ORDER, KIND_LEGACY = "ORDER", "LEGACY_MANUAL"


class PinRejectedError(ForbiddenError):
    code = "PIN_INVALID"


class PaymentRefusal(DomainError):
    """An expected refusal raised before any financial write."""


class MerchantInactiveError(PaymentRefusal, ConflictError):
    code = "MERCHANT_INACTIVE"


@dataclass(frozen=True)
class PaymentView:
    id: str
    institution_id: str
    order_id: Optional[str]
    merchant_id: str
    campus_user_id: str
    amount_cu: int
    status: str
    reference: str
    kind: str
    failure_reason: Optional[str]
    created_at: datetime
    completed_at: Optional[datetime]


@dataclass(frozen=True)
class ReceiptView:
    id: str
    receipt_number: str
    payment_id: str
    order_id: Optional[str]
    status: str
    snapshot: dict
    issued_at: datetime


@dataclass(frozen=True)
class PaymentOutcome:
    payment: PaymentView
    receipt: Optional[ReceiptView]
    balance_before_cu: int
    balance_after_cu: int
    replayed: bool
    order: Optional[merchants.OrderView]


def _pv(p: Payment) -> PaymentView:
    return PaymentView(p.id, p.institution_id, p.order_id, p.merchant_id, p.campus_user_id, p.amount_cu, p.status,
                       p.reference, p.kind, p.failure_reason, p.created_at, p.completed_at)


def _rv(r: Receipt) -> ReceiptView:
    return ReceiptView(r.id, r.receipt_number, r.payment_id, r.order_id, r.status, r.snapshot, r.issued_at)


def _by_reference(db: Session, institution_id: str, reference: str) -> Optional[Payment]:
    return db.execute(select(Payment).where(Payment.institution_id == institution_id,
                                            Payment.reference == reference)).scalar_one_or_none()


def _check_key(key: Optional[str]) -> str:
    key = (key or "").strip()
    if len(key) < 8 or len(key) > 128:
        raise ValidationFailure("An Idempotency-Key of 8-128 characters is required", code="IDEMPOTENCY_KEY_REQUIRED")
    return key


def _check_pin_format(pin: str) -> None:
    if not isinstance(pin, str) or len(pin) != 4 or not pin.isdigit() or not pin.isascii():
        raise ValidationFailure("PIN must be exactly 4 digits", code="INVALID_PIN_FORMAT")


def _receipt_for(db: Session, institution_id: str, payment_id: str) -> Optional[Receipt]:
    return db.execute(select(Receipt).where(Receipt.institution_id == institution_id,
                                            Receipt.payment_id == payment_id)).scalar_one_or_none()


# -- canonical: order-driven purchase ---------------------------------------------------------------

def pay_order(db: Session, *, institution_id: str, actor_user_id: str, actor_role: str, order_id: str,
              identity: IdentitySignal, pin: str, idempotency_key: str,
              device_id: Optional[str] = None) -> PaymentOutcome:
    """Order-driven Purchase. The payable amount is the server-derived order total; the client never sends one.
    Commits (or rolls back) the whole unit of work itself."""
    if os.getenv("CAMPUSPAY_PAYMENT_AUTH", "fingerprint") != "pin":
        raise ForbiddenError("PIN payment is disabled. Use fingerprint checkout.", code="FINGERPRINT_REQUIRED")
    key = _check_key(idempotency_key)
    _check_pin_format(pin)
    order = merchants.lock_order_for_payment(db, institution_id=institution_id, order_id=order_id)  # serialises per order
    merchants.require_merchant_scope(db, institution_id=institution_id, actor_user_id=actor_user_id,
                                     actor_role=actor_role, merchant_id=order.merchant_id)
    existing = _by_reference(db, institution_id, key)
    if existing is not None:
        return _replay(db, existing, expected_order_id=order.id, actor_user_id=actor_user_id, actor_role=actor_role)
    if order.status == merchants.ORDER_PAID:
        raise ConflictError("Order is already paid", code="ORDER_ALREADY_PAID")
    if order.status != merchants.ORDER_CREATED:
        raise ConflictError("Order is not payable", code="ORDER_NOT_PAYABLE")

    customer = users.resolve_customer(db, institution_id=institution_id, signal=identity)
    if customer.id != order.customer_id:
        audit.record_event(db, institution_id=institution_id, actor_id=actor_user_id, actor_role=actor_role,
                           event_type="PAYMENT_REJECTED", entity_type="Order", entity_id=order.id, result="FAILURE",
                           reason="ORDER_CUSTOMER_MISMATCH", source_device_id=device_id)
        db.commit()
        raise ForbiddenError("This order belongs to a different customer", code="ORDER_CUSTOMER_MISMATCH")
    return _run_purchase(db, institution_id=institution_id, actor_user_id=actor_user_id, actor_role=actor_role,
                         customer=customer, merchant_id=order.merchant_id, amount_cu=order.total_cu, order=order,
                         reference=key, kind=KIND_ORDER, item_description=None, device_id=device_id, pin=pin)


# -- deprecated: manual amount-driven payment (demo compatibility only) ------------------------------------

def legacy_manual_payment(db: Session, *, institution_id: str, actor_user_id: str, actor_role: str,
                          identity: IdentitySignal, merchant_id: str, amount_minor: int, pin: str, reference: str,
                          item_description: Optional[str]) -> PaymentOutcome:
    """DEPRECATED/DEMO compatibility path (never the canonical commerce flow). It runs through the SAME purchase
    core as `pay_order`, so tenant scoping, PIN authorisation, ledger, wallet guard, idempotency and audit all apply."""
    if os.getenv("CAMPUSPAY_PAYMENT_AUTH", "fingerprint") != "pin" or not get_settings().legacy_manual_payment_enabled:
        raise ForbiddenError("The deprecated manual payment endpoint is disabled", code="LEGACY_PAYMENT_DISABLED")
    key = _check_key(reference)
    _check_pin_format(pin)
    try:
        amount_cu = validate_cu(legacy_paise_to_cu(amount_minor))
    except CampusUnitError as exc:
        raise ValidationFailure(str(exc), code="INVALID_AMOUNT") from exc
    merchants.require_merchant_scope(db, institution_id=institution_id, actor_user_id=actor_user_id,
                                     actor_role=actor_role, merchant_id=merchant_id)
    existing = _by_reference(db, institution_id, key)
    if existing is not None:
        return _replay(db, existing, expected_order_id=None, actor_user_id=actor_user_id, actor_role=actor_role)
    customer = users.resolve_customer(db, institution_id=institution_id, signal=identity)
    return _run_purchase(db, institution_id=institution_id, actor_user_id=actor_user_id, actor_role=actor_role,
                         customer=customer, merchant_id=merchant_id, amount_cu=amount_cu, order=None, reference=key,
                         kind=KIND_LEGACY, item_description=item_description, device_id=None, pin=pin)


# -- shared purchase core --------------------------------------------------------------------------------------

def _run_purchase(db: Session, *, institution_id: str, actor_user_id: str, actor_role: str, customer: users.UserView,
                  merchant_id: str, amount_cu: int, order: Optional[merchants.OrderView], reference: str, kind: str,
                  item_description: Optional[str], device_id: Optional[str], pin: Optional[str],
                  authorization_id: Optional[str] = None) -> PaymentOutcome:
    if customer.status != users.ACTIVE:
        raise ForbiddenError("Customer is not active", code="CUSTOMER_INACTIVE")
    wallet = wallets.get_wallet(db, institution_id=institution_id, campus_user_id=customer.id)  # 404 if none

    # 1. Payment authorisation (4-digit PIN). Counters/audit are committed even though the payment is refused.
    if authorization_id:
        auth.consume_fingerprint_authorization(db, institution_id=institution_id, authorization_id=authorization_id,
            order_id=order.id, student_id=customer.id, device_id=device_id)
    else:
        check = auth.verify_payment_pin(db, institution_id=institution_id, campus_user_id=customer.id, pin=pin,
                                        source_device_id=device_id)
        if not check.ok:
            db.commit()
            raise PinRejectedError({"INVALID": "Incorrect PIN", "LOCKED": "PIN is locked", "NOT_SET": "No PIN is set"}[check.status],
                                   code={"INVALID": "PIN_INVALID", "LOCKED": "PIN_LOCKED", "NOT_SET": "PIN_NOT_SET"}[check.status])

    # 2. Payment INITIATED
    payment = Payment(id=new_id(), institution_id=institution_id, campus_user_id=customer.id, merchant_id=merchant_id,
                      wallet_id=wallet.id, order_id=order.id if order else None, device_id=device_id, kind=kind,
                      amount_cu=amount_cu, status=INITIATED, reference=reference, item_description=item_description)
    try:
        with db.begin_nested():
            db.add(payment)
            db.flush()
    except IntegrityError:
        db.rollback()
        existing = _by_reference(db, institution_id, reference)
        if existing is None:
            raise
        return _replay(db, existing, expected_order_id=order.id if order else None,
                       actor_user_id=actor_user_id, actor_role=actor_role)
    audit.record_event(db, institution_id=institution_id, actor_id=actor_user_id, actor_role=actor_role,
                       source_device_id=device_id, event_type="PAYMENT_INITIATED", entity_type="Payment",
                       entity_id=payment.id, reference=reference,
                       new={"amount_cu": amount_cu, "order_id": order.id if order else None, "kind": kind})

    # 3. Financial mutation (all-or-nothing inside a savepoint)
    try:
        with db.begin_nested():
            merchant = merchants.get_merchant(db, institution_id=institution_id, merchant_id=merchant_id, for_update=True)
            if merchant.status != merchants.ACTIVE or not merchant.accepting_orders:
                raise MerchantInactiveError("Merchant is not active")
            movement = wallets.debit_for_purchase(db, institution_id=institution_id, campus_user_id=customer.id,
                                                  amount_cu=amount_cu, payment_id=payment.id, actor_id=actor_user_id,
                                                  actor_role=actor_role, source_device_id=device_id)
            paid_order = (merchants.mark_order_paid(db, institution_id=institution_id, order_id=order.id,
                                                    actor_id=actor_user_id, actor_role=actor_role) if order else None)
    except (wallets.WalletFinancialRefusal, PaymentRefusal) as refusal:
        payment.status, payment.failure_reason = FAILED, refusal.code
        audit.record_event(db, institution_id=institution_id, actor_id=actor_user_id, actor_role=actor_role,
                           source_device_id=device_id, event_type="PAYMENT_FAILED", entity_type="Payment",
                           entity_id=payment.id, result="FAILURE", reason=refusal.code, reference=reference,
                           new={"amount_cu": amount_cu})
        db.commit()
        refusal.details.update({"payment_id": payment.id, "payment_status": FAILED})
        raise

    # 4. Payment COMPLETED, single commit
    payment.status, payment.completed_at = COMPLETED, utcnow()
    db.flush()
    audit.record_event(db, institution_id=institution_id, actor_id=actor_user_id, actor_role=actor_role,
                       source_device_id=device_id, event_type="PAYMENT_COMPLETED", entity_type="Payment",
                       entity_id=payment.id, reference=reference,
                       new={"amount_cu": amount_cu, "balance_after_cu": movement.balance_after_cu})
    db.commit()

    # 5. Receipt: separate concern, after the financial commit; its failure never reverses the debit.
    receipt = receipts.issue_receipt(db, institution_id=institution_id, payment_id=payment.id, actor_id=actor_user_id,
                                     actor_role=actor_role)
    return PaymentOutcome(_pv(payment), _rv(receipt) if receipt else None, movement.balance_before_cu,
                          movement.balance_after_cu, False, paid_order)


def pay_fingerprint_order(db, *, institution_id, order_id, student_id, device_id, authorization_id):
    from modules.devices import service as devices
    order = merchants.lock_order_for_payment(db, institution_id=institution_id, order_id=order_id)
    if order.customer_id != student_id or order.device_id != device_id:
        raise ForbiddenError("Fingerprint does not authorize this order")
    devices.require_active_kiosk_for_merchant(db, institution_id=institution_id, device_id=device_id, merchant_id=order.merchant_id)
    key = "fingerprint-" + authorization_id
    existing = _by_reference(db, institution_id, key)
    if existing:
        return _replay(db, existing, expected_order_id=order_id, actor_user_id=student_id, actor_role="STUDENT")
    if order.status != merchants.ORDER_CREATED:
        raise ConflictError("Order is no longer payable")
    customer = users.require_active_customer(db, institution_id=institution_id, user_id=student_id)
    return _run_purchase(db, institution_id=institution_id, actor_user_id=student_id, actor_role="STUDENT",
        customer=customer, merchant_id=order.merchant_id, amount_cu=order.total_cu, order=order,
        reference=key, kind=KIND_ORDER, item_description=None, device_id=device_id, pin=None,
        authorization_id=authorization_id)


def _replay(db: Session, existing: Payment, *, expected_order_id: Optional[str], actor_user_id: str,
            actor_role: str) -> PaymentOutcome:
    """Same idempotency key: resolve to the original result; never a second financial effect."""
    if existing.order_id != expected_order_id:
        raise ConflictError("Idempotency key already used for a different payment", code="IDEMPOTENCY_KEY_REUSED")
    if existing.status == FAILED:
        err = PaymentRequiredError("Original payment attempt failed", code=existing.failure_reason or "PAYMENT_FAILED",
                                   details={"payment_id": existing.id, "payment_status": FAILED, "replayed": True})
        raise err
    if existing.status != COMPLETED:
        raise ConflictError("Payment is still being processed; retry shortly", code="PAYMENT_IN_PROGRESS")
    movement = wallets.get_movement_for_payment(db, institution_id=existing.institution_id, payment_id=existing.id)
    receipt = _receipt_for(db, existing.institution_id, existing.id) or receipts.issue_receipt(
        db, institution_id=existing.institution_id, payment_id=existing.id, actor_id=actor_user_id, actor_role=actor_role)
    order = (merchants.describe_order(db, institution_id=existing.institution_id, order_id=existing.order_id)
             if existing.order_id else None)
    return PaymentOutcome(_pv(existing), _rv(receipt) if receipt else None,
                          movement.balance_before_cu if movement else 0, movement.balance_after_cu if movement else 0,
                          True, order)


# -- reads --------------------------------------------------------------------------------------------------------

def get_payment_for_order(db: Session, *, institution_id: str, order_id: str, actor_user_id: str,
                          actor_role: str) -> Optional[PaymentView]:
    order = merchants.get_order(db, institution_id=institution_id, order_id=order_id, actor_user_id=actor_user_id,
                                actor_role=actor_role)
    rows = db.execute(select(Payment).where(Payment.institution_id == institution_id, Payment.order_id == order.id)
                      .order_by(Payment.created_at.desc())).scalars().all()
    completed = [p for p in rows if p.status == COMPLETED]
    chosen = completed[0] if completed else (rows[0] if rows else None)
    return _pv(chosen) if chosen else None


def get_receipt(db: Session, *, institution_id: str, receipt_id: str, actor_user_id: str, actor_role: str) -> ReceiptView:
    r = db.execute(select(Receipt).where(Receipt.institution_id == institution_id, Receipt.id == receipt_id)).scalar_one_or_none()
    if r is None:
        raise NotFoundError("Receipt not found", code="RECEIPT_NOT_FOUND")
    p = db.execute(select(Payment).where(Payment.id == r.payment_id)).scalar_one()
    merchants.require_merchant_scope(db, institution_id=institution_id, actor_user_id=actor_user_id,
                                     actor_role=actor_role, merchant_id=p.merchant_id)
    return _rv(r)


def get_receipt_for_payment(db: Session, *, institution_id: str, payment_id: str, actor_user_id: str,
                            actor_role: str) -> ReceiptView:
    """Returns the receipt, issuing it now if a previous issuance attempt had failed (idempotent)."""
    p = db.execute(select(Payment).where(Payment.institution_id == institution_id, Payment.id == payment_id)).scalar_one_or_none()
    if p is None:
        raise NotFoundError("Payment not found", code="PAYMENT_NOT_FOUND")
    merchants.require_merchant_scope(db, institution_id=institution_id, actor_user_id=actor_user_id,
                                     actor_role=actor_role, merchant_id=p.merchant_id)
    if p.status != COMPLETED:
        raise ConflictError("Receipts exist only for completed payments", code="PAYMENT_NOT_COMPLETED")
    r = _receipt_for(db, institution_id, payment_id) or receipts.issue_receipt(
        db, institution_id=institution_id, payment_id=payment_id, actor_id=actor_user_id, actor_role=actor_role)
    if r is None:
        raise ConflictError("Receipt could not be issued right now; retry", code="RECEIPT_UNAVAILABLE")
    return _rv(r)


def list_payments(db: Session, *, institution_id: str, limit: int = 50) -> list[dict]:
    rows = db.execute(select(Payment).where(Payment.institution_id == institution_id)
                      .order_by(Payment.created_at.desc()).limit(min(max(limit, 1), 300))).scalars().all()
    people = {u.id: u for u in users.list_users(db, institution_id=institution_id)}
    names = {m.id: m.name for m in merchants.list_merchants(db, institution_id=institution_id, actor_role=users.ADMIN)}
    return [{"id": p.id, "reference": p.reference, "order_id": p.order_id, "kind": p.kind, "amount_cu": p.amount_cu,
             "status": p.status, "failure_reason": p.failure_reason,
             "student": people[p.campus_user_id].name if p.campus_user_id in people else None,
             "campus_id": people[p.campus_user_id].unique_identifier if p.campus_user_id in people else None,
             "merchant": names.get(p.merchant_id), "created_at": p.created_at.isoformat()} for p in rows]


def payment_summary(db: Session, *, institution_id: str) -> dict:
    rows = db.execute(select(Payment.status, func.count(), func.coalesce(func.sum(Payment.amount_cu), 0)).where(
        Payment.institution_id == institution_id).group_by(Payment.status)).all()
    return {status: {"count": int(n), "amount_cu": int(total)} for status, n, total in rows}


def list_refund_payments(db, *, institution_id):
    rows=list_payments(db,institution_id=institution_id,limit=300)
    for row in rows:
        row["refunded"]=wallets.payment_refunded(db,institution_id=institution_id,payment_id=row["id"])
    return rows


def refund_payment(db, *, institution_id, payment_id, reason, actor_id, actor_role):
    if actor_role != "ADMIN":
        raise ForbiddenError("Only administrators can issue refunds")
    payment=db.execute(select(Payment).where(Payment.id==payment_id,
        Payment.institution_id==institution_id).with_for_update()).scalar_one_or_none()
    if not payment:
        raise NotFoundError("Payment not found")
    if payment.status != COMPLETED:
        raise ConflictError("Only completed payments can be refunded")
    movement=wallets.credit_admin(db,institution_id=institution_id,campus_user_id=payment.campus_user_id,
        amount_cu=payment.amount_cu,reference=payment.id,reason=reason,actor_id=actor_id,refund=True)
    db.commit()
    from dataclasses import asdict
    return {**asdict(movement),"payment_id":payment.id}
