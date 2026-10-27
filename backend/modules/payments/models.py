from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, BigInteger, CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base
from core.tenancy import TenantScoped
from shared.clock import utcnow
from shared.ids import new_id


class Payment(TenantScoped, Base):
    """Financial authorisation/completion of a purchase. INITIATED -> COMPLETED | FAILED.

    Separate from Order, Receipt and Fulfillment. `reference` is the idempotency key, unique PER INSTITUTION.
    """

    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint("institution_id", "reference", name="uq_payments_inst_reference"),
        CheckConstraint("amount_cu > 0", name="ck_payments_amount_positive"),
        # Database backstop: an order can have at most ONE completed payment, whatever the idempotency keys.
        Index("uq_payments_order_completed", "order_id", unique=True,
              postgresql_where=text("status = 'COMPLETED'"), sqlite_where=text("status = 'COMPLETED'")),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    institution_id: Mapped[str] = mapped_column(ForeignKey("institutions.id"), nullable=False, index=True)
    # Nullable ONLY because legacy MVP FAILED attempts for unidentified students have no subject; P1 always sets both.
    campus_user_id: Mapped[Optional[str]] = mapped_column(ForeignKey("campus_users.id"), nullable=True)
    merchant_id: Mapped[Optional[str]] = mapped_column(ForeignKey("merchants.id"), nullable=True)
    wallet_id: Mapped[Optional[str]] = mapped_column(ForeignKey("wallets.id"), nullable=True)
    order_id: Mapped[Optional[str]] = mapped_column(ForeignKey("orders.id"), nullable=True)
    device_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="ORDER")  # ORDER | LEGACY_MANUAL
    amount_cu: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="INITIATED")
    reference: Mapped[str] = mapped_column(String(128), nullable=False)
    item_description: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    failure_reason: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class Receipt(TenantScoped, Base):
    """Digital receipt: proof/output of a COMPLETED payment (separate concern; physical printing deferred)."""

    __tablename__ = "receipts"
    __table_args__ = (UniqueConstraint("institution_id", "receipt_number", name="uq_receipts_inst_number"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    institution_id: Mapped[str] = mapped_column(ForeignKey("institutions.id"), nullable=False, index=True)
    payment_id: Mapped[str] = mapped_column(ForeignKey("payments.id"), unique=True, nullable=False)
    order_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    receipt_number: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ISSUED")
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
