from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base
from core.tenancy import TenantScoped
from shared.clock import utcnow
from shared.ids import new_id


class LedgerEntry(TenantScoped, Base):
    """One Financial Event in the Institution Ledger (Operating Model §3.2, §3.9, §4.4).

    The Institution Ledger is the AUTHORITATIVE financial record. Entries are
    append-only (ORM guards + database triggers). A customer's financial
    position is the ``position_after_cu`` of their latest entry; the Wallet is
    only a representation of that position.
    """

    __tablename__ = "ledger_entries"
    __table_args__ = (
        UniqueConstraint("institution_id", "campus_user_id", "customer_sequence", name="uq_ledger_customer_sequence"),
        UniqueConstraint("institution_id", "event_type", "reference_type", "reference_id", name="uq_ledger_reference"),
        CheckConstraint("amount_cu > 0", name="ck_ledger_amount_positive"),
        CheckConstraint("position_before_cu >= 0 AND position_after_cu >= 0", name="ck_ledger_position_non_negative"),
        CheckConstraint(
            "(direction = 'CREDIT' AND position_after_cu = position_before_cu + amount_cu) OR "
            "(direction = 'DEBIT' AND position_after_cu = position_before_cu - amount_cu)",
            name="ck_ledger_position_arithmetic"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    institution_id: Mapped[str] = mapped_column(ForeignKey("institutions.id"), nullable=False, index=True)
    campus_user_id: Mapped[str] = mapped_column(ForeignKey("campus_users.id"), nullable=False)
    customer_sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)
    amount_cu: Mapped[int] = mapped_column(BigInteger, nullable=False)
    position_before_cu: Mapped[int] = mapped_column(BigInteger, nullable=False)
    position_after_cu: Mapped[int] = mapped_column(BigInteger, nullable=False)
    origin: Mapped[str] = mapped_column(String(16), default="STANDARD", nullable=False)  # STANDARD | DEMO
    reference_type: Mapped[str] = mapped_column(String(32), nullable=False)
    reference_id: Mapped[str] = mapped_column(String, nullable=False)
    external_reference: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    actor_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    actor_role: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    source_device_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
