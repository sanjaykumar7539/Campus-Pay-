"""Concurrency safety of money movement.

Runs against PostgreSQL (the target architecture: real row locks, MVCC) whenever CAMPUSPAY_TEST_POSTGRES_URL is set,
and against SQLite. SQLite serialises writers (BEGIN IMMEDIATE), so a SQLite pass is NOT evidence of production
safety: the `postgres` parametrisation is the reference.
"""
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from tests.conftest import alembic_upgrade
from tests.helpers import add_product, balance, build_world, ledger_count, place_order, sql

PG_ADMIN_URL = os.getenv("CAMPUSPAY_TEST_POSTGRES_URL")
BACKENDS = ["sqlite", pytest.param("postgres", marks=[pytest.mark.postgres, pytest.mark.skipif(
    not PG_ADMIN_URL, reason="CAMPUSPAY_TEST_POSTGRES_URL not set")])]
ARUN, PIN = "EGS-STD-0001", "4826"


@pytest.fixture(params=BACKENDS)
def cworld(request, template_db, tmp_path):
    import shutil
    from app.main import create_app
    if request.param == "sqlite":
        db_file = tmp_path / "c.db"
        shutil.copy(template_db, db_file)
        application = create_app(f"sqlite:///{db_file}")
        cleanup = lambda: None
    else:
        name = f"cp_test_{uuid.uuid4().hex[:10]}"
        admin = create_engine(PG_ADMIN_URL, isolation_level="AUTOCOMMIT")
        with admin.connect() as c:
            c.execute(text(f"CREATE DATABASE {name}"))
        url = PG_ADMIN_URL.rsplit("/", 1)[0] + "/" + name
        alembic_upgrade(url)
        application = create_app(url)

        def cleanup():
            application.state.engine.dispose()
            with admin.connect() as c:
                c.execute(text(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)"))
    world = build_world(application, funding=500, students=2)
    world.backend = request.param
    yield world
    application.state.engine.dispose()
    cleanup()


def _race(n, fn):
    barrier = threading.Barrier(n)

    def run(i):
        barrier.wait()
        return fn(i)

    with ThreadPoolExecutor(max_workers=n) as pool:
        return list(pool.map(run, range(n)))


def _pay(w, order_id, key, cid=ARUN, pin=PIN):
    c = TestClient(w.app)
    r = c.post(f"/api/v1/orders/{order_id}/pay", headers=dict(w.staff, **{"Idempotency-Key": key}),
               json={"identity": {"value": cid}, "pin": pin})
    return r.status_code, r.json()


def _orders(w, name, n, cid=ARUN):
    return [place_order(w, cid, {name: 1}).json()["data"]["id"] for _ in range(n)]


def test_two_simultaneous_400_purchases_on_a_500_balance_only_one_succeeds(cworld):
    w = cworld
    add_product(w, "Feast400", 400)
    o1, o2 = _orders(w, "Feast400", 2)
    results = _race(2, lambda i: _pay(w, (o1, o2)[i], f"race-key-{i}-{uuid.uuid4().hex[:6]}"))
    codes = sorted(s for s, _ in results)
    assert codes == [200, 402], results
    assert [b["error"]["code"] for s, b in results if s == 402] == ["INSUFFICIENT_BALANCE"]
    assert balance(w, ARUN) == 100 and ledger_count(w, "PURCHASE") == 1


def test_many_concurrent_purchases_never_overspend_and_chain_stays_consistent(cworld):
    w = cworld
    add_product(w, "Meal100", 100)
    orders = _orders(w, "Meal100", 8)
    results = _race(8, lambda i: _pay(w, orders[i], f"many-{i}-{uuid.uuid4().hex[:6]}"))
    ok = [r for r in results if r[0] == 200]
    refused = [r for r in results if r[0] == 402]
    assert len(ok) == 5 and len(refused) == 3, [s for s, _ in results]
    assert balance(w, ARUN) == 0 and ledger_count(w, "PURCHASE") == 5
    rec = w.client().get("/api/v1/reports/reconciliation", headers=w.admin).json()["data"]
    assert rec["discrepancies"] == []
    seqs = [r[0] for r in sql(w, "SELECT customer_sequence FROM ledger_entries WHERE campus_user_id=:u ORDER BY customer_sequence", u=w.students[ARUN].id)]
    assert seqs == list(range(1, len(seqs) + 1))  # no gaps, no duplicates


def test_duplicate_payment_race_with_the_same_idempotency_key_debits_once(cworld):
    w = cworld
    (oid,) = _orders(w, "Veg Meal", 1)
    key = f"dup-race-{uuid.uuid4().hex[:8]}"
    results = _race(8, lambda i: _pay(w, oid, key))
    assert all(s == 200 for s, _ in results), results
    assert sum(1 for _, b in results if not b["data"]["replayed"]) == 1
    assert balance(w, ARUN) == 440 and ledger_count(w, "PURCHASE") == 1
    assert len({b["data"]["payment"]["id"] for _, b in results}) == 1


def test_same_order_with_different_keys_races_to_exactly_one_payment(cworld):
    w = cworld
    (oid,) = _orders(w, "Veg Meal", 1)
    results = _race(8, lambda i: _pay(w, oid, f"diff-{i}-{uuid.uuid4().hex[:6]}"))
    assert sorted(s for s, _ in results).count(200) == 1
    assert all(s in (200, 409) for s, _ in results), results
    assert all(b["error"]["code"] == "ORDER_ALREADY_PAID" for s, b in results if s == 409)
    assert balance(w, ARUN) == 440 and ledger_count(w, "PURCHASE") == 1
    assert sql(w, "SELECT COUNT(*) FROM payments WHERE status='COMPLETED'")[0][0] == 1


def test_duplicate_demo_funding_race_credits_once(cworld):
    w = cworld
    body = {"campus_user_id": w.students[ARUN].id, "amount_cu": 50, "reference": f"fund-race-{uuid.uuid4().hex[:6]}"}
    results = _race(6, lambda i: TestClient(w.app).post("/api/v1/demo/wallet-funding", json=body, headers=w.admin).status_code)
    assert all(s == 200 for s in results), results
    assert balance(w, ARUN) == 550 and ledger_count(w, "RECHARGE") == 2 + 1  # 2 seed credits + 1


def test_concurrent_order_creation_with_one_request_key_makes_one_order(cworld):
    w = cworld
    key = f"order-race-{uuid.uuid4().hex[:8]}"
    results = _race(6, lambda i: place_order(w, ARUN, {"Tea": 1}, key=key).status_code)
    assert all(s == 201 for s in results), results
    assert sql(w, "SELECT COUNT(*) FROM orders WHERE client_request_key=:k", k=key)[0][0] == 1


def test_concurrent_purchases_by_two_customers_do_not_interfere(cworld):
    w = cworld
    a, b = _orders(w, "Veg Meal", 1, "EGS-STD-0001")[0], _orders(w, "Veg Meal", 1, "EGS-STD-0002")[0]
    results = _race(2, lambda i: _pay(w, (a, b)[i], f"pair-{i}-{uuid.uuid4().hex[:6]}", cid=("EGS-STD-0001", "EGS-STD-0002")[i]))
    assert [s for s, _ in results] == [200, 200]
    assert balance(w, "EGS-STD-0001") == 440 and balance(w, "EGS-STD-0002") == 440
