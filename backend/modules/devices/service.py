"""Device module — published interface (minimal P1 kiosk foundation, ADR-0007).

Merchant ≠ Kiosk: any number of kiosks may serve one merchant. The kiosk
authentication mechanism is OPEN, so no device credential scheme is invented:
a kiosk is a registered, tenant-scoped, activatable record that ordering
operations may reference and that the service validates.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.errors import ConflictError, ForbiddenError, NotFoundError, ValidationFailure
from modules.audit import service as audit
from modules.devices.models import Device

KIOSK = "KIOSK"
ACTIVE, INACTIVE = "ACTIVE", "INACTIVE"


@dataclass(frozen=True)
class DeviceView:
    id: str
    institution_id: str
    device_type: str
    name: str
    merchant_id: Optional[str]
    status: str


def _view(d: Device) -> DeviceView:
    return DeviceView(d.id, d.institution_id, d.device_type, d.name, d.merchant_id, d.status)


def register_kiosk(db: Session, *, institution_id: str, name: str, merchant_id: str,
                   actor_id: Optional[str] = None, actor_role: Optional[str] = None,
                   device_id: Optional[str] = None) -> DeviceView:
    name = name.strip()
    if not name:
        raise ValidationFailure("Device name required", code="INVALID_DEVICE")
    row = Device(institution_id=institution_id, device_type=KIOSK, name=name, merchant_id=merchant_id, status=ACTIVE)
    if device_id is not None:
        row.id = device_id
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError as exc:
        raise ConflictError("Device name already used or merchant unknown", code="DEVICE_REGISTRATION_FAILED") from exc
    audit.record_event(db, institution_id=institution_id, actor_id=actor_id, actor_role=actor_role,
                       event_type="DEVICE_REGISTERED", entity_type="Device", entity_id=row.id,
                       new={"name": name, "merchant_id": merchant_id, "type": KIOSK})
    return _view(row)


def _load(db: Session, institution_id: str, device_id: str) -> Device:
    row = db.execute(select(Device).where(Device.institution_id == institution_id, Device.id == device_id)).scalar_one_or_none()
    if row is None:
        raise NotFoundError("Device not found", code="DEVICE_NOT_FOUND")
    return row


def list_devices(db: Session, *, institution_id: str, merchant_id: Optional[str] = None) -> list[DeviceView]:
    stmt = select(Device).where(Device.institution_id == institution_id)
    if merchant_id:
        stmt = stmt.where(Device.merchant_id == merchant_id)
    return [_view(d) for d in db.execute(stmt.order_by(Device.name)).scalars()]


def set_status(db: Session, *, institution_id: str, device_id: str, status: str,
               actor_id: Optional[str] = None, actor_role: Optional[str] = None) -> DeviceView:
    if status not in (ACTIVE, INACTIVE):
        raise ValidationFailure("Status must be ACTIVE or INACTIVE", code="INVALID_STATUS")
    row = _load(db, institution_id, device_id)
    previous, row.status = row.status, status
    db.flush()
    audit.record_event(db, institution_id=institution_id, actor_id=actor_id, actor_role=actor_role,
                       event_type="DEVICE_STATUS_CHANGED", entity_type="Device", entity_id=row.id,
                       previous={"status": previous}, new={"status": status})
    return _view(row)


def require_active_kiosk_for_merchant(db: Session, *, institution_id: str, device_id: str, merchant_id: str) -> DeviceView:
    """The device must exist in this institution, be an ACTIVE kiosk, and serve this merchant."""
    row = _load(db, institution_id, device_id)
    if row.device_type != KIOSK or row.status != ACTIVE:
        raise ForbiddenError("Device is not an active kiosk", code="DEVICE_INACTIVE")
    if row.merchant_id != merchant_id:
        raise ForbiddenError("Device does not serve this merchant", code="DEVICE_MERCHANT_MISMATCH")
    return _view(row)


def update_device(db: Session, *, institution_id: str, device_id: str, actor_id: str, actor_role: str,
                  name: Optional[str] = None, status: Optional[str] = None) -> DeviceView:
    d = db.execute(select(Device).where(Device.institution_id == institution_id, Device.id == device_id).with_for_update()).scalar_one_or_none()
    if d is None:
        raise NotFoundError("Device not found", code="DEVICE_NOT_FOUND")
    if name is not None:
        d.name = name.strip()
    if status is not None:
        if status not in ("ACTIVE", "INACTIVE"):
            raise ValidationFailure("Invalid device status", code="INVALID_STATUS")
        d.status = status
    db.flush()
    audit.record_event(db, institution_id=institution_id, actor_id=actor_id, actor_role=actor_role,
                       event_type="DEVICE_UPDATED", entity_type="Device", entity_id=d.id,
                       new={"name": d.name, "status": d.status})
    return _view(d)
