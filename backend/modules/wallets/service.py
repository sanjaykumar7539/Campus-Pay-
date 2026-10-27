"""Wallet module — published interface.

Wallet exclusively owns the wallet's available value. The ONLY way it changes
is `debit_for_purchase` / `credit_demo_funding`, each of which

    1. checks the wallet and reads the authoritative ledger position,
    2. records the Financial Event in the Institution Ledger,
    3. sets available value to the resulting ledger position,
    4. writes the wallet movement record and an audit event,

all inside the caller's transaction. Validation happens BEFORE any write, so a
refused operation leaves no trace on the wallet (Invariant 3).
"""
from __future__ import annotations

import contextvars
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import event, func, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import get_history as _attribute_history

from core.config import get_settings
from core.errors import ConflictError, DomainError, ForbiddenError, NotFoundError, PaymentRequiredError, ValidationFailure
from modules.audit import service as audit
from modules.ledger import service as ledger
from modules.users import service as users
from modules.wallets.models import Wallet, WalletTransaction
from shared.campus_units import CampusUnitError, validate_cu

ACTIVE = "ACTIVE"

__all__ = ["WalletView", "MovementResult", "WalletFinancialRefusal", "InsufficientBalanceError",
           "WalletInactiveError", "LedgerWalletDiscrepancyError", "WalletNotFoundError",
           "create_wallet", "get_wallet", "list_wallets", "debit_for_purchase", "credit_demo_funding",
           "get_movement_for_payment", "get_history", "total_available", "count_wallets", "reconcile_wallet"]


class WalletNotFoundError(NotFoundError):
    code = "WALLET_NOT_FOUND"


class WalletFinancialRefusal(DomainError):
    """An expected refusal raised BEFORE any write; state is untouched."""


class InsufficientBalanceError(WalletFinancialRefusal, PaymentRequiredError):
    code = "INSUFFICIENT_BALANCE"


class WalletInactiveError(WalletFinancialRefusal, ForbiddenError):
    code = "WALLET_INACTIVE"


class LedgerWalletDiscrepancyError(WalletFinancialRefusal, ConflictError):
    """Ledger position != wallet representation. The response policy is MG-16 (OPEN);
    the only safe technical behaviour is to fail closed, record nothing and audit."""

    code = "LEDGER_WALLET_DISCREPANCY"


@dataclass(frozen=True)
class WalletView:
    id: str
    institution_id: str
    campus_user_id: str
    available_cu: int
    status: str


@dataclass(frozen=True)
class MovementResult:
    wallet_id: str
    transaction_id: str
    ledger_entry_id: str
    type: str
    amount_cu: int
    balance_before_cu: int
    balance_after_cu: int
    replayed: bool = False


def _view(w: Wallet) -> WalletView:
    return WalletView(w.id, w.institution_id, w.campus_user_id, w.available_cu, w.status)


# -- the wallet-mutation guard -------------------------------------------------
_MUTATION_AUTHORISED: contextvars.ContextVar[bool] = contextvars.ContextVar("wallet_mutation_authorised", default=False)


@contextmanager
def _authorised_wallet_mutation():
    token = _MUTATION_AUTHORISED.set(True)
    try:
        yield
    finally:
        _MUTATION_AUTHORISED.reset(token)


@event.listens_for(Wallet, "before_update")
def _guard_wallet_value(_mapper, _conn, target: Wallet):
    if _attribute_history(target, "available_cu").has_changes() and not _MUTATION_AUTHORISED.get():
        raise ForbiddenError("Wallet available value can only change through an authorised Financial Event",
                             code="WALLET_DIRECT_MUTATION_FORBIDDEN")


# -- reads -------------------------------------------------------------------------

def _load(db: Session, institution_id: str, campus_user_id: str, *, for_update: bool = False) -> Wallet:
    stmt = select(Wallet).where(Wallet.institution_id == institution_id, Wallet.campus_user_id == campus_user_id)
    if for_update:
        stmt = stmt.with_for_update()
    wallet = db.execute(stmt).scalar_one_or_none()
    if wallet is None:
        raise WalletNotFoundError("Wallet not found for this Campus User")
    return wallet


def get_wallet(db: Session, *, institution_id: str, campus_user_id: str) -> WalletView:
    return _view(_load(db, institution_id, campus_user_id))


def list_wallets(db: Session, *, institution_id: str) -> list[dict]:
    """Wallets with customer identity, for administration views."""
    rows = db.execute(select(Wallet).where(Wallet.institution_id == institution_id)).scalars().all()
    people = {u.id: u for u in users.list_users(db, institution_id=institution_id)}
    out = []
    for w in rows:
        u = people.get(w.campus_user_id)
        out.append({"wallet_id": w.id, "campus_user_id": w.campus_user_id,
                    "campus_id": u.unique_identifier if u else None, "name": u.name if u else None,
                    "available_cu": w.available_cu, "status": w.status})
    return sorted(out, key=lambda r: r["campus_id"] or "")


def count_wallets(db: Session, *, institution_id: str) -> int:
    return int(db.execute(select(func.count()).select_from(Wallet).where(Wallet.institution_id == institution_id)).scalar_one())


def total_available(db: Session, *, institution_id: str) -> int:
    return int(db.execute(select(func.coalesce(func.sum(Wallet.available_cu), 0)).where(
        Wallet.institution_id == institution_id)).scalar_one())


def get_history(db: Session, *, institution_id: str, campus_user_id: str, limit: int = 50) -> list[dict]:
    wallet = _load(db, institution_id, campus_user_id)
    rows = db.execute(select(WalletTransaction).where(
        WalletTransaction.institution_id == institution_id, WalletTransaction.wallet_id == wallet.id
    ).order_by(WalletTransaction.created_at.desc()).limit(min(max(limit, 1), 200))).scalars()
    return [{"id": t.id, "type": t.type, "amount_cu": t.amount_cu, "balance_before_cu": t.balance_before_cu,
             "balance_after_cu": t.balance_after_cu, "payment_id": t.payment_id,
             "ledger_entry_id": t.ledger_entry_id, "created_at": t.created_at.isoformat()} for t in rows]


def get_movement_for_payment(db: Session, *, institution_id: str, payment_id: str) -> Optional[MovementResult]:
    t = db.execute(select(WalletTransaction).where(
        WalletTransaction.institution_id == institution_id, WalletTransaction.payment_id == payment_id,
        WalletTransaction.type == "DEBIT")).scalar_one_or_none()
    if t is None:
        return None
    return MovementResult(t.wallet_id, t.id, t.ledger_entry_id, t.type, t.amount_cu, t.balance_before_cu,
                          t.balance_after_cu, replayed=True)


def reconcile_wallet(db: Session, *, institution_id: str, campus_user_id: str) -> dict:
    """Compare the wallet representation with the authoritative ledger (detection only; MG-16 OPEN)."""
    wallet = _load(db, institution_id, campus_user_id)
    position = ledger.get_customer_position(db, institution_id=institution_id, campus_user_id=campus_user_id)
    chain = ledger.verify_customer_chain(db, institution_id=institution_id, campus_user_id=campus_user_id)
    return {"campus_user_id": campus_user_id, "wallet_available_cu": wallet.available_cu,
            "ledger_position_cu": position, "chain_ok": chain.ok, "consistent": chain.ok and position == wallet.available_cu}


# -- writes ----------------------------------------------------------------------------

def create_wallet(db: Session, *, institution_id: str, campus_user_id: str, actor_id: Optional[str] = None,
                  actor_role: Optional[str] = None) -> WalletView:
    customer = users.get_user(db, institution_id=institution_id, user_id=campus_user_id)
    if not customer.is_customer:
        raise ValidationFailure("Only Customers have wallets", code="NOT_A_CUSTOMER")
    existing = db.execute(select(Wallet).where(Wallet.campus_user_id == campus_user_id)).scalar_one_or_none()
    if existing is not None:
        raise ConflictError("Wallet already exists for this Campus User", code="WALLET_EXISTS")
    wallet = Wallet(institution_id=institution_id, campus_user_id=campus_user_id, available_cu=0, status=ACTIVE)
    db.add(wallet)
    db.flush()
    audit.record_event(db, institution_id=institution_id, actor_id=actor_id, actor_role=actor_role,
                       event_type="WALLET_CREATED", entity_type="Wallet", entity_id=wallet.id,
                       new={"available_cu": 0, "status": ACTIVE})
    return _view(wallet)


def _checked_wallet(db: Session, institution_id: str, campus_user_id: str, amount_cu: int, *, need_funds: bool) -> tuple[Wallet, int]:
    try:
        amount_cu = validate_cu(amount_cu)
    except CampusUnitError as exc:
        raise ValidationFailure(str(exc), code="INVALID_AMOUNT") from exc
    wallet = _load(db, institution_id, campus_user_id, for_update=True)
    if wallet.status != ACTIVE:
        raise WalletInactiveError("Wallet is not active")
    position = ledger.get_customer_position(db, institution_id=institution_id, campus_user_id=campus_user_id)
    if position != wallet.available_cu:
        # MG-16 (OPEN): fail closed. Nothing is written; the caller records the failure.
        raise LedgerWalletDiscrepancyError("Wallet does not match the Institution Ledger; operation blocked")
    if need_funds and position < amount_cu:
        raise InsufficientBalanceError("Insufficient wallet balance")
    return wallet, amount_cu


def _apply(db: Session, wallet: Wallet, entry: ledger.LedgerEntryView, txn_type: str,
           payment_id: Optional[str]) -> MovementResult:
    before = wallet.available_cu
    with _authorised_wallet_mutation():
        wallet.available_cu = entry.position_after_cu
        db.flush()
    txn = WalletTransaction(institution_id=wallet.institution_id, wallet_id=wallet.id, ledger_entry_id=entry.id,
                            payment_id=payment_id, type=txn_type, amount_cu=entry.amount_cu,
                            balance_before_cu=before, balance_after_cu=wallet.available_cu, status="COMPLETED")
    db.add(txn)
    db.flush()
    return MovementResult(wallet.id, txn.id, entry.id, txn_type, entry.amount_cu, before, wallet.available_cu)


def debit_for_purchase(db: Session, *, institution_id: str, campus_user_id: str, amount_cu: int, payment_id: str,
                       actor_id: Optional[str], actor_role: Optional[str] = None,
                       source_device_id: Optional[str] = None) -> MovementResult:
    """PURCHASE Financial Event: ledger first, then the wallet's available value is reduced."""
    wallet, amount_cu = _checked_wallet(db, institution_id, campus_user_id, amount_cu, need_funds=True)
    try:
        entry = ledger.record_financial_event(
            db, institution_id=institution_id, campus_user_id=campus_user_id, event_type=ledger.PURCHASE,
            direction=ledger.DEBIT, amount_cu=amount_cu, reference_type="PAYMENT", reference_id=payment_id,
            actor_id=actor_id, actor_role=actor_role, source_device_id=source_device_id)
    except ledger.InsufficientPositionError as exc:
        raise InsufficientBalanceError("Insufficient wallet balance") from exc
    result = _apply(db, wallet, entry, "DEBIT", payment_id)
    audit.record_event(db, institution_id=institution_id, actor_id=actor_id, actor_role=actor_role,
                       source_device_id=source_device_id, event_type="WALLET_DEBITED", entity_type="Wallet",
                       entity_id=wallet.id, previous={"available_cu": result.balance_before_cu},
                       new={"available_cu": result.balance_after_cu}, reference=payment_id,
                       metadata={"amount_cu": amount_cu, "ledger_entry_id": entry.id,
                                 "wallet_transaction_id": result.transaction_id})
    return result


def credit_demo_funding(db: Session, *, institution_id: str, campus_user_id: str, amount_cu: int, reference: str,
                        actor_id: Optional[str], actor_role: Optional[str] = None) -> MovementResult:
    """DEMO/seed funding — NOT the production recharge workflow (Operating Model §7; MG-03 OPEN).

    It is recorded in the Institution Ledger like any credit, flagged origin=DEMO,
    and can be switched off with CAMPUSPAY_DEMO_FUNDING. The approved production
    path (Institutional Payment → Payment Acknowledgement → Authorised Recharge)
    is deliberately not implemented.
    """
    if not get_settings().demo_funding_enabled:
        raise ForbiddenError("Demo funding is disabled in this environment", code="DEMO_FUNDING_DISABLED")
    reference = (reference or "").strip()
    if not reference:
        raise ValidationFailure("A funding reference is required", code="REFERENCE_REQUIRED")
    wallet, amount_cu = _checked_wallet(db, institution_id, campus_user_id, amount_cu, need_funds=False)
    try:
        entry = ledger.record_financial_event(
            db, institution_id=institution_id, campus_user_id=campus_user_id, event_type=ledger.RECHARGE,
            direction=ledger.CREDIT, amount_cu=amount_cu, reference_type="DEMO_FUNDING", reference_id=reference,
            actor_id=actor_id, actor_role=actor_role, origin=ledger.ORIGIN_DEMO,
            reason="DEMO/seed funding (not a production recharge)")
    except ledger.DuplicateFinancialEventError:
        existing = ledger.get_entry_for_reference(db, institution_id=institution_id, event_type=ledger.RECHARGE,
                                                  reference_type="DEMO_FUNDING", reference_id=reference)
        if existing and existing.campus_user_id == campus_user_id and existing.amount_cu == amount_cu:
            txn = db.execute(select(WalletTransaction).where(WalletTransaction.ledger_entry_id == existing.id)).scalar_one()
            return MovementResult(txn.wallet_id, txn.id, existing.id, txn.type, txn.amount_cu,
                                  txn.balance_before_cu, txn.balance_after_cu, replayed=True)
        raise ConflictError("Funding reference already used for a different operation",
                            code="IDEMPOTENCY_KEY_REUSED")
    result = _apply(db, wallet, entry, "RECHARGE", None)
    audit.record_event(db, institution_id=institution_id, actor_id=actor_id, actor_role=actor_role,
                       event_type="DEMO_FUNDING_APPLIED", entity_type="Wallet", entity_id=wallet.id,
                       previous={"available_cu": result.balance_before_cu}, new={"available_cu": result.balance_after_cu},
                       reference=reference, reason="demo/seed funding",
                       metadata={"amount_cu": amount_cu, "ledger_entry_id": entry.id, "origin": "DEMO"})
    return result


def credit_admin(db, *, institution_id, campus_user_id, amount_cu, reference, reason, actor_id, refund=False):
    """Audited manual credit; caller authenticates admin and validates original refund payment."""
    reference, reason = reference.strip(), reason.strip()
    if not reference or not reason:
        raise ValidationFailure("Reference and reason are required")
    wallet, amount_cu = _checked_wallet(db, institution_id, campus_user_id, amount_cu, need_funds=False)
    event_type = ledger.REFUND if refund else ledger.RECHARGE
    reference_type = "ADMIN_REFUND" if refund else "ADMIN_TOPUP"
    existing = ledger.get_entry_for_reference(db, institution_id=institution_id, event_type=event_type,
        reference_type=reference_type, reference_id=reference)
    if existing:
        if existing.campus_user_id != campus_user_id or existing.amount_cu != amount_cu:
            raise ConflictError("Reference already used for a different operation", code="IDEMPOTENCY_KEY_REUSED")
        txn = db.execute(select(WalletTransaction).where(WalletTransaction.ledger_entry_id == existing.id)).scalar_one()
        return MovementResult(txn.wallet_id, txn.id, existing.id, txn.type, txn.amount_cu,
            txn.balance_before_cu, txn.balance_after_cu, replayed=True)
    entry = ledger.record_financial_event(db, institution_id=institution_id, campus_user_id=campus_user_id,
        event_type=event_type, direction=ledger.CREDIT, amount_cu=amount_cu,
        reference_type=reference_type, reference_id=reference, actor_id=actor_id, actor_role="ADMIN",
        reason=reason, external_reference=None if refund else reference)
    result = _apply(db, wallet, entry, "REFUND" if refund else "RECHARGE", reference if refund else None)
    audit.record_event(db, institution_id=institution_id, actor_id=actor_id, actor_role="ADMIN",
        event_type="ADMIN_REFUND_ISSUED" if refund else "ADMIN_MONEY_ADDED", entity_type="Wallet", entity_id=wallet.id,
        previous={"available_cu":result.balance_before_cu},new={"available_cu":result.balance_after_cu},
        reference=reference,reason=reason,metadata={"amount_cu":amount_cu,"ledger_entry_id":entry.id})
    return result


def payment_refunded(db, *, institution_id, payment_id):
    return bool(ledger.get_entry_for_reference(db, institution_id=institution_id, event_type=ledger.REFUND,
        reference_type="ADMIN_REFUND", reference_id=payment_id))


def withdraw_admin(db, *, institution_id, campus_user_id, amount_cu, reference, reason, actor_id):
    """Admin-confirmed wallet cash-out; debit exactly once per institution/reference."""
    reference, reason = (reference or "").strip(), (reason or "").strip()
    if not reference or not reason:
        raise ValidationFailure("Withdrawal reference and reason are required")
    # Idempotency reference is scoped to institution, across all student accounts.
    existing = ledger.get_entry_for_reference(db, institution_id=institution_id,
        event_type=ledger.WALLET_WITHDRAWAL, reference_type="ADMIN_WALLET_WITHDRAWAL", reference_id=reference)
    if existing:
        if existing.campus_user_id != campus_user_id or existing.amount_cu != amount_cu:
            raise ConflictError("Withdrawal reference already used for a different operation", code="IDEMPOTENCY_KEY_REUSED")
        txn = db.execute(select(WalletTransaction).where(WalletTransaction.ledger_entry_id == existing.id)).scalar_one()
        return MovementResult(txn.wallet_id, txn.id, existing.id, txn.type, txn.amount_cu,
            txn.balance_before_cu, txn.balance_after_cu, replayed=True)
    wallet, amount_cu = _checked_wallet(db, institution_id, campus_user_id, amount_cu, need_funds=True)
    try:
        entry = ledger.record_financial_event(db, institution_id=institution_id, campus_user_id=campus_user_id,
            event_type=ledger.WALLET_WITHDRAWAL, direction=ledger.DEBIT, amount_cu=amount_cu,
            reference_type="ADMIN_WALLET_WITHDRAWAL", reference_id=reference,
            actor_id=actor_id, actor_role="ADMIN", reason=reason, external_reference=reference)
    except ledger.InsufficientPositionError as exc:
        raise InsufficientBalanceError("Insufficient wallet balance") from exc
    result = _apply(db, wallet, entry, "WITHDRAWAL", None)
    audit.record_event(db, institution_id=institution_id, actor_id=actor_id, actor_role="ADMIN",
        event_type="ADMIN_WALLET_WITHDRAWAL", entity_type="Wallet", entity_id=wallet.id,
        previous={"available_cu": result.balance_before_cu}, new={"available_cu": result.balance_after_cu},
        reference=reference, reason=reason, metadata={"amount_cu":amount_cu,"ledger_entry_id":entry.id})
    return result
