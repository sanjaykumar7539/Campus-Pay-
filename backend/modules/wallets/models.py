from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base
from core.tenancy import TenantScoped
from shared.clock import utcnow
from shared.ids import new_id


class Wallet(TenantScoped, Base):
    """The customer's spendable-value representation (Operating Model §3.4).

    ``available_cu`` is NOT a source of truth: it must always equal the
    customer's latest Institution Ledger position. Only the Wallet service may
    change it, only in step with a ledger entry (ORM guard here + a database
    trigger installed by migration 0002).
    """

    __tablename__ = "wallets"
    __table_args__ = (CheckConstraint("available_cu >= 0", name="ck_wallets_available_non_negative"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    institution_id: Mapped[str] = mapped_column(ForeignKey("institutions.id"), nullable=False, index=True)
    campus_user_id: Mapped[str] = mapped_column(ForeignKey("campus_users.id"), unique=True, nullable=False)
    available_cu: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class WalletTransaction(TenantScoped, Base):
    """Wallet-side movement record. Non-authoritative: each row references the
    authoritative ledger entry that caused it (`ledger_entry_id`, unique)."""

    __tablename__ = "wallet_transactions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    institution_id: Mapped[str] = mapped_column(ForeignKey("institutions.id"), nullable=False, index=True)
    wallet_id: Mapped[str] = mapped_column(ForeignKey("wallets.id"), nullable=False, index=True)
    ledger_entry_id: Mapped[str] = mapped_column(ForeignKey("ledger_entries.id"), unique=True, nullable=False)
    payment_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # opaque reference, no FK
    type: Mapped[str] = mapped_column(String(16), nullable=False)  # RECHARGE | DEBIT
    amount_cu: Mapped[int] = mapped_column(BigInteger, nullable=False)
    balance_before_cu: Mapped[int] = mapped_column(BigInteger, nullable=False)
    balance_after_cu: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String, default="COMPLETED", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
