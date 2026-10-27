"""Ledger authority, wallet-as-representation, immutability, demo-funding separation."""
import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from core.errors import ForbiddenError, PolicyOpenError
from modules.audit.service import ImmutableRecordError
from modules.ledger import service as ledger
from modules.ledger.models import LedgerEntry
from modules.wallets.models import Wallet
from tests.helpers import audit_types, balance, ledger_count, pay, place_order, sql

ARUN, PIN = "EGS-STD-0001", "4826"


def test_ledger_position_wallet_and_reconciliation_agree_after_activity(world):
    for cid in ("EGS-STD-0001", "EGS-STD-0002"):
        for items in ({"Tea": 2}, {"Veg Meal": 1}):
            o = place_order(world, cid, items).json()["data"]
            assert pay(world, o["id"], cid, PIN).status_code == 200
    balances = {cid: balance(world, cid) for cid in world.students}  # (SQLite: one open transaction at a time)
    db = world.session()
    try:
        for cid, s in world.students.items():
            chain = ledger.verify_customer_chain(db, institution_id=world.institution_id, campus_user_id=s.id)
            assert chain.ok and chain.position_cu == balances[cid]
    finally:
        db.close()
    rec = world.client().get("/api/v1/reports/reconciliation", headers=world.admin).json()["data"]
    assert rec["discrepancies"] == [] and rec["institution_ledger_position_cu"] == rec["sum_of_wallet_available_cu"]


def test_the_wallet_cannot_be_overwritten_by_application_code(world):
    db = world.session()
    try:
        w = db.execute(select(Wallet).where(Wallet.campus_user_id == world.students[ARUN].id)).scalar_one()
        w.available_cu = 10**9
        with pytest.raises(ForbiddenError) as e:
            db.flush()
        assert e.value.code == "WALLET_DIRECT_MUTATION_FORBIDDEN"
    finally:
        db.rollback()
        db.close()
    assert balance(world, ARUN) == 500


def test_the_wallet_cannot_be_overwritten_even_with_raw_sql(world):
    """Database trigger: available value must equal the Institution Ledger position."""
    db = world.session()
    try:
        with pytest.raises(DBAPIError):
            db.execute(text("UPDATE wallets SET available_cu = 999999 WHERE campus_user_id = :u"), {"u": world.students[ARUN].id})
            db.commit()
    finally:
        db.rollback()
        db.close()
    assert balance(world, ARUN) == 500


def test_ledger_entries_are_immutable_in_orm_and_database(world):
    db = world.session()
    try:
        e = db.execute(select(LedgerEntry).limit(1)).scalar_one()
        e.amount_cu = 1
        with pytest.raises(Exception) as exc:
            db.flush()
        assert "immutable" in str(exc.value).lower()
        db.rollback()
        for stmt in ("UPDATE ledger_entries SET amount_cu = 1", "DELETE FROM ledger_entries"):
            with pytest.raises(DBAPIError):
                db.execute(text(stmt))
            db.rollback()
    finally:
        db.close()


def test_audit_records_are_immutable_in_orm_and_database(world):
    from modules.audit.models import AuditLog
    db = world.session()
    try:
        row = db.execute(select(AuditLog).limit(1)).scalar_one()
        row.event_type = "TAMPERED"
        with pytest.raises(ImmutableRecordError):
            db.flush()
        db.rollback()
        for stmt in ("UPDATE audit_logs SET event_type='X'", "DELETE FROM audit_logs"):
            with pytest.raises(DBAPIError):
                db.execute(text(stmt))
            db.rollback()
    finally:
        db.close()


def test_ledger_table_rejects_inconsistent_arithmetic(world):
    db = world.session()
    try:
        with pytest.raises(DBAPIError):
            db.execute(text(
                "INSERT INTO ledger_entries (id, institution_id, campus_user_id, customer_sequence, event_type, direction, amount_cu,"
                " position_before_cu, position_after_cu, origin, reference_type, reference_id, created_at)"
                " VALUES ('x', :i, :u, 99, 'PURCHASE', 'DEBIT', 10, 500, 500, 'STANDARD', 'PAYMENT', 'p', '2026-01-01')"),
                {"i": world.institution_id, "u": world.students[ARUN].id})
            db.commit()
    finally:
        db.rollback()
        db.close()


def test_events_whose_policy_is_open_are_recognised_but_not_implemented(world):
    db = world.session()
    try:
        for et in (ledger.ADJUSTMENT, ledger.REFUND, ledger.SETTLEMENT, ledger.WALLET_STATUS_CHANGE):
            with pytest.raises(PolicyOpenError) as e:
                ledger.record_financial_event(db, institution_id=world.institution_id, campus_user_id=world.students[ARUN].id,
                                              event_type=et, direction=ledger.CREDIT, amount_cu=10, reference_type="X",
                                              reference_id="r", actor_id=None)
            assert e.value.code == "FINANCIAL_EVENT_POLICY_OPEN"
    finally:
        db.close()
    assert balance(world, ARUN) == 500


def test_demo_funding_is_flagged_demo_and_separate_from_production_recharge(world):
    r = world.client().post("/api/v1/demo/wallet-funding", headers=world.admin, json={
        "campus_user_id": world.students[ARUN].id, "amount_cu": 100, "reference": "demo-topup-01"})
    assert r.status_code == 200 and "not a production recharge" in r.json()["message"]
    assert r.json()["data"]["balance_after_cu"] == 600
    row = sql(world, "SELECT event_type, origin, reference_type FROM ledger_entries WHERE reference_id='demo-topup-01'")[0]
    assert row == ("RECHARGE", "DEMO", "DEMO_FUNDING")
    assert "DEMO_FUNDING_APPLIED" in audit_types(world)
    paths = set(world.app.openapi()["paths"])
    assert "/api/v1/wallets/recharge" not in paths and "/api/v1/recharge" not in paths  # no production recharge path exists


def test_registration_does_not_fund_a_wallet(world):
    c = world.client()
    r = c.post("/api/v1/students", headers=world.admin, json={"name": "New", "unique_identifier": "EGS-STD-0100", "initial_balance_minor": 99900})
    assert r.status_code == 201
    uid = r.json()["data"]["id"]
    w = c.post("/api/v1/wallets", headers=world.admin, json={"campus_user_id": uid}).json()["data"]
    assert w["available_cu"] == 0  # registration never becomes a recharge


def test_demo_funding_is_idempotent_and_flag_gated(world, monkeypatch):
    body = {"campus_user_id": world.students[ARUN].id, "amount_cu": 50, "reference": "demo-idem-1"}
    c = world.client()
    r1, r2 = c.post("/api/v1/demo/wallet-funding", headers=world.admin, json=body), c.post("/api/v1/demo/wallet-funding", headers=world.admin, json=body)
    assert r1.json()["data"]["replayed"] is False and r2.json()["data"]["replayed"] is True
    assert balance(world, ARUN) == 550
    r3 = c.post("/api/v1/demo/wallet-funding", headers=world.admin, json=dict(body, amount_cu=60))
    assert r3.status_code == 409 and r3.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"
    assert c.post("/api/v1/demo/wallet-funding", headers=world.admin, json=dict(body, amount_cu=10.5, reference="r2-frac")).status_code == 422
    monkeypatch.setenv("CAMPUSPAY_DEMO_FUNDING", "false")
    r4 = c.post("/api/v1/demo/wallet-funding", headers=world.admin, json=dict(body, reference="demo-off-1"))
    assert r4.status_code == 403 and r4.json()["error"]["code"] == "DEMO_FUNDING_DISABLED"
    assert balance(world, ARUN) == 550


def test_ledger_wallet_discrepancy_fails_closed_and_writes_nothing(world):
    """MG-16 (response policy) is OPEN: the only safe behaviour is to block the financial operation and detect."""
    sql(world, "DROP TRIGGER trg_wallet_matches_ledger_upd")  # simulate tampering that bypassed the guard
    sql(world, "UPDATE wallets SET available_cu = available_cu + 250 WHERE campus_user_id=:u", u=world.students[ARUN].id)
    o = place_order(world, ARUN, {"Tea": 1}).json()["data"]
    before = ledger_count(world)
    r = pay(world, o["id"], ARUN, PIN)
    assert r.status_code == 409 and r.json()["error"]["code"] == "LEDGER_WALLET_DISCREPANCY"
    assert ledger_count(world) == before
    rec = world.client().get("/api/v1/reports/reconciliation", headers=world.admin).json()["data"]
    assert [d["campus_user_id"] for d in rec["discrepancies"]] == [world.students[ARUN].id]


def test_every_completed_payment_has_exactly_one_debit_and_one_ledger_purchase(world):
    for _ in range(3):
        o = place_order(world, ARUN, {"Tea": 1}).json()["data"]
        assert pay(world, o["id"], ARUN, PIN).status_code == 200
    rows = sql(world, """SELECT p.id,
        (SELECT COUNT(*) FROM wallet_transactions w WHERE w.payment_id=p.id AND w.type='DEBIT'),
        (SELECT COUNT(*) FROM ledger_entries l WHERE l.reference_id=p.id AND l.event_type='PURCHASE')
        FROM payments p WHERE p.status='COMPLETED'""")
    assert len(rows) == 3 and all(r[1] == 1 and r[2] == 1 for r in rows)
