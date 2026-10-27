"""Test data builders that go through the modules' published services (never raw table writes)."""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Optional

from fastapi.testclient import TestClient

from modules.auth import service as auth
from modules.devices import service as devices
from modules.institutions import service as institutions
from modules.merchants import service as merchants
from modules.users import service as users
from modules.wallets import service as wallets

_counter = itertools.count(1)
PASSWORD = "Test-Password-123"
DEFAULT_PIN = "4826"


@dataclass
class Student:
    id: str
    campus_id: str
    name: str
    pin: str = DEFAULT_PIN


@dataclass
class Tenant:
    app: object
    institution_id: str
    code: str
    admin_id: str
    staff_id: str
    merchant_id: str
    kiosk_id: str
    students: dict = field(default_factory=dict)
    products: dict = field(default_factory=dict)
    category_id: str = ""
    inactive_merchant_id: str = ""
    _clients: dict = field(default_factory=dict)

    def client(self) -> TestClient:
        return TestClient(self.app)

    def headers(self, who: str) -> dict:
        if who not in self._clients:
            c = self.client()
            r = c.post("/api/v1/auth/login", json={"institution_code": self.code, "username": who, "password": PASSWORD})
            assert r.status_code == 200, r.text
            self._clients[who] = {"Authorization": "Bearer " + r.json()["data"]["access_token"]}
        return self._clients[who]

    @property
    def admin(self) -> dict:
        return self.headers("admin")

    @property
    def staff(self) -> dict:
        return self.headers("staff")

    def session(self):
        return self.app.state.session_factory()


def build_world(app, *, code: Optional[str] = None, funding: int = 500, students: int = 3,
                pin: str = DEFAULT_PIN, campus_prefix: str = "EGS-STD") -> Tenant:
    n = next(_counter)
    code = code or f"TEST-INST-{n}"
    db = app.state.session_factory()
    try:
        inst = institutions.create_institution(db, name=f"Institution {n}", code=code)
        admin = users.create_user(db, institution_id=inst.id, name="Admin", role=users.ADMIN, unique_identifier=f"ADM-{n}")
        staff = users.create_user(db, institution_id=inst.id, name="Canteen Staff", role=users.MERCHANT_STAFF,
                                  unique_identifier=f"STF-{n}")
        auth.create_credential(db, institution_id=inst.id, campus_user_id=admin.id, username="admin", password=PASSWORD)
        auth.create_credential(db, institution_id=inst.id, campus_user_id=staff.id, username="staff", password=PASSWORD)
        main = merchants.create_merchant(db, institution_id=inst.id, name="Main Canteen", category="Canteen")
        closed = merchants.create_merchant(db, institution_id=inst.id, name="Old Print Shop", category="Stationery",
                                           status="INACTIVE")
        merchants.assign_staff(db, institution_id=inst.id, campus_user_id=staff.id, merchant_id=main.id)
        kiosk = devices.register_kiosk(db, institution_id=inst.id, name="KIOSK-1", merchant_id=main.id)
        cat = merchants.create_category(db, institution_id=inst.id, merchant_id=main.id, name="Meals", display_order=1,
                                        actor_user_id=admin.id, actor_role=users.ADMIN)
        tenant = Tenant(app, inst.id, code, admin.id, staff.id, main.id, kiosk.id, category_id=cat["id"],
                        inactive_merchant_id=closed.id)
        for name, price in (("Veg Meal", 60), ("Tea", 10), ("Samosa", 15)):
            p = merchants.create_product(db, institution_id=inst.id, category_id=cat["id"], name=name, price_cu=price,
                                         description=None, actor_user_id=admin.id, actor_role=users.ADMIN)
            tenant.products[name] = p.id
        for i in range(1, students + 1):
            cid = f"{campus_prefix}-{i:04d}"
            u = users.create_user(db, institution_id=inst.id, name=f"Student {i}", role=users.STUDENT, unique_identifier=cid)
            wallets.create_wallet(db, institution_id=inst.id, campus_user_id=u.id)
            auth.set_payment_pin(db, institution_id=inst.id, campus_user_id=u.id, pin=pin, actor_id=admin.id)
            if funding:
                wallets.credit_demo_funding(db, institution_id=inst.id, campus_user_id=u.id, amount_cu=funding,
                                            reference=f"seed-{code}-{cid}", actor_id=admin.id)
            tenant.students[cid] = Student(u.id, cid, u.name, pin)
        db.commit()
    finally:
        db.close()
    return tenant


def place_order(t: Tenant, campus_id: str, items: dict, *, key: Optional[str] = None, device: bool = True,
                merchant_id: Optional[str] = None):
    """items: {product name: quantity}. Returns the raw response."""
    import uuid
    headers = dict(t.staff)
    if device:
        headers["X-Device-Id"] = t.kiosk_id
    body = {"merchant_id": merchant_id or t.merchant_id, "identity": {"kind": "CAMPUS_ID", "value": campus_id},
            "items": [{"product_id": t.products[n], "quantity": q} for n, q in items.items()],
            "client_request_key": key or f"order-{uuid.uuid4()}"}
    return t.client().post("/api/v1/orders", json=body, headers=headers)


def pay(t: Tenant, order_id: str, campus_id: str, pin: str, *, key: Optional[str] = None, headers: Optional[dict] = None):
    import uuid
    h = dict(headers or t.staff)
    h["Idempotency-Key"] = key or f"pay-{uuid.uuid4()}"
    return t.client().post(f"/api/v1/orders/{order_id}/pay", json={"identity": {"kind": "CAMPUS_ID", "value": campus_id}, "pin": pin}, headers=h)


def balance(t: Tenant, campus_id: str) -> int:
    db = t.session()
    try:
        return wallets.get_wallet(db, institution_id=t.institution_id, campus_user_id=t.students[campus_id].id).available_cu
    finally:
        db.close()


def sql(t: Tenant, statement: str, **params):
    """Raw SQL against the tenant's database (tests only: used to simulate tampering/legacy states)."""
    from sqlalchemy import text
    db = t.session()
    try:
        result = db.execute(text(statement), params)
        rows = result.fetchall() if result.returns_rows else None
        db.commit()
        return rows
    finally:
        db.close()


def audit_types(t: Tenant, limit: int = 500) -> list[str]:
    r = t.client().get(f"/api/v1/audit?limit={limit}", headers=t.admin)
    assert r.status_code == 200, r.text
    return [e["event_type"] for e in r.json()["data"]]


def ledger_count(t: Tenant, event_type: Optional[str] = None) -> int:
    q = "SELECT COUNT(*) FROM ledger_entries WHERE institution_id=:i"
    if event_type:
        return sql(t, q + " AND event_type=:e", i=t.institution_id, e=event_type)[0][0]
    return sql(t, q, i=t.institution_id)[0][0]


def add_product(t: Tenant, name: str, price: int, **kw):
    db = t.session()
    try:
        p = merchants.create_product(db, institution_id=t.institution_id, category_id=t.category_id, name=name,
                                     price_cu=price, description=None, actor_user_id=t.admin_id, actor_role="ADMIN", **kw)
        db.commit()
        t.products[name] = p.id
        return p.id
    finally:
        db.close()
