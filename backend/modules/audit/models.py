from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base
from core.tenancy import TenantScoped
from shared.clock import utcnow
from shared.ids import new_id


class AuditLog(TenantScoped, Base):
    """Immutable record of a significant operational event (ARCHITECTURE.md §9.5).

    Rows are append-only: ORM guards + database triggers reject UPDATE/DELETE.
    """

    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    institution_id: Mapped[Optional[str]] = mapped_column(ForeignKey("institutions.id"), nullable=True)
    actor_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    entity_type: Mapped[str] = mapped_column(String, nullable=False)
    entity_id: Mapped[str] = mapped_column(String, nullable=False)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
