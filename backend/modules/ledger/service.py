"""Institution Ledger — published interface (ADR-0004).

The ledger is the authoritative financial source of truth. Every
balance-affecting Financial Event is recorded here FIRST; the Wallet's
available value is then set to the resulting position by the Wallet module.

P1 supports the two Financial Events with approved workflows — RECHARGE
(demo funding only; production recharge is MG-03 OPEN) and PURCHASE. The other
event classes named by the Operating Model (ADJUSTMENT, REFUND, SETTLEMENT,
WALLET_STATUS_CHANGE) are recognised but rejected because their policies are
OPEN; the ledger structure already accommodates them (append-only, new event
per correction, original never altered — Operating Model §9.1).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy import event, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.errors import ConflictError, DomainError, PaymentRequiredError, PolicyOpenError, ValidationFailure
from modules.ledger.models import LedgerEntry
from shared.campus_units import CampusUnitError, validate_cu

RECHARGE = "RECHARGE"
PURCHASE = "PURCHASE"
ADJUSTMENT = "ADJUSTMENT"
REFUND = "REFUND"
SETTLEMENT = "SETTLEMENT"
WALLET_STATUS_CHANGE = "WALLET_STATUS_CHANGE"
WALLET_WITHDRAWAL = "WALLET_WITHDRAWAL"
ALL_EVENT_TYPES = frozenset({RECHARGE, PURCHASE, ADJUSTMENT, REFUND, SETTLEMENT, WALLET_STATUS_CHANGE, WALLET_WITHDRAWAL})
SUPPORTED_EVENT_TYPES = frozenset({RECHARGE, PURCHASE})

CREDIT = "CREDIT"
DEBIT = "DEBIT"

ORIGIN_STANDARD = "STANDARD"
ORIGIN_DEMO = "DEMO"


class ImmutableLedgerError(DomainError):
    status_code = 409
    code = "LEDGER_IMMUTABLE"


class InsufficientPositionError(PaymentRequiredError):
    code = "INSUFFICIENT_BALANCE"


class DuplicateFinancialEventError(ConflictError):
    code = "DUPLICATE_FINANCIAL_EVENT"


class ConcurrentFinancialUpdateError(ConflictError):
    code = "CONCURRENT_FINANCIAL_UPDATE"


@dataclass(frozen=True)
class LedgerEntryView:
    id: str
    institution_id: str
    campus_user_id: str
    customer_sequence: int
    event_type: str
    direction: str
    amount_cu: int
    position_before_cu: int
    position_after_cu: int
    origin: str
    reference_type: str
    reference_id: str
    actor_id: Optional[str]
    created_at: datetime


@dataclass(frozen=True)
class ChainVerification:
    ok: bool
    entries: int
    position_cu: int
    problem: Optional[str] = None


def _view(e: LedgerEntry) -> LedgerEntryView:
    return LedgerEntryView(e.id, e.institution_id, e.campus_user_id, e.customer_sequence, e.event_type,
                           e.direction, e.amount_cu, e.position_before_cu, e.position_after_cu, e.origin,
                           e.reference_type, e.reference_id, e.actor_id, e.created_at)


def _latest(db: Session, institution_id: str, campus_user_id: str) -> Optional[LedgerEntry]:
    return db.execute(
        select(LedgerEntry)
        .where(LedgerEntry.institution_id == institution_id, LedgerEntry.campus_user_id == campus_user_id)
        .order_by(LedgerEntry.customer_sequence.desc()).limit(1)
    ).scalar_one_or_none()


def get_customer_position(db: Session, *, institution_id: str, campus_user_id: str) -> int:
    """Customer Financial Position (Operating Model §3.3): latest ledger position, 0 if none."""
    latest = _latest(db, institution_id, campus_user_id)
    return latest.position_after_cu if latest else 0


def record_financial_event(
    db: Session, *, institution_id: str, campus_user_id: str, event_type: str, direction: str,
    amount_cu: int, reference_type: str, reference_id: str, actor_id: Optional[str],
    actor_role: Optional[str] = None, origin: str = ORIGIN_STANDARD,
    source_device_id: Optional[str] = None, reason: Optional[str] = None,
    external_reference: Optional[str] = None,
) -> LedgerEntryView:
    """Append one Financial Event and return it. Callers serialise per customer (Wallet row lock);
    the unique (customer, sequence) constraint is the database backstop against lost updates."""
    if event_type not in ALL_EVENT_TYPES:
        raise ValidationFailure(f"Unknown financial event type {event_type}", code="UNKNOWN_EVENT_TYPE")
    admin_refund = (event_type == REFUND and reference_type == "ADMIN_REFUND" and actor_role == "ADMIN" and direction == CREDIT and bool(reason))
    admin_withdrawal = (event_type == WALLET_WITHDRAWAL and reference_type == "ADMIN_WALLET_WITHDRAWAL"
        and actor_role == "ADMIN" and direction == DEBIT and bool(reason))
    if event_type not in SUPPORTED_EVENT_TYPES and not admin_refund and not admin_withdrawal:
        raise PolicyOpenError(f"{event_type} is a recognised Financial Event whose policy is OPEN "
                              "(Operating Model v0.2); it is not implemented in P1", code="FINANCIAL_EVENT_POLICY_OPEN")
    if direction not in (CREDIT, DEBIT):
        raise ValidationFailure("Invalid direction", code="INVALID_DIRECTION")
    try:
        amount_cu = validate_cu(amount_cu)
    except CampusUnitError as exc:
        raise ValidationFailure(str(exc), code="INVALID_AMOUNT") from exc

    latest = _latest(db, institution_id, campus_user_id)
    before = latest.position_after_cu if latest else 0
    sequence = (latest.customer_sequence if latest else 0) + 1
    after = before + amount_cu if direction == CREDIT else before - amount_cu
    if after < 0:
        raise InsufficientPositionError("Insufficient balance", code="INSUFFICIENT_BALANCE")

    entry = LedgerEntry(
        institution_id=institution_id, campus_user_id=campus_user_id, customer_sequence=sequence,
        event_type=event_type, direction=direction, amount_cu=amount_cu, position_before_cu=before,
        position_after_cu=after, origin=origin, reference_type=reference_type, reference_id=reference_id,
        external_reference=external_reference, actor_id=actor_id, actor_role=actor_role,
        source_device_id=source_device_id, reason=reason)
    try:
        with db.begin_nested():  # the savepoint owns the pending row, so a failed flush leaves the session usable
            db.add(entry)
            db.flush()
    except IntegrityError as exc:
        text = str(getattr(exc, "orig", exc))
        if "uq_ledger_reference" in text or "reference_id" in text:
            raise DuplicateFinancialEventError("Financial event already recorded for this reference") from exc
        raise ConcurrentFinancialUpdateError(
            "Concurrent financial update detected; nothing was recorded. Retry the operation.") from exc
    return _view(entry)


def list_entries(db: Session, *, institution_id: str, campus_user_id: Optional[str] = None,
                 limit: int = 100) -> list[LedgerEntryView]:
    stmt = select(LedgerEntry).where(LedgerEntry.institution_id == institution_id)
    if campus_user_id:
        stmt = stmt.where(LedgerEntry.campus_user_id == campus_user_id)
    stmt = stmt.order_by(LedgerEntry.created_at.desc(), LedgerEntry.customer_sequence.desc()).limit(min(max(limit, 1), 500))
    return [_view(e) for e in db.execute(stmt).scalars()]


def get_entry_for_reference(db: Session, *, institution_id: str, event_type: str, reference_type: str,
                            reference_id: str) -> Optional[LedgerEntryView]:
    row = db.execute(select(LedgerEntry).where(
        LedgerEntry.institution_id == institution_id, LedgerEntry.event_type == event_type,
        LedgerEntry.reference_type == reference_type, LedgerEntry.reference_id == reference_id)).scalar_one_or_none()
    return _view(row) if row else None


def verify_customer_chain(db: Session, *, institution_id: str, campus_user_id: str) -> ChainVerification:
    """Re-derive the position from the entries and check the chain is continuous."""
    rows = list(db.execute(select(LedgerEntry).where(
        LedgerEntry.institution_id == institution_id, LedgerEntry.campus_user_id == campus_user_id
    ).order_by(LedgerEntry.customer_sequence)).scalars())
    position = 0
    for expected_seq, row in enumerate(rows, start=1):
        if row.customer_sequence != expected_seq:
            return ChainVerification(False, len(rows), position, f"sequence gap at {expected_seq}")
        if row.position_before_cu != position:
            return ChainVerification(False, len(rows), position, f"broken chain at sequence {expected_seq}")
        position = row.position_after_cu
    signed = sum(r.amount_cu if r.direction == CREDIT else -r.amount_cu for r in rows)
    if signed != position:
        return ChainVerification(False, len(rows), position, "position does not equal signed sum of entries")
    return ChainVerification(True, len(rows), position)


def total_position(db: Session, *, institution_id: str) -> int:
    """Institution-wide sum of customer positions (credits minus debits)."""
    credits = db.execute(select(func.coalesce(func.sum(LedgerEntry.amount_cu), 0)).where(
        LedgerEntry.institution_id == institution_id, LedgerEntry.direction == CREDIT)).scalar_one()
    debits = db.execute(select(func.coalesce(func.sum(LedgerEntry.amount_cu), 0)).where(
        LedgerEntry.institution_id == institution_id, LedgerEntry.direction == DEBIT)).scalar_one()
    return int(credits) - int(debits)


def totals_by_event_type(db: Session, *, institution_id: str) -> dict[str, int]:
    rows = db.execute(select(LedgerEntry.event_type, func.coalesce(func.sum(LedgerEntry.amount_cu), 0))
                      .where(LedgerEntry.institution_id == institution_id).group_by(LedgerEntry.event_type))
    return {t: int(s) for t, s in rows}


@event.listens_for(LedgerEntry, "before_update")
def _ledger_no_update(*_):
    raise ImmutableLedgerError("Ledger entries are immutable; record a new Financial Event instead")


@event.listens_for(LedgerEntry, "before_delete")
def _ledger_no_delete(*_):
    raise ImmutableLedgerError("Ledger entries cannot be deleted")
