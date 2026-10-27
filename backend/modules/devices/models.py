from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base
from core.tenancy import TenantScoped
from shared.clock import utcnow
from shared.ids import new_id


class Device(TenantScoped, Base):
    """Registered hardware endpoint (ARCHITECTURE.md §7.11). In P1 only ordering-station kiosks."""

    __tablename__ = "devices"
    __table_args__ = (UniqueConstraint("institution_id", "name", name="uq_devices_inst_name"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    institution_id: Mapped[str] = mapped_column(ForeignKey("institutions.id"), nullable=False, index=True)
    device_type: Mapped[str] = mapped_column(String(32), nullable=False, default="KIOSK")
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    # Device assignment: the merchant this ordering station serves (many kiosks per merchant).
    merchant_id: Mapped[Optional[str]] = mapped_column(ForeignKey("merchants.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
