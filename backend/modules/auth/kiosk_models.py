"""Persistent kiosk sessions and opaque scanner references; never biometric images."""
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, DateTime, JSON, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from core.database import Base
from core.tenancy import TenantScoped
from shared.ids import new_id
from shared.clock import utcnow


class KioskSession(TenantScoped, Base):
    __tablename__ = "kiosk_sessions"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    institution_id: Mapped[str] = mapped_column(ForeignKey("institutions.id"), index=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    revoked: Mapped[int] = mapped_column(Integer, default=0)
    authentication_mode: Mapped[str] = mapped_column(String(16), default="AUTO")
    receipt_mode: Mapped[str] = mapped_column(String(16), default="BROWSER")


class ScannerAgent(TenantScoped, Base):
    __tablename__ = "scanner_agents"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    institution_id: Mapped[str] = mapped_column(ForeignKey("institutions.id"), index=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), unique=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class FingerprintEnrollment(TenantScoped, Base):
    __tablename__ = "fingerprint_enrollments"
    __table_args__ = (UniqueConstraint("institution_id", "finger_ref"), UniqueConstraint("institution_id", "campus_user_id"))
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    institution_id: Mapped[str] = mapped_column(ForeignKey("institutions.id"), index=True)
    campus_user_id: Mapped[str] = mapped_column(ForeignKey("campus_users.id"))
    finger_ref: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE")
    enrolled_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class FingerprintChallenge(TenantScoped, Base):
    __tablename__ = "fingerprint_challenges"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    institution_id: Mapped[str] = mapped_column(ForeignKey("institutions.id"), index=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), index=True)
    session_id: Mapped[Optional[str]] = mapped_column(ForeignKey("kiosk_sessions.id"), nullable=True)
    auth_method: Mapped[str] = mapped_column(String(16), default="SCANNER")
    purpose: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(24), default="FIRST_SCAN")
    nonce: Mapped[str] = mapped_column(String(64))
    student_id: Mapped[Optional[str]] = mapped_column(ForeignKey("campus_users.id"), nullable=True)
    finger_ref: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    order_id: Mapped[Optional[str]] = mapped_column(ForeignKey("orders.id"), nullable=True)
    cart: Mapped[dict] = mapped_column(JSON, default=dict)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ScannerCapture(TenantScoped, Base):
    __tablename__ = "scanner_captures"
    __table_args__ = (UniqueConstraint("device_id", "capture_id"),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    institution_id: Mapped[str] = mapped_column(ForeignKey("institutions.id"), index=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"))
    challenge_id: Mapped[str] = mapped_column(ForeignKey("fingerprint_challenges.id"))
    capture_id: Mapped[str] = mapped_column(String(128))


class MobileCredential(TenantScoped, Base):
    __tablename__ = "mobile_credentials"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    institution_id: Mapped[str] = mapped_column(ForeignKey("institutions.id"), index=True)
    campus_user_id: Mapped[str] = mapped_column(ForeignKey("campus_users.id"), index=True)
    credential_id: Mapped[str] = mapped_column(String(2048), unique=True)
    public_key: Mapped[str] = mapped_column(String(8192))
    sign_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE")


class MobileCeremony(TenantScoped, Base):
    __tablename__ = "mobile_ceremonies"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    institution_id: Mapped[str] = mapped_column(ForeignKey("institutions.id"), index=True)
    owner_id: Mapped[str] = mapped_column(String)
    target_id: Mapped[str] = mapped_column(String)
    purpose: Mapped[str] = mapped_column(String(16))
    challenge: Mapped[str] = mapped_column(String(128))
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used: Mapped[int] = mapped_column(Integer, default=0)


class PrinterAgent(TenantScoped, Base):
    __tablename__ = "printer_agents"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    institution_id: Mapped[str] = mapped_column(ForeignKey("institutions.id"), index=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), unique=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

class PrintJob(TenantScoped, Base):
    __tablename__ = "print_jobs"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    institution_id: Mapped[str] = mapped_column(ForeignKey("institutions.id"), index=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), index=True)
    checkout_id: Mapped[str] = mapped_column(ForeignKey("fingerprint_challenges.id"), unique=True)
    snapshot: Mapped[dict] = mapped_column(JSON)
    state: Mapped[str] = mapped_column(String(16), default="QUEUED")
    claimed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
