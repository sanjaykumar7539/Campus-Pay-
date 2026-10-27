import pytest
from sqlalchemy import text

from tests.helpers import add_product, audit_types, balance, ledger_count, pay, place_order, sql

ARUN = "EGS-STD-0001"
PIN = "4826"


def _order(w, cid=ARUN, items=None):
    r = place_order(w, cid, items or {"Veg Meal": 1, "Tea": 2})
    assert r.status_code == 201, r.text
    return r.json()["data"]


def test_successful_purchase_creates_every_required_record(world):
    order = _order(world)
    r = pay(world, order["id"], ARUN, PIN)
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["payment"]["status"] == "COMPLETED" and d["payment"]["amount_cu"] == 80
    assert (d["balance_before_cu"], d["balance_after_cu"]) == (500, 420)
    assert balance(world, ARUN) == 420
    # ledger: 1 funding + 1 purchase, purchase is the authoritative Financial Event
    assert ledger_count(world, "PURCHASE") == 1
    rows = sql(world, "SELECT direction, amount_cu, position_before_cu, position_after_cu, reference_type, reference_id "
                      "FROM ledger_entries WHERE event_type='PURCHASE' AND institution_id=:i", i=world.institution_id)
    assert rows[0][:4] == ("DEBIT", 80, 500, 420) and rows[0][4] == "PAYMENT" and rows[0][5] == d["payment"]["id"]
    # wallet movement references the ledger entry; exactly one debit per payment
    wt = sql(world, "SELECT COUNT(*) FROM wallet_transactions WHERE payment_id=:p AND type='DEBIT'", p=d["payment"]["id"])
    assert wt[0][0] == 1
    types = audit_types(world)
    for expected in ("ORDER_CREATED", "PAYMENT_INITIATED", "WALLET_DEBITED", "ORDER_PAID", "PAYMENT_COMPLETED", "RECEIPT_ISSUED"):
        assert expected in types


def test_payment_order_receipt_fulfillment_are_separate_states_that_coexist(world):
    order = _order(world)
    d = pay(world, order["id"], ARUN, PIN).json()["data"]
    assert d["payment"]["status"] == "COMPLETED"
    assert d["order"]["status"] == "PAID"
    assert d["receipt"]["status"] == "ISSUED"
    assert d["order"]["fulfillment"]["status"] == "PAID"
    c = world.client()
    prep = c.post(f"/api/v1/orders/{order['id']}/fulfillment/prepare", headers=world.staff).json()["data"]
    assert prep["fulfillment"]["status"] == "PREPARING" and prep["status"] == "PAID"
    pay_state = c.get(f"/api/v1/orders/{order['id']}/payment", headers=world.staff).json()["data"]
    assert pay_state["status"] == "COMPLETED"  # fulfillment progress never changes the financial state


def test_client_cannot_control_the_amount(world):
    order = _order(world)
    h = dict(world.staff, **{"Idempotency-Key": "amount-tamper-1"})
    r = world.client().post(f"/api/v1/orders/{order['id']}/pay", headers=h,
                            json={"identity": {"value": ARUN}, "pin": PIN, "amount_cu": 1})
    assert r.status_code == 422
    r = world.client().post("/api/v1/orders", headers=world.staff, json={
        "merchant_id": world.merchant_id, "identity": {"value": ARUN}, "total_cu": 1,
        "items": [{"product_id": world.products["Veg Meal"], "quantity": 1, "unit_price_cu": 1}]})
    assert r.status_code == 422
    assert balance(world, ARUN) == 500


def test_insufficient_balance_fails_without_touching_the_wallet(world):
    add_product(world, "Feast", 900)
    order = _order(world, items={"Feast": 1})
    before_ledger = ledger_count(world)
    r = pay(world, order["id"], ARUN, PIN)
    assert r.status_code == 402
    err = r.json()["error"]
    assert err["code"] == "INSUFFICIENT_BALANCE" and err["details"]["payment_status"] == "FAILED"
    assert balance(world, ARUN) == 500
    assert ledger_count(world) == before_ledger
    pay_row = sql(world, "SELECT status, failure_reason FROM payments WHERE id=:p", p=err["details"]["payment_id"])
    assert pay_row[0] == ("FAILED", "INSUFFICIENT_BALANCE")
    order_now = world.client().get(f"/api/v1/orders/{order['id']}", headers=world.staff).json()["data"]
    assert order_now["status"] == "CREATED" and order_now["fulfillment"] is None
    assert "PAYMENT_FAILED" in audit_types(world)


def test_invalid_customer_is_rejected(world):
    r = place_order(world, "EGS-STD-9999", {"Tea": 1})
    assert r.status_code == 404 and r.json()["error"]["code"] == "CUSTOMER_NOT_IDENTIFIED"
    order = _order(world)
    r = pay(world, order["id"], "EGS-STD-9999", PIN)
    assert r.status_code == 404 and r.json()["error"]["code"] == "CUSTOMER_NOT_IDENTIFIED"
    assert balance(world, ARUN) == 500


def test_customer_cannot_pay_another_customers_order(world):
    order = _order(world, "EGS-STD-0001")
    r = pay(world, order["id"], "EGS-STD-0002", PIN)  # student 2 knows their own valid PIN
    assert r.status_code == 403 and r.json()["error"]["code"] == "ORDER_CUSTOMER_MISMATCH"
    assert balance(world, "EGS-STD-0001") == 500 and balance(world, "EGS-STD-0002") == 500
    assert "PAYMENT_REJECTED" in audit_types(world)


def test_inactive_customer_cannot_order_or_pay(world):
    order = _order(world)
    sql(world, "UPDATE campus_users SET status='INACTIVE' WHERE unique_identifier=:c AND institution_id=:i", c=ARUN, i=world.institution_id)
    r = pay(world, order["id"], ARUN, PIN)
    assert r.status_code == 403 and r.json()["error"]["code"] == "CUSTOMER_INACTIVE"
    r = place_order(world, ARUN, {"Tea": 1})
    assert r.status_code == 403 and r.json()["error"]["code"] == "CUSTOMER_INACTIVE"
    assert balance(world, ARUN) == 500


def test_inactive_wallet_fails_and_is_recorded(world):
    order = _order(world)
    sql(world, "UPDATE wallets SET status='INACTIVE' WHERE campus_user_id=:u", u=world.students[ARUN].id)
    r = pay(world, order["id"], ARUN, PIN)
    assert r.status_code == 403 and r.json()["error"]["code"] == "WALLET_INACTIVE"
    assert r.json()["error"]["details"]["payment_status"] == "FAILED"
    assert balance(world, ARUN) == 500


def test_inactive_merchant_fails_at_order_and_at_payment(world):
    r = place_order(world, ARUN, {"Tea": 1}, merchant_id=world.inactive_merchant_id)
    assert r.status_code in (403, 409)
    order = _order(world)
    sql(world, "UPDATE merchants SET status='INACTIVE' WHERE id=:m", m=world.merchant_id)
    r = pay(world, order["id"], ARUN, PIN)
    assert r.status_code == 409 and r.json()["error"]["code"] == "MERCHANT_INACTIVE"
    assert balance(world, ARUN) == 500


def test_duplicate_request_replays_without_a_second_debit(world):
    order = _order(world)
    r1 = pay(world, order["id"], ARUN, PIN, key="dup-key-0001")
    r2 = pay(world, order["id"], ARUN, PIN, key="dup-key-0001")
    assert r1.status_code == r2.status_code == 200
    assert r2.json()["data"]["replayed"] is True
    assert r1.json()["data"]["payment"]["id"] == r2.json()["data"]["payment"]["id"]
    assert r2.json()["data"]["balance_after_cu"] == 420
    assert balance(world, ARUN) == 420 and ledger_count(world, "PURCHASE") == 1


def test_already_paid_order_cannot_be_paid_again_with_a_new_key(world):
    order = _order(world)
    assert pay(world, order["id"], ARUN, PIN, key="first-key-01").status_code == 200
    r = pay(world, order["id"], ARUN, PIN, key="second-key-2")
    assert r.status_code == 409 and r.json()["error"]["code"] == "ORDER_ALREADY_PAID"
    assert balance(world, ARUN) == 420 and ledger_count(world, "PURCHASE") == 1


def test_idempotency_key_reused_for_another_order_is_a_conflict(world):
    o1, o2 = _order(world), _order(world, items={"Tea": 1})
    assert pay(world, o1["id"], ARUN, PIN, key="shared-key-1").status_code == 200
    r = pay(world, o2["id"], ARUN, PIN, key="shared-key-1")
    assert r.status_code == 409 and r.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"
    assert balance(world, ARUN) == 420


def test_idempotency_key_is_required(world):
    order = _order(world)
    r = world.client().post(f"/api/v1/orders/{order['id']}/pay", headers=world.staff,
                            json={"identity": {"value": ARUN}, "pin": PIN})
    assert r.status_code == 422 and r.json()["error"]["code"] == "IDEMPOTENCY_KEY_REQUIRED"


def test_price_change_after_order_does_not_change_the_order(world):
    order = _order(world, items={"Veg Meal": 1})
    assert order["total_cu"] == 60
    r = world.client().patch(f"/api/v1/products/{world.products['Veg Meal']}", json={"price_cu": 999}, headers=world.staff)
    assert r.status_code == 200
    d = pay(world, order["id"], ARUN, PIN).json()["data"]
    assert d["payment"]["amount_cu"] == 60 and d["balance_after_cu"] == 440
    assert d["receipt"]["lines"][0]["unit_price_cu"] == 60  # snapshot, not the new price


def test_cancelled_order_cannot_be_paid_and_has_no_financial_effect(world):
    order = _order(world)
    assert world.client().post(f"/api/v1/orders/{order['id']}/cancel", headers=world.staff).status_code == 200
    r = pay(world, order["id"], ARUN, PIN)
    assert r.status_code == 409 and r.json()["error"]["code"] == "ORDER_NOT_PAYABLE"
    assert balance(world, ARUN) == 500 and ledger_count(world, "PURCHASE") == 0


def test_receipt_failure_never_reverses_the_completed_payment(world, monkeypatch):
    import modules.payments.receipts as receipts
    order = _order(world)
    monkeypatch.setattr(receipts, "build_snapshot", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("printer on fire")))
    r = pay(world, order["id"], ARUN, PIN)
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["payment"]["status"] == "COMPLETED" and d["receipt"] is None and d["receipt_status"] == "NOT_ISSUED"
    assert balance(world, ARUN) == 420 and ledger_count(world, "PURCHASE") == 1
    monkeypatch.undo()
    r = world.client().get(f"/api/v1/payments/{d['payment']['id']}/receipt", headers=world.staff)
    assert r.status_code == 200 and r.json()["data"]["status"] == "ISSUED"
    again = world.client().get(f"/api/v1/payments/{d['payment']['id']}/receipt", headers=world.staff).json()["data"]
    assert again["id"] == r.json()["data"]["id"]  # idempotent: one receipt per payment


def test_failure_after_debit_rolls_the_whole_transaction_back(world, monkeypatch):
    from fastapi.testclient import TestClient
    import modules.merchants.service as merchants_service
    order = _order(world)
    monkeypatch.setattr(merchants_service, "mark_order_paid", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("db down")))
    c = TestClient(world.app, raise_server_exceptions=False)
    h = dict(world.staff, **{"Idempotency-Key": "boom-key-0001"})
    r = c.post(f"/api/v1/orders/{order['id']}/pay", headers=h, json={"identity": {"value": ARUN}, "pin": PIN})
    assert r.status_code == 500
    assert balance(world, ARUN) == 500 and ledger_count(world, "PURCHASE") == 0
    assert sql(world, "SELECT COUNT(*) FROM payments WHERE reference='boom-key-0001'")[0][0] == 0
    monkeypatch.undo()
    assert pay(world, order["id"], ARUN, PIN, key="boom-key-0001").status_code == 200  # safe to retry
    assert balance(world, ARUN) == 420  # 80 CU order debited exactly once after the retry
