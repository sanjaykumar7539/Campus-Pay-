from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base
from core.tenancy import TenantScoped
from shared.clock import utcnow
from shared.ids import new_id


class CampusUser(TenantScoped, Base):
    """Campus User (ARCHITECTURE.md §7.4): identity, profile, role and status.

    ``unique_identifier`` (the campus identifier) is unique **per institution**,
    never globally: the identity boundary is (Institution, identifier).
    """

    __tablename__ = "campus_users"
    __table_args__ = (UniqueConstraint("institution_id", "unique_identifier", name="uq_campus_users_inst_identifier"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    institution_id: Mapped[str] = mapped_column(ForeignKey("institutions.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    unique_identifier: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
