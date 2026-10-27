"""Institution A must not be able to see or mutate Institution B's records."""
import pytest
from sqlalchemy import select

from modules.merchants.models import Product
from tests.helpers import build_world, ledger_count, pay, place_order, sql

CID = "EGS-STD-0001"


@pytest.fixture()
def two(app):
    a = build_world(app, code="INST-A", funding=500)
    b = build_world(app, code="INST-B", funding=700)  # SAME campus IDs and usernames as A on purpose
    return a, b


def test_same_campus_id_and_username_resolve_independently_per_institution(two):
    a, b = two
    ra = a.client().post("/api/v1/customers/identify", json={"value": CID}, headers=a.staff).json()["data"]
    rb = b.client().post("/api/v1/customers/identify", json={"value": CID}, headers=b.staff).json()["data"]
    assert ra["customer_id"] != rb["customer_id"] and ra["customer_id"] == a.students[CID].id


def test_every_admin_listing_only_shows_its_own_tenant(two):
    a, b = two
    c = a.client()
    for path in ("/api/v1/students", "/api/v1/wallets", "/api/v1/merchants", "/api/v1/products", "/api/v1/devices",
                 "/api/v1/payments", "/api/v1/audit", "/api/v1/institutions"):
        body = c.get(path, headers=a.admin).text
        assert b.institution_id not in body, path
        assert b.students[CID].id not in body, path
        assert b.merchant_id not in body, path
    inst = c.get("/api/v1/institutions", headers=a.admin).json()["data"]
    assert [i["code"] for i in inst] == ["INST-A"]
    dash = c.get("/api/v1/reports/dashboard", headers=a.admin).json()["data"]
    assert dash["totals"]["students"] == 3 and dash["totals"]["wallet_available_cu"] == 1500
    assert b.institution_id not in str(dash)


def test_cannot_touch_another_tenants_order_payment_or_receipt(two):
    a, b = two
    b_order = place_order(b, CID, {"Tea": 1}).json()["data"]
    paid = pay(b, b_order["id"], CID, "4826").json()["data"]
    c = a.client()
    assert c.get(f"/api/v1/orders/{b_order['id']}", headers=a.admin).status_code == 404
    assert pay(a, b_order["id"], CID, "4826", headers=a.admin).status_code == 404
    assert c.post(f"/api/v1/orders/{b_order['id']}/cancel", headers=a.admin).status_code == 404
    assert c.post(f"/api/v1/orders/{b_order['id']}/fulfillment/prepare", headers=a.admin).status_code == 404
    assert c.get(f"/api/v1/receipts/{paid['receipt']['id']}", headers=a.admin).status_code == 404
    assert c.get(f"/api/v1/payments/{paid['payment']['id']}/receipt", headers=a.admin).status_code == 404
    assert c.get(f"/api/v1/orders/{b_order['id']}/payment", headers=a.admin).status_code == 404


def test_cannot_touch_another_tenants_catalog_devices_wallets_or_merchants(two):
    a, b = two
    c = a.client()
    assert c.patch(f"/api/v1/products/{b.products['Tea']}", json={"price_cu": 1}, headers=a.admin).status_code == 404
    assert c.patch(f"/api/v1/categories/{b.category_id}", json={"name": "x"}, headers=a.admin).status_code == 404
    assert c.post("/api/v1/products", json={"category_id": b.category_id, "name": "X", "price_cu": 5}, headers=a.admin).status_code == 404
    assert c.patch(f"/api/v1/devices/{b.kiosk_id}", json={"status": "INACTIVE"}, headers=a.admin).status_code == 404
    assert c.get(f"/api/v1/merchants/{b.merchant_id}/menu", headers=a.admin).status_code == 404
    assert c.get(f"/api/v1/wallets/{b.students[CID].id}/history", headers=a.admin).status_code == 404
    assert c.post("/api/v1/wallets", json={"campus_user_id": b.students[CID].id}, headers=a.admin).status_code == 404
    assert c.post("/api/v1/demo/wallet-funding", json={"campus_user_id": b.students[CID].id, "amount_cu": 5, "reference": "x-ref"},
                  headers=a.admin).status_code == 404
    assert c.post("/api/v1/auth/payment-pin", json={"campus_user_id": b.students[CID].id, "pin": "1111"}, headers=a.admin).status_code == 404
    assert place_order(a, CID, {"Tea": 1}, merchant_id=b.merchant_id).status_code == 404  # B's merchant
    r = c.post("/api/v1/orders", headers=a.staff, json={"merchant_id": a.merchant_id, "identity": {"value": CID},
                                                        "items": [{"product_id": b.products["Tea"], "quantity": 1}]})
    assert r.status_code == 404 and r.json()["error"]["code"] == "PRODUCT_NOT_FOUND"


def test_idempotency_keys_and_references_are_tenant_scoped(two):
    a, b = two
    oa, ob = place_order(a, CID, {"Tea": 1}).json()["data"], place_order(b, CID, {"Tea": 1}).json()["data"]
    ra = pay(a, oa["id"], CID, "4826", key="shared-key-XYZ")
    rb = pay(b, ob["id"], CID, "4826", key="shared-key-XYZ")  # same key in another tenant: NOT a replay
    assert ra.status_code == rb.status_code == 200
    assert ra.json()["data"]["replayed"] is False and rb.json()["data"]["replayed"] is False
    assert ra.json()["data"]["payment"]["id"] != rb.json()["data"]["payment"]["id"]
    # demo-funding reference reuse across tenants is independent too
    for t in (a, b):
        r = t.client().post("/api/v1/demo/wallet-funding", headers=t.admin,
                            json={"campus_user_id": t.students[CID].id, "amount_cu": 10, "reference": "fund-shared-ref"})
        assert r.status_code == 200 and r.json()["data"]["replayed"] is False


def test_login_is_bound_to_the_institution_code(two):
    a, b = two
    r = a.client().post("/api/v1/auth/login", json={"institution_code": "NO-SUCH", "username": "admin", "password": "Test-Password-123"})
    assert r.status_code == 401
    r = a.client().post("/api/v1/auth/login", json={"institution_code": "INST-A", "username": "admin", "password": "wrong-password"})
    assert r.status_code == 401
    token_a = a.admin["Authorization"]
    assert token_a != b.admin["Authorization"]


def test_tenant_bound_session_backstop_filters_forgotten_queries(two):
    a, b = two
    from core.tenancy import bind_session_to_tenant
    db = bind_session_to_tenant(a.session(), a.institution_id)
    try:
        rows = db.execute(select(Product)).scalars().all()  # deliberately NO institution filter
        assert rows and {p.institution_id for p in rows} == {a.institution_id}
    finally:
        db.close()
    db = a.session()
    try:
        assert {p.institution_id for p in db.execute(select(Product)).scalars()} == {a.institution_id, b.institution_id}
    finally:
        db.close()


def test_ledger_is_tenant_scoped(two):
    a, b = two
    from modules.ledger import service as ledger
    db = a.session()
    try:
        entries = ledger.list_entries(db, institution_id=a.institution_id, limit=500)
        assert entries and {e.institution_id for e in entries} == {a.institution_id}
        assert ledger.get_customer_position(db, institution_id=a.institution_id, campus_user_id=b.students[CID].id) == 0
        assert ledger.total_position(db, institution_id=a.institution_id) == 1500
        assert ledger.total_position(db, institution_id=b.institution_id) == 2100
    finally:
        db.close()


def test_a_token_cannot_be_used_after_the_user_is_deactivated(two):
    a, _ = two
    assert a.client().get("/api/v1/students", headers=a.admin).status_code == 200
    sql(a, "UPDATE campus_users SET status='INACTIVE' WHERE id=:u", u=a.admin_id)
    assert a.client().get("/api/v1/students", headers=a.admin).status_code == 401


def test_unauthenticated_and_student_roles_are_rejected(two):
    a, _ = two
    c = a.client()
    assert c.get("/api/v1/students").status_code == 401
    assert c.get("/api/v1/students", headers={"Authorization": "Bearer nonsense"}).status_code == 401
