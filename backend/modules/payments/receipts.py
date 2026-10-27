"""Receipt issuance (internal to the Payments module).

A receipt is issued AFTER the financial transaction commits, in its own
transaction, and is idempotent per payment (unique payment_id). A failure here can
therefore never reverse a completed wallet debit. Physical printer integration,
printer-failure recovery (MG-10) and reprint policy (MG-11) are OPEN and not
implemented; `ReceiptDelivery` is the extension point for them.
"""
from __future__ import annotations

import logging
from typing import Optional, Protocol

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from modules.audit import service as audit
from modules.institutions import service as institutions
from modules.merchants import service as merchants
from modules.payments.models import Payment, Receipt
from modules.users import service as users
from modules.wallets import service as wallets
from shared.clock import utcnow
from shared.ids import opaque_reference

log = logging.getLogger("campuspay.receipts")


class ReceiptDelivery(Protocol):
    """Future output channels (thermal printer, SMS...). Not implemented in P1."""

    def deliver(self, receipt: dict) -> None: ...


class DigitalReceiptDelivery:
    """P1 delivery: the digital receipt record itself is the deliverable."""

    def deliver(self, receipt: dict) -> None:
        return None


def build_snapshot(db: Session, payment: Payment) -> dict:
    movement = wallets.get_movement_for_payment(db, institution_id=payment.institution_id, payment_id=payment.id)
    inst = institutions.get_institution(db, payment.institution_id)
    merchant = merchants.get_merchant(db, institution_id=payment.institution_id, merchant_id=payment.merchant_id)
    customer = users.get_user(db, institution_id=payment.institution_id, user_id=payment.campus_user_id)
    order_reference, lines = None, []
    if payment.order_id:
        order = merchants.describe_order(db, institution_id=payment.institution_id, order_id=payment.order_id)
        order_reference = order.reference
        lines = [{"name": i.name, "unit_price_cu": i.unit_price_cu, "quantity": i.quantity,
                  "line_total_cu": i.line_total_cu} for i in order.items]
    else:
        lines = [{"name": payment.item_description or "Manual payment", "unit_price_cu": payment.amount_cu,
                  "quantity": 1, "line_total_cu": payment.amount_cu}]
    return {"institution": inst.name, "merchant": merchant.name,
            "balance_after_cu": movement.balance_after_cu if movement else None,
            "warning": "Keep this receipt until collection. Do not share it. For payment or printing issues, contact canteen staff; do not pay again.",
            "customer": {"name": customer.name, "campus_id": customer.unique_identifier},
            "order_reference": order_reference, "payment_reference": payment.reference, "payment_id": payment.id,
            "amount_cu": payment.amount_cu, "unit": "Campus Units (1 CU = ₹1)", "lines": lines,
            "paid_at": (payment.completed_at or utcnow()).isoformat() + "Z"}


def issue_receipt(db: Session, *, institution_id: str, payment_id: str, actor_id: Optional[str],
                  actor_role: Optional[str] = None) -> Optional[Receipt]:
    """Idempotently issue the digital receipt for a COMPLETED payment. Returns None (and logs) on failure."""
    try:
        existing = db.execute(select(Receipt).where(Receipt.institution_id == institution_id,
                                                    Receipt.payment_id == payment_id)).scalar_one_or_none()
        if existing is not None:
            return existing
        payment = db.execute(select(Payment).where(Payment.institution_id == institution_id,
                                                   Payment.id == payment_id)).scalar_one_or_none()
        if payment is None or payment.status != "COMPLETED":
            return None
        receipt = Receipt(institution_id=institution_id, payment_id=payment_id, order_id=payment.order_id,
                          receipt_number=opaque_reference("RCT"), status="ISSUED",
                          snapshot=build_snapshot(db, payment), issued_at=utcnow())
        with db.begin_nested():
            db.add(receipt)
            db.flush()
        audit.record_event(db, institution_id=institution_id, actor_id=actor_id, actor_role=actor_role,
                           event_type="RECEIPT_ISSUED", entity_type="Receipt", entity_id=receipt.id,
                           reference=receipt.receipt_number, metadata={"payment_id": payment_id})
        db.commit()
        DigitalReceiptDelivery().deliver(receipt.snapshot)
        return receipt
    except IntegrityError:  # concurrent issuer won: return theirs
        db.rollback()
        return db.execute(select(Receipt).where(Receipt.institution_id == institution_id,
                                                Receipt.payment_id == payment_id)).scalar_one_or_none()
    except Exception:  # receipt failure must never affect the completed payment
        db.rollback()
        log.exception("receipt issuance failed for payment %s (payment remains COMPLETED)", payment_id)
        return None
