import pytest

from tests.helpers import add_product, audit_types, balance, build_world, ledger_count, place_order, sql

ARUN = "EGS-STD-0001"


def test_menu_shows_categories_products_and_availability_states(world):
    add_product(world, "Idli", 20, availability="SOLD_OUT")
    add_product(world, "Special", 90, availability="UNAVAILABLE")
    menu = world.client().get(f"/api/v1/merchants/{world.merchant_id}/menu", headers=world.staff).json()["data"]
    products = {p["name"]: p for c in menu["categories"] for p in c["products"]}
    assert products["Veg Meal"]["price_cu"] == 60 and products["Veg Meal"]["availability"] == "AVAILABLE"
    assert products["Idli"]["availability"] == "SOLD_OUT" and products["Special"]["availability"] == "UNAVAILABLE"


def test_server_computes_prices_and_snapshots_each_line(world):
    r = place_order(world, ARUN, {"Veg Meal": 2, "Tea": 3, "Samosa": 1})
    o = r.json()["data"]
    assert r.status_code == 201 and o["status"] == "CREATED"
    assert o["total_cu"] == 2 * 60 + 3 * 10 + 15
    by = {i["name"]: i for i in o["items"]}
    assert by["Veg Meal"]["unit_price_cu"] == 60 and by["Veg Meal"]["line_total_cu"] == 120
    assert o["reference"].startswith("ORD-") and o["merchant_id"] == world.merchant_id
    assert o["device_id"] == world.kiosk_id and o["customer"]["campus_id"] == ARUN
    assert balance(world, ARUN) == 500  # creating an order/cart never touches the wallet


def test_price_snapshot_survives_menu_price_changes(world):
    o = place_order(world, ARUN, {"Tea": 2}).json()["data"]
    world.client().patch(f"/api/v1/products/{world.products['Tea']}", json={"price_cu": 25}, headers=world.admin)
    again = world.client().get(f"/api/v1/orders/{o['id']}", headers=world.staff).json()["data"]
    assert again["total_cu"] == 20 and again["items"][0]["unit_price_cu"] == 10
    assert place_order(world, ARUN, {"Tea": 2}).json()["data"]["total_cu"] == 50  # new orders use the new price


@pytest.mark.parametrize("availability,code", [("SOLD_OUT", "PRODUCT_SOLD_OUT"), ("UNAVAILABLE", "PRODUCT_UNAVAILABLE")])
def test_unavailable_products_cannot_be_ordered(world, availability, code):
    world.client().patch(f"/api/v1/products/{world.products['Tea']}", json={"availability": availability}, headers=world.staff)
    r = place_order(world, ARUN, {"Tea": 1})
    assert r.status_code == 409 and r.json()["error"]["code"] == code


def test_inactive_product_and_unknown_product_are_rejected(world):
    world.client().patch(f"/api/v1/products/{world.products['Tea']}", json={"status": "INACTIVE"}, headers=world.staff)
    assert place_order(world, ARUN, {"Tea": 1}).json()["error"]["code"] == "PRODUCT_UNAVAILABLE"
    r = world.client().post("/api/v1/orders", headers=world.staff, json={
        "merchant_id": world.merchant_id, "identity": {"value": ARUN}, "items": [{"product_id": "nope", "quantity": 1}]})
    assert r.status_code == 404 and r.json()["error"]["code"] == "PRODUCT_NOT_FOUND"


@pytest.mark.parametrize("qty", [0, -1, 1001])
def test_invalid_quantity_and_empty_order_are_rejected(world, qty):
    r = world.client().post("/api/v1/orders", headers=world.staff, json={
        "merchant_id": world.merchant_id, "identity": {"value": ARUN}, "items": [{"product_id": world.products["Tea"], "quantity": qty}]})
    assert r.status_code == 422
    r = world.client().post("/api/v1/orders", headers=world.staff, json={"merchant_id": world.merchant_id, "identity": {"value": ARUN}, "items": []})
    assert r.status_code == 422


def test_order_creation_is_idempotent_per_request_key(world):
    r1 = place_order(world, ARUN, {"Tea": 2}, key="checkout-key-1")
    r2 = place_order(world, ARUN, {"Tea": 2}, key="checkout-key-1")
    assert r2.status_code == 201 and r2.json()["data"]["replayed"] is True
    assert r1.json()["data"]["id"] == r2.json()["data"]["id"]
    assert sql(world, "SELECT COUNT(*) FROM orders WHERE institution_id=:i", i=world.institution_id)[0][0] == 1
    r3 = place_order(world, ARUN, {"Tea": 3}, key="checkout-key-1")
    assert r3.status_code == 409 and r3.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"


def test_duplicate_lines_are_merged(world):
    r = world.client().post("/api/v1/orders", headers=world.staff, json={
        "merchant_id": world.merchant_id, "identity": {"value": ARUN},
        "items": [{"product_id": world.products["Tea"], "quantity": 1}, {"product_id": world.products["Tea"], "quantity": 2}]})
    o = r.json()["data"]
    assert len(o["items"]) == 1 and o["items"][0]["quantity"] == 3 and o["total_cu"] == 30


def test_kiosk_must_be_active_and_serve_the_merchant(world):
    r = world.client().patch(f"/api/v1/devices/{world.kiosk_id}", json={"status": "INACTIVE"}, headers=world.admin)
    assert r.status_code == 200
    r = place_order(world, ARUN, {"Tea": 1})
    assert r.status_code == 403 and r.json()["error"]["code"] == "DEVICE_INACTIVE"
    assert place_order(world, ARUN, {"Tea": 1}, device=False).status_code == 201  # device reference is optional in P1


def test_multiple_kiosks_per_merchant_and_multiple_merchants_are_supported(world):
    c = world.client()
    for name in ("KIOSK-2", "KIOSK-3", "KIOSK-4"):
        assert c.post("/api/v1/devices", json={"name": name, "merchant_id": world.merchant_id}, headers=world.admin).status_code == 201
    other = c.post("/api/v1/devices", json={"name": "KIOSK-1", "merchant_id": world.merchant_id}, headers=world.admin)
    assert other.status_code == 409  # names are unique per institution
    kiosks = c.get(f"/api/v1/devices?merchant_id={world.merchant_id}", headers=world.admin).json()["data"]
    assert len(kiosks) == 4
    # a second merchant can be added; nothing assumes one canteen or one kiosk
    from modules.merchants import service as merchants
    db = world.session()
    try:
        m = merchants.create_merchant(db, institution_id=world.institution_id, name="North Canteen", category="Canteen")
        db.commit()
    finally:
        db.close()
    assert len(c.get("/api/v1/merchants", headers=world.admin).json()["data"]) == 3


def test_merchant_staff_cannot_modify_another_merchants_menu(world):
    from modules.merchants import service as merchants
    db = world.session()
    try:
        m2 = merchants.create_merchant(db, institution_id=world.institution_id, name="Stationery", category="Stationery")
        cat2 = merchants.create_category(db, institution_id=world.institution_id, merchant_id=m2.id, name="Pens", display_order=1,
                                         actor_user_id=world.admin_id, actor_role="ADMIN")
        p2 = merchants.create_product(db, institution_id=world.institution_id, category_id=cat2["id"], name="Pen", price_cu=10,
                                      description=None, actor_user_id=world.admin_id, actor_role="ADMIN")
        db.commit()
    finally:
        db.close()
    c = world.client()
    r = c.patch(f"/api/v1/products/{p2.id}", json={"price_cu": 1}, headers=world.staff)
    assert r.status_code == 403 and r.json()["error"]["code"] == "MERCHANT_SCOPE_VIOLATION"
    assert c.get(f"/api/v1/merchants/{m2.id}/menu", headers=world.staff).status_code == 403
    assert c.post("/api/v1/products", json={"category_id": cat2["id"], "name": "X", "price_cu": 5}, headers=world.staff).status_code == 403


def test_menu_authority_is_configurable_because_it_is_an_open_decision(world, monkeypatch):
    monkeypatch.setenv("CAMPUSPAY_MENU_MANAGE_ROLES", "ADMIN")  # MG-08 OPEN: who may change the menu
    c = world.client()
    r = c.patch(f"/api/v1/products/{world.products['Tea']}", json={"availability": "SOLD_OUT"}, headers=world.staff)
    assert r.status_code == 403 and r.json()["error"]["code"] == "MENU_AUTHORITY_DENIED"
    assert c.patch(f"/api/v1/products/{world.products['Tea']}", json={"availability": "SOLD_OUT"}, headers=world.admin).status_code == 200


def test_catalog_changes_are_audited(world):
    c = world.client()
    c.patch(f"/api/v1/products/{world.products['Tea']}", json={"availability": "SOLD_OUT"}, headers=world.staff)
    c.patch(f"/api/v1/products/{world.products['Tea']}", json={"price_cu": 12}, headers=world.staff)
    types = audit_types(world)
    for e in ("CATEGORY_CREATED", "PRODUCT_CREATED", "PRODUCT_AVAILABILITY_CHANGED", "PRODUCT_UPDATED"):
        assert e in types


def test_invalid_prices_are_rejected(world):
    c = world.client()
    for bad in (0, -5, 12.5):
        r = c.post("/api/v1/products", json={"category_id": world.category_id, "name": "Bad", "price_cu": bad}, headers=world.admin)
        assert r.status_code == 422, bad


def test_abandoned_cart_and_cancelled_order_have_no_financial_effect(world):
    before = ledger_count(world)
    o = place_order(world, ARUN, {"Veg Meal": 1}).json()["data"]
    assert world.client().post(f"/api/v1/orders/{o['id']}/cancel", headers=world.staff).status_code == 200
    assert balance(world, ARUN) == 500 and ledger_count(world) == before
