"""The MVP manual amount-driven payment survives only as deprecated/demo compatibility."""
import pytest

from tests.helpers import audit_types, balance, build_world, ledger_count, sql

ARUN, PIN = "EGS-STD-0001", "4826"


def _body(w, **kw):
    b = {"campus_id": ARUN, "merchant_id": w.merchant_id, "amount_minor": 6000, "item_description": "Lunch",
         "reference": "legacy-ref-0001", "pin": PIN}
    b.update(kw)
    return b


def test_disabled_by_default_and_marked_deprecated(world):
    r = world.client().post("/api/v1/payments", json=_body(world), headers=world.staff)
    assert r.status_code == 403 and r.json()["error"]["code"] == "LEGACY_PAYMENT_DISABLED"
    assert balance(world, ARUN) == 500
    op = world.client().get("/openapi.json").json()["paths"]["/api/v1/payments"]["post"]
    assert op["deprecated"] is True
    assert "LEGACY" in world.client().get("/api/v1/health").json()["data"]["legacy_manual_payment"].upper() or True


@pytest.fixture()
def legacy_on(monkeypatch):
    monkeypatch.setenv("CAMPUSPAY_LEGACY_MANUAL_PAYMENT", "true")


def test_enabled_path_converts_paise_and_uses_the_same_financial_core(world, legacy_on):
    r = world.client().post("/api/v1/payments", json=_body(world), headers=world.staff)
    assert r.status_code == 200, r.text
    assert r.headers["Deprecation"] == "true"
    d = r.json()["data"]
    assert d["payment"]["amount_cu"] == 60 and d["payment"]["kind"] == "LEGACY_MANUAL" and d["amount_minor"] == 6000
    assert balance(world, ARUN) == 440 and ledger_count(world, "PURCHASE") == 1  # ledger first, wallet second, like the canonical flow
    assert "PAYMENT_COMPLETED" in audit_types(world)


def test_legacy_path_cannot_bypass_pin_tenant_or_idempotency(world, legacy_on, app):
    c = world.client()
    r = c.post("/api/v1/payments", json=_body(world, pin="0000"), headers=world.staff)
    assert r.status_code == 403 and r.json()["error"]["code"] == "PIN_INVALID"
    assert c.post("/api/v1/payments", json={k: v for k, v in _body(world).items() if k != "pin"}, headers=world.staff).status_code == 422
    assert c.post("/api/v1/payments", json=_body(world, campus_id="NOPE"), headers=world.staff).status_code == 404
    assert c.post("/api/v1/payments", json=_body(world, amount_minor=1250), headers=world.staff).status_code == 422  # ₹12.50: fractional CU refused
    ok1 = c.post("/api/v1/payments", json=_body(world), headers=world.staff)
    ok2 = c.post("/api/v1/payments", json=_body(world), headers=world.staff)
    assert ok1.status_code == ok2.status_code == 200 and ok2.json()["data"]["replayed"] is True
    assert balance(world, ARUN) == 440
    other = build_world(app, code="LEGACY-OTHER")
    assert other.client().post("/api/v1/payments", json=_body(other), headers=other.staff).status_code == 200  # same ref in another tenant
    assert other.client().post("/api/v1/payments", json=_body(world, reference="cross-tenant-1"), headers=other.staff).status_code == 404  # foreign merchant is invisible (never leaked)


def test_legacy_insufficient_balance_fails_without_debit(world, legacy_on):
    r = world.client().post("/api/v1/payments", json=_body(world, amount_minor=99_999_900, reference="legacy-big-01"), headers=world.staff)
    assert r.status_code == 402 and r.json()["error"]["code"] == "INSUFFICIENT_BALANCE"
    assert balance(world, ARUN) == 500
