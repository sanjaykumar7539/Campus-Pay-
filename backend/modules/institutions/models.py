from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base
from shared.clock import utcnow
from shared.ids import new_id


class Institution(Base):
    """Tenant root (ARCHITECTURE.md §7.3). Every business record belongs to exactly one Institution."""

    __tablename__ = "institutions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
