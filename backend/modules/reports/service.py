"""Reporting module — published interface. Read-only composition over other modules' published interfaces."""
from __future__ import annotations

from sqlalchemy.orm import Session

from modules.audit import service as audit
from modules.devices import service as devices
from modules.ledger import service as ledger
from modules.merchants import service as merchants
from modules.payments import service as payments
from modules.users import service as users
from modules.wallets import service as wallets


def dashboard(db: Session, *, institution_id: str) -> dict:
    wallet_rows = wallets.list_wallets(db, institution_id=institution_id)
    entries = ledger.list_entries(db, institution_id=institution_id, limit=15)
    return {
        "totals": {
            "students": users.count_users(db, institution_id=institution_id, role=users.STUDENT),
            "merchants": len(merchants.list_merchants(db, institution_id=institution_id, actor_role=users.ADMIN)),
            "kiosks": len(devices.list_devices(db, institution_id=institution_id)),
            "products": merchants.count_products(db, institution_id=institution_id),
            "wallet_available_cu": wallets.total_available(db, institution_id=institution_id),
            "ledger_position_cu": ledger.total_position(db, institution_id=institution_id),
            "orders_by_status": merchants.order_summary(db, institution_id=institution_id),
            "payments_by_status": payments.payment_summary(db, institution_id=institution_id),
            "ledger_totals_by_event": ledger.totals_by_event_type(db, institution_id=institution_id),
        },
        "wallets": wallet_rows,
        "merchants": [{"id": m.id, "name": m.name, "category": m.category, "status": m.status}
                      for m in merchants.list_merchants(db, institution_id=institution_id, actor_role=users.ADMIN)],
        "kiosks": [{"id": d.id, "name": d.name, "merchant_id": d.merchant_id, "status": d.status}
                   for d in devices.list_devices(db, institution_id=institution_id)],
        "recent_payments": payments.list_payments(db, institution_id=institution_id, limit=15),
        "recent_ledger_entries": [{"id": e.id, "campus_user_id": e.campus_user_id, "event_type": e.event_type,
                                   "direction": e.direction, "amount_cu": e.amount_cu,
                                   "position_after_cu": e.position_after_cu, "origin": e.origin,
                                   "reference_type": e.reference_type, "created_at": e.created_at.isoformat()}
                                  for e in entries],
        "recent_audit": [{"event_type": a.event_type, "entity_type": a.entity_type, "entity_id": a.entity_id,
                          "created_at": a.created_at.isoformat(), "metadata": a.metadata}
                         for a in audit.list_events(db, institution_id=institution_id, limit=15)],
    }


def reconciliation(db: Session, *, institution_id: str) -> dict:
    """Detection only (MG-16 response policy is OPEN): compares every wallet with the authoritative ledger."""
    rows = [wallets.reconcile_wallet(db, institution_id=institution_id, campus_user_id=w["campus_user_id"])
            for w in wallets.list_wallets(db, institution_id=institution_id)]
    return {"wallets_checked": len(rows), "discrepancies": [r for r in rows if not r["consistent"]],
            "institution_ledger_position_cu": ledger.total_position(db, institution_id=institution_id),
            "sum_of_wallet_available_cu": wallets.total_available(db, institution_id=institution_id)}
