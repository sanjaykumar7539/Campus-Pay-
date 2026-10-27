import pytest

from tests.helpers import audit_types, balance, ledger_count, pay, place_order, sql

ARUN, PIN = "EGS-STD-0001", "4826"


def _paid(w, cid=ARUN):
    o = place_order(w, cid, {"Tea": 1}).json()["data"]
    assert pay(w, o["id"], cid, PIN).status_code == 200
    return o["id"]


def _step(w, oid, action, headers=None):
    return w.client().post(f"/api/v1/orders/{oid}/fulfillment/{action}", headers=headers or w.staff)


def test_fulfillment_follows_paid_preparing_ready_collected(world):
    oid = _paid(world)
    seen = []
    for action, expected in (("prepare", "PREPARING"), ("ready", "READY"), ("collect", "COLLECTED")):
        r = _step(world, oid, action)
        assert r.status_code == 200, r.text
        seen.append(r.json()["data"]["fulfillment"]["status"])
        assert r.json()["data"]["fulfillment"]["status"] == expected
    assert seen == ["PREPARING", "READY", "COLLECTED"]
    types = audit_types(world)
    for e in ("FULFILLMENT_STARTED", "FULFILLMENT_READY", "FULFILLMENT_COLLECTED"):
        assert e in types


@pytest.mark.parametrize("skip", [("ready",), ("collect",), ("prepare", "collect")])
def test_invalid_transitions_are_rejected(world, skip):
    oid = _paid(world)
    for action in skip[:-1]:
        assert _step(world, oid, action).status_code == 200
    r = _step(world, oid, skip[-1])
    assert r.status_code == 409 and r.json()["error"]["code"] == "INVALID_FULFILLMENT_TRANSITION"


def test_no_backward_or_repeated_transition(world):
    oid = _paid(world)
    for a in ("prepare", "ready", "collect"):
        _step(world, oid, a)
    for a in ("prepare", "ready", "collect"):
        assert _step(world, oid, a).status_code == 409


def test_unpaid_order_has_no_fulfillment(world):
    o = place_order(world, ARUN, {"Tea": 1}).json()["data"]
    r = _step(world, o["id"], "prepare")
    assert r.status_code == 409 and r.json()["error"]["code"] == "ORDER_NOT_PAID"


def test_merchant_queue_lists_paid_orders_by_fulfillment_status(world):
    a, b = _paid(world), _paid(world, "EGS-STD-0002")
    _step(world, a, "prepare")
    c = world.client()
    paid = c.get("/api/v1/merchant/orders?fulfillment_status=PAID", headers=world.staff).json()["data"]
    prep = c.get("/api/v1/merchant/orders?fulfillment_status=PREPARING", headers=world.staff).json()["data"]
    assert [o["id"] for o in paid] == [b] and [o["id"] for o in prep] == [a]


def test_fulfillment_never_touches_wallet_ledger_or_payment(world):
    oid = _paid(world)
    ledger_before, bal = ledger_count(world), balance(world, ARUN)
    pay_before = sql(world, "SELECT status, amount_cu FROM payments WHERE order_id=:o", o=oid)
    for a in ("prepare", "ready", "collect"):
        _step(world, oid, a)
    assert ledger_count(world) == ledger_before and balance(world, ARUN) == bal
    assert sql(world, "SELECT status, amount_cu FROM payments WHERE order_id=:o", o=oid) == pay_before


def test_staff_of_another_merchant_cannot_operate_this_orders_fulfillment(world):
    from modules.auth import service as auth
    from modules.merchants import service as merchants
    from modules.users import service as users
    db = world.session()
    try:
        m2 = merchants.create_merchant(db, institution_id=world.institution_id, name="Stationery", category="Stationery")
        s2 = users.create_user(db, institution_id=world.institution_id, name="Stationery Staff", role="MERCHANT_STAFF", unique_identifier="STF-2")
        auth.create_credential(db, institution_id=world.institution_id, campus_user_id=s2.id, username="staff2", password="Test-Password-123")
        merchants.assign_staff(db, institution_id=world.institution_id, campus_user_id=s2.id, merchant_id=m2.id)
        db.commit()
    finally:
        db.close()
    oid = _paid(world)
    h2 = world.headers("staff2")
    r = _step(world, oid, "prepare", headers=h2)
    assert r.status_code == 403 and r.json()["error"]["code"] == "MERCHANT_SCOPE_VIOLATION"
    assert world.client().get(f"/api/v1/orders/{oid}", headers=h2).status_code == 403
    assert place_order(world, ARUN, {"Tea": 1}, merchant_id=m2.id).status_code == 403
    assert world.client().get("/api/v1/merchant/orders", headers=h2).json()["data"] == []


def test_merchant_staff_have_no_route_to_change_money_customers_or_roles(world):
    c, uid = world.client(), world.students[ARUN].id
    assert c.post("/api/v1/demo/wallet-funding", headers=world.staff, json={"campus_user_id": uid, "amount_cu": 500, "reference": "staff-fund-1"}).status_code == 403
    assert c.post("/api/v1/wallets", headers=world.staff, json={"campus_user_id": uid}).status_code == 403
    assert c.get("/api/v1/wallets", headers=world.staff).status_code == 403
    assert c.post("/api/v1/auth/payment-pin", headers=world.staff, json={"campus_user_id": uid, "pin": "1234"}).status_code == 403
    assert c.post("/api/v1/students", headers=world.staff, json={"name": "x", "unique_identifier": "X"}).status_code == 403
    assert c.get("/api/v1/students", headers=world.staff).status_code == 403
    assert c.get("/api/v1/reports/dashboard", headers=world.staff).status_code == 403
    assert c.get("/api/v1/audit", headers=world.staff).status_code == 403
    assert c.post("/api/v1/devices", headers=world.staff, json={"name": "k", "merchant_id": world.merchant_id}).status_code == 403
    assert balance(world, ARUN) == 500


def test_admin_is_not_unrestricted_financial_authority(world):
    """ADMIN cannot rewrite balances or ledger through any API route; only audited demo funding exists (flag-gated)."""
    c, uid = world.client(), world.students[ARUN].id
    for method, path in (("put", f"/api/v1/wallets/{uid}"), ("patch", f"/api/v1/wallets/{uid}"), ("delete", f"/api/v1/wallets/{uid}"),
                         ("post", "/api/v1/wallets/recharge"), ("post", "/api/v1/ledger"), ("delete", "/api/v1/ledger/x")):
        assert getattr(c, method)(path, headers=world.admin).status_code in (404, 405)
