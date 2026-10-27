import pytest
from sqlalchemy import text

from core.config import ConfigurationError, get_settings
from tests.helpers import audit_types, balance, pay, place_order, sql

ARUN, PIN = "EGS-STD-0001", "4826"


def _order(w, cid=ARUN):
    return place_order(w, cid, {"Tea": 1}).json()["data"]


def _failed_attempts(w):
    return sql(w, "SELECT failed_attempts FROM payment_pin_credentials WHERE campus_user_id=:u", u=w.students[ARUN].id)[0][0]


def test_valid_pin_authorises_the_purchase(world):
    assert pay(world, _order(world)["id"], ARUN, PIN).status_code == 200


def test_invalid_pin_is_refused_counted_and_audited_without_any_payment_or_debit(world):
    order = _order(world)
    r = pay(world, order["id"], ARUN, "0000")
    assert r.status_code == 403 and r.json()["error"]["code"] == "PIN_INVALID"
    assert balance(world, ARUN) == 500
    assert _failed_attempts(world) == 1  # counter survives the refused request (committed on its own)
    assert "PIN_FAILED" in audit_types(world)
    assert sql(world, "SELECT COUNT(*) FROM payments WHERE institution_id=:i", i=world.institution_id)[0][0] == 0
    assert pay(world, order["id"], ARUN, PIN).status_code == 200
    assert _failed_attempts(world) == 0  # success resets the counter


@pytest.mark.parametrize("bad", ["123", "12345", "12a4", "١٢٣٤", "", " 123"])
def test_pin_must_be_exactly_four_ascii_digits(world, bad):
    order = _order(world)
    r = pay(world, order["id"], ARUN, bad)
    assert r.status_code == 422
    assert balance(world, ARUN) == 500


def test_pin_not_set(world):
    sql(world, "DELETE FROM payment_pin_credentials WHERE campus_user_id=:u", u=world.students["EGS-STD-0002"].id)
    order = place_order(world, "EGS-STD-0002", {"Tea": 1}).json()["data"]
    r = pay(world, order["id"], "EGS-STD-0002", PIN)
    assert r.status_code == 403 and r.json()["error"]["code"] == "PIN_NOT_SET"


def test_pin_is_stored_only_as_a_slow_salted_hash_and_never_leaks(world):
    h = sql(world, "SELECT pin_hash FROM payment_pin_credentials WHERE campus_user_id=:u", u=world.students[ARUN].id)[0][0]
    assert h.startswith("$2") and PIN not in h
    order = _order(world)
    body = pay(world, order["id"], ARUN, "1111").text + pay(world, order["id"], ARUN, PIN).text
    assert "pin_hash" not in body and "$2" not in body
    meta = " ".join(str(r[0]) for r in sql(world, "SELECT metadata_json FROM audit_logs WHERE institution_id=:i", i=world.institution_id))
    assert PIN not in meta and "1111" not in meta


def test_lockout_mechanism_is_configurable_not_hard_coded(world, monkeypatch):
    monkeypatch.setenv("CAMPUSPAY_PIN_MAX_FAILED_ATTEMPTS", "2")
    monkeypatch.setenv("CAMPUSPAY_PIN_LOCK_DURATION_SECONDS", "600")
    order = _order(world)
    assert pay(world, order["id"], ARUN, "0001").json()["error"]["code"] == "PIN_INVALID"
    assert pay(world, order["id"], ARUN, "0002").json()["error"]["code"] == "PIN_INVALID"
    r = pay(world, order["id"], ARUN, PIN)  # correct PIN while locked
    assert r.status_code == 403 and r.json()["error"]["code"] == "PIN_LOCKED"
    assert "PIN_LOCKED" in audit_types(world)
    assert balance(world, ARUN) == 500
    # lock expires by time only (unlock authority is OPEN: there is no manual unlock in P1)
    sql(world, "UPDATE payment_pin_credentials SET locked_until='2000-01-01 00:00:00' WHERE campus_user_id=:u", u=world.students[ARUN].id)
    assert pay(world, order["id"], ARUN, PIN).status_code == 200


def test_without_configuration_failures_are_counted_but_nothing_locks(world):
    """MG-01 is OPEN: with no configured policy the mechanism records failures and never invents a lock."""
    assert get_settings().pin_max_failed_attempts is None
    order = _order(world)
    for i in range(6):
        assert pay(world, order["id"], ARUN, f"000{i}").json()["error"]["code"] == "PIN_INVALID"
    assert _failed_attempts(world) == 6
    assert pay(world, order["id"], ARUN, PIN).status_code == 200


def test_lock_policy_must_be_configured_as_a_pair(monkeypatch):
    monkeypatch.setenv("CAMPUSPAY_PIN_MAX_FAILED_ATTEMPTS", "3")
    with pytest.raises(ConfigurationError):
        get_settings()


def test_health_reports_open_pin_policy(client):
    d = client.get("/api/v1/health").json()["data"]
    assert "MG-01" in d["pin_lockout"]


def test_pin_provisioning_is_admin_only_audited_and_validated(world):
    c, sid = world.client(), world.students["EGS-STD-0003"].id
    assert c.post("/api/v1/auth/payment-pin", json={"campus_user_id": sid, "pin": "1357"}, headers=world.staff).status_code == 403
    assert c.post("/api/v1/auth/payment-pin", json={"campus_user_id": sid, "pin": "13"}, headers=world.admin).status_code == 422
    r = c.post("/api/v1/auth/payment-pin", json={"campus_user_id": sid, "pin": "1357"}, headers=world.admin)
    assert r.status_code == 200 and r.json()["data"]["event"] == "PIN_CHANGED"
    assert "PIN_CHANGED" in audit_types(world) and "PIN_CREATED" in audit_types(world)
    order = place_order(world, "EGS-STD-0003", {"Tea": 1}).json()["data"]
    assert pay(world, order["id"], "EGS-STD-0003", "1357").status_code == 200
