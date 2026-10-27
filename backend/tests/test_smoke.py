from tests.helpers import balance, pay, place_order


def test_end_to_end_smoke(world):
    r = place_order(world, "EGS-STD-0001", {"Veg Meal": 1, "Tea": 2})
    assert r.status_code == 201, r.text
    order = r.json()["data"]
    assert order["total_cu"] == 80
    p = pay(world, order["id"], "EGS-STD-0001", "4826")
    assert p.status_code == 200, p.text
    data = p.json()["data"]
    assert data["payment"]["status"] == "COMPLETED"
    assert data["balance_before_cu"] == 500 and data["balance_after_cu"] == 420
    assert balance(world, "EGS-STD-0001") == 420
    assert data["receipt"]["receipt_number"].startswith("RCT-")
