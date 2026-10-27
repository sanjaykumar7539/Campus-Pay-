from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base
from core.tenancy import TenantScoped
from shared.clock import utcnow
from shared.ids import new_id


class Credential(TenantScoped, Base):
    """Login credential of a staff/admin Campus User (ARCHITECTURE.md §7.2). Passwords are bcrypt-hashed."""

    __tablename__ = "credentials"
    __table_args__ = (UniqueConstraint("institution_id", "username", name="uq_credentials_inst_username"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    institution_id: Mapped[str] = mapped_column(ForeignKey("institutions.id"), nullable=False, index=True)
    campus_user_id: Mapped[str] = mapped_column(ForeignKey("campus_users.id"), unique=True, nullable=False)
    username: Mapped[str] = mapped_column(String(128), nullable=False)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE", nullable=False)
    token_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class PaymentPinCredential(TenantScoped, Base):
    """The customer's 4-digit payment-authorisation PIN (Operating Model §4.2).

    A PIN is NOT a password and NOT an identity: it authorises a financial
    action. Stored only as a slow salted hash; never returned or logged.
    """

    __tablename__ = "payment_pin_credentials"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    institution_id: Mapped[str] = mapped_column(ForeignKey("institutions.id"), nullable=False, index=True)
    campus_user_id: Mapped[str] = mapped_column(ForeignKey("campus_users.id"), unique=True, nullable=False)
    pin_hash: Mapped[str] = mapped_column(String, nullable=False)
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_failed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    pin_set_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE", nullable=False)
