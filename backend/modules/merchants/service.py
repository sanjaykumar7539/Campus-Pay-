"""Merchant module — published interface (ADR-0005).

Owns: Merchant, catalog (Category, Product, price, availability), Order + OrderItem
(server-authoritative, price-snapshotted) and Fulfillment. It does NOT own payment,
wallet or ledger and never imports them: merchant staff physically cannot alter
financial state through this module.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.config import get_settings
from core.errors import ConflictError, ForbiddenError, NotFoundError, ValidationFailure
from modules.audit import service as audit
from modules.devices import service as devices
from modules.merchants.models import (Fulfillment, Merchant, MerchantStaff, Order, OrderItem, Product,
                                      ProductCategory)
from modules.users import service as users
from shared.campus_units import CampusUnitError, MAX_CU, validate_cu
from shared.clock import utcnow
from shared.ids import opaque_reference

ACTIVE = "ACTIVE"
AVAILABLE, SOLD_OUT, UNAVAILABLE = "AVAILABLE", "SOLD_OUT", "UNAVAILABLE"
AVAILABILITIES = frozenset({AVAILABLE, SOLD_OUT, UNAVAILABLE})
ORDER_CREATED, ORDER_PAID, ORDER_CANCELLED = "CREATED", "PAID", "CANCELLED"
F_PAID, F_PREPARING, F_READY, F_COLLECTED = "PAID", "PREPARING", "READY", "COLLECTED"
_FULFILLMENT_NEXT = {F_PAID: F_PREPARING, F_PREPARING: F_READY, F_READY: F_COLLECTED}
_FULFILLMENT_AUDIT = {F_PREPARING: "FULFILLMENT_STARTED", F_READY: "FULFILLMENT_READY", F_COLLECTED: "FULFILLMENT_COLLECTED"}
MAX_QUANTITY_PER_LINE = 1000  # technical sanity bound on input, not a business rule


@dataclass(frozen=True)
class MerchantView:
    id: str
    institution_id: str
    name: str
    category: str
    status: str
    accepting_orders: bool = True


@dataclass(frozen=True)
class ProductView:
    id: str
    merchant_id: str
    category_id: str
    name: str
    description: Optional[str]
    price_cu: int
    stock_quantity: int
    availability: str
    status: str


@dataclass(frozen=True)
class OrderItemView:
    product_id: str
    name: str
    unit_price_cu: int
    quantity: int
    line_total_cu: int


@dataclass(frozen=True)
class FulfillmentView:
    status: str
    paid_at: datetime
    preparing_at: Optional[datetime]
    ready_at: Optional[datetime]
    collected_at: Optional[datetime]


@dataclass(frozen=True)
class OrderView:
    id: str
    institution_id: str
    merchant_id: str
    customer_id: str
    device_id: Optional[str]
    reference: str
    status: str
    total_cu: int
    created_at: datetime
    items: list[OrderItemView] = field(default_factory=list)
    fulfillment: Optional[FulfillmentView] = None


def _mv(m: Merchant) -> MerchantView:
    return MerchantView(m.id, m.institution_id, m.name, m.category, m.status, bool(m.accepting_orders))


def _pv(p: Product) -> ProductView:
    return ProductView(p.id, p.merchant_id, p.category_id, p.name, p.description, p.price_cu, p.stock_quantity, p.availability, p.status)


def _fv(f: Optional[Fulfillment]) -> Optional[FulfillmentView]:
    return FulfillmentView(f.status, f.paid_at, f.preparing_at, f.ready_at, f.collected_at) if f else None


def _ov(db: Session, o: Order) -> OrderView:
    items = db.execute(select(OrderItem).where(OrderItem.institution_id == o.institution_id,
                                               OrderItem.order_id == o.id).order_by(OrderItem.product_name_snapshot)).scalars().all()
    f = db.execute(select(Fulfillment).where(Fulfillment.institution_id == o.institution_id,
                                             Fulfillment.order_id == o.id)).scalar_one_or_none()
    return OrderView(o.id, o.institution_id, o.merchant_id, o.campus_user_id, o.device_id, o.reference, o.status,
                     o.total_cu, o.created_at,
                     [OrderItemView(i.product_id, i.product_name_snapshot, i.unit_price_cu_snapshot, i.quantity,
                                    i.line_total_cu) for i in items], _fv(f))


# -- merchants & staff ----------------------------------------------------------------------

def create_merchant(db: Session, *, institution_id: str, name: str, category: str, status: str = ACTIVE,
                    actor_id: Optional[str] = None, actor_role: Optional[str] = None) -> MerchantView:
    m = Merchant(institution_id=institution_id, name=name.strip(), category=category.strip(), status=status)
    db.add(m)
    db.flush()
    audit.record_event(db, institution_id=institution_id, actor_id=actor_id or "system", actor_role=actor_role,
                       event_type="MERCHANT_CREATED", entity_type="Merchant", entity_id=m.id, new={"name": m.name, "status": status})
    return _mv(m)


def get_merchant(db: Session, *, institution_id: str, merchant_id: str, for_update: bool = False) -> MerchantView:
    stmt = select(Merchant).where(Merchant.institution_id == institution_id, Merchant.id == merchant_id)
    if for_update:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    m = db.execute(stmt).scalar_one_or_none()
    if m is None:
        raise NotFoundError("Merchant not found", code="MERCHANT_NOT_FOUND")
    return _mv(m)


def list_merchants(db: Session, *, institution_id: str, actor_user_id: Optional[str] = None,
                   actor_role: Optional[str] = None) -> list[MerchantView]:
    stmt = select(Merchant).where(Merchant.institution_id == institution_id)
    if actor_role == users.MERCHANT_STAFF:
        own = staff_merchant_id(db, institution_id=institution_id, campus_user_id=actor_user_id or "")
        stmt = stmt.where(Merchant.id == (own or "-"))
    return [_mv(m) for m in db.execute(stmt.order_by(Merchant.name)).scalars()]


def assign_staff(db: Session, *, institution_id: str, campus_user_id: str, merchant_id: str) -> None:
    get_merchant(db, institution_id=institution_id, merchant_id=merchant_id)
    u = users.get_user(db, institution_id=institution_id, user_id=campus_user_id)
    if u.role != users.MERCHANT_STAFF:
        raise ValidationFailure("Only MERCHANT_STAFF users can be assigned to a merchant", code="NOT_MERCHANT_STAFF")
    db.add(MerchantStaff(institution_id=institution_id, campus_user_id=campus_user_id, merchant_id=merchant_id))
    db.flush()


def staff_merchant_id(db: Session, *, institution_id: str, campus_user_id: str) -> Optional[str]:
    row = db.execute(select(MerchantStaff).where(MerchantStaff.institution_id == institution_id,
                                                 MerchantStaff.campus_user_id == campus_user_id)).scalar_one_or_none()
    return row.merchant_id if row else None


def require_merchant_scope(db: Session, *, institution_id: str, actor_user_id: str, actor_role: str,
                           merchant_id: str) -> MerchantView:
    """Merchant scoping: ADMIN may act on any merchant of their institution; staff only on their own."""
    merchant = get_merchant(db, institution_id=institution_id, merchant_id=merchant_id)
    if actor_role in (users.ADMIN, users.STUDENT):
        return merchant
    if actor_role == users.MERCHANT_STAFF and staff_merchant_id(
            db, institution_id=institution_id, campus_user_id=actor_user_id) == merchant_id:
        return merchant
    raise ForbiddenError("Not permitted for this merchant", code="MERCHANT_SCOPE_VIOLATION")


def update_merchant(db: Session, *, institution_id: str, merchant_id: str, actor_id: str,
                    name: Optional[str] = None, category: Optional[str] = None, status: Optional[str] = None,
                    actor_role: str = "ADMIN") -> MerchantView:
    m = db.execute(select(Merchant).where(Merchant.institution_id == institution_id, Merchant.id == merchant_id).with_for_update()).scalar_one_or_none()
    if m is None:
        raise NotFoundError("Merchant not found", code="MERCHANT_NOT_FOUND")
    prev = {"name": m.name, "category": m.category, "status": m.status}
    if name is not None: m.name = name.strip()
    if category is not None: m.category = category.strip()
    if status is not None:
        if status not in ("ACTIVE", "INACTIVE"):
            raise ValidationFailure("Invalid merchant status", code="INVALID_STATUS")
        m.status = status
    db.flush()
    audit.record_event(db, institution_id=institution_id, actor_id=actor_id, actor_role=actor_role,
                       event_type="MERCHANT_UPDATED", entity_type="Merchant", entity_id=m.id, previous=prev,
                       new={"name": m.name, "category": m.category, "status": m.status})
    return _mv(m)


# -- catalog ---------------------------------------------------------------------------------------
def set_accepting_orders(db, *, institution_id, merchant_id, actor_id, accepting):
    row = db.execute(select(Merchant).where(Merchant.institution_id == institution_id,
        Merchant.id == merchant_id).with_for_update()).scalar_one_or_none()
    if not row or row.status != ACTIVE:
        raise ForbiddenError("This merchant is disabled by the administrator", code="MERCHANT_INACTIVE")
    row.accepting_orders = int(accepting)
    audit.record_event(db, institution_id=institution_id, actor_id=actor_id, actor_role="MERCHANT_STAFF",
        event_type="CANTEEN_AVAILABILITY_CHANGED", entity_type="Merchant", entity_id=row.id,
        new={"accepting_orders": accepting})
    db.flush()
    return _mv(row)


def _menu_authority(role: str) -> None:
    # MG-08 (OPEN): who may change menu availability/price. Provisional, configurable set.
    if role not in get_settings().menu_manage_roles:
        raise ForbiddenError("Role may not manage the menu", code="MENU_AUTHORITY_DENIED")


def create_category(db: Session, *, institution_id: str, merchant_id: str, name: str, display_order: int,
                    actor_user_id: str, actor_role: str) -> dict:
    _menu_authority(actor_role)
    require_merchant_scope(db, institution_id=institution_id, actor_user_id=actor_user_id, actor_role=actor_role,
                           merchant_id=merchant_id)
    c = ProductCategory(institution_id=institution_id, merchant_id=merchant_id, name=name.strip(),
                        display_order=display_order, status=ACTIVE)
    try:
        with db.begin_nested():
            db.add(c)
            db.flush()
    except IntegrityError as exc:
        raise ConflictError("Category already exists for this merchant", code="CATEGORY_EXISTS") from exc
    audit.record_event(db, institution_id=institution_id, actor_id=actor_user_id, actor_role=actor_role,
                       event_type="CATEGORY_CREATED", entity_type="ProductCategory", entity_id=c.id, new={"name": c.name})
    return {"id": c.id, "merchant_id": merchant_id, "name": c.name, "display_order": c.display_order, "status": c.status}


def update_category(db: Session, *, institution_id: str, category_id: str, actor_user_id: str, actor_role: str,
                    name: Optional[str] = None, display_order: Optional[int] = None, status: Optional[str] = None) -> dict:
    _menu_authority(actor_role)
    c = db.execute(select(ProductCategory).where(ProductCategory.institution_id == institution_id,
                                                 ProductCategory.id == category_id)).scalar_one_or_none()
    if c is None:
        raise NotFoundError("Category not found", code="CATEGORY_NOT_FOUND")
    require_merchant_scope(db, institution_id=institution_id, actor_user_id=actor_user_id, actor_role=actor_role,
                           merchant_id=c.merchant_id)
    prev = {"name": c.name, "display_order": c.display_order, "status": c.status}
    if name is not None:
        c.name = name.strip()
    if display_order is not None:
        c.display_order = display_order
    if status is not None:
        if status not in ("ACTIVE", "INACTIVE"):
            raise ValidationFailure("Invalid status", code="INVALID_STATUS")
        c.status = status
    db.flush()
    audit.record_event(db, institution_id=institution_id, actor_id=actor_user_id, actor_role=actor_role,
                       event_type="CATEGORY_UPDATED", entity_type="ProductCategory", entity_id=c.id, previous=prev,
                       new={"name": c.name, "display_order": c.display_order, "status": c.status})
    return {"id": c.id, "merchant_id": c.merchant_id, "name": c.name, "display_order": c.display_order, "status": c.status}


def _valid_price(price_cu: int) -> int:
    try:
        return validate_cu(price_cu)
    except CampusUnitError as exc:
        raise ValidationFailure(str(exc), code="INVALID_PRICE") from exc


def create_product(db: Session, *, institution_id: str, category_id: str, name: str, price_cu: int,
                   description: Optional[str], actor_user_id: str, actor_role: str,
                   availability: str = AVAILABLE, stock_quantity: int = 25) -> ProductView:
    _menu_authority(actor_role)
    cat = db.execute(select(ProductCategory).where(ProductCategory.institution_id == institution_id,
                                                   ProductCategory.id == category_id)).scalar_one_or_none()
    if cat is None:
        raise NotFoundError("Category not found", code="CATEGORY_NOT_FOUND")
    require_merchant_scope(db, institution_id=institution_id, actor_user_id=actor_user_id, actor_role=actor_role,
                           merchant_id=cat.merchant_id)
    if availability not in AVAILABILITIES:
        raise ValidationFailure("Invalid availability", code="INVALID_AVAILABILITY")
    if not isinstance(stock_quantity, int) or isinstance(stock_quantity, bool) or stock_quantity < 0:
        raise ValidationFailure("Stock quantity must be a non-negative whole number", code="INVALID_STOCK")
    p = Product(institution_id=institution_id, merchant_id=cat.merchant_id, category_id=cat.id, name=name.strip(),
                description=description, price_cu=_valid_price(price_cu), stock_quantity=stock_quantity, availability=availability, status=ACTIVE,
                updated_by=actor_user_id)
    db.add(p)
    db.flush()
    audit.record_event(db, institution_id=institution_id, actor_id=actor_user_id, actor_role=actor_role,
                       event_type="PRODUCT_CREATED", entity_type="Product", entity_id=p.id,
                       new={"name": p.name, "price_cu": p.price_cu, "availability": availability})
    return _pv(p)


def update_product(db: Session, *, institution_id: str, product_id: str, actor_user_id: str, actor_role: str,
                   name: Optional[str] = None, description: Optional[str] = None, price_cu: Optional[int] = None,
                   availability: Optional[str] = None, status: Optional[str] = None, stock_quantity: Optional[int] = None) -> ProductView:
    _menu_authority(actor_role)
    p = db.execute(select(Product).where(Product.institution_id == institution_id, Product.id == product_id)
                   .with_for_update()).scalar_one_or_none()
    if p is None:
        raise NotFoundError("Product not found", code="PRODUCT_NOT_FOUND")
    require_merchant_scope(db, institution_id=institution_id, actor_user_id=actor_user_id, actor_role=actor_role,
                           merchant_id=p.merchant_id)
    prev = {"name": p.name, "price_cu": p.price_cu, "availability": p.availability, "status": p.status}
    if name is not None:
        p.name = name.strip()
    if description is not None:
        p.description = description
    if price_cu is not None:
        p.price_cu = _valid_price(price_cu)
    if stock_quantity is not None:
        if not isinstance(stock_quantity, int) or isinstance(stock_quantity, bool) or stock_quantity < 0:
            raise ValidationFailure("Stock quantity must be a non-negative whole number", code="INVALID_STOCK")
        p.stock_quantity = stock_quantity
        if stock_quantity == 0:
            p.availability = SOLD_OUT
    if availability is not None:
        if availability not in AVAILABILITIES:
            raise ValidationFailure("Invalid availability", code="INVALID_AVAILABILITY")
        p.availability = availability
    if status is not None:
        if status not in ("ACTIVE", "INACTIVE"):
            raise ValidationFailure("Invalid status", code="INVALID_STATUS")
        p.status = status
    p.updated_by = actor_user_id
    db.flush()
    new = {"name": p.name, "price_cu": p.price_cu, "availability": p.availability, "status": p.status}
    event_type = "PRODUCT_AVAILABILITY_CHANGED" if (prev["availability"] != p.availability and
                                                     prev["price_cu"] == p.price_cu and prev["name"] == p.name) else "PRODUCT_UPDATED"
    audit.record_event(db, institution_id=institution_id, actor_id=actor_user_id, actor_role=actor_role,
                       event_type=event_type, entity_type="Product", entity_id=p.id, previous=prev, new=new)
    return _pv(p)


def get_menu(db: Session, *, institution_id: str, merchant_id: str, actor_user_id: str, actor_role: str) -> dict:
    merchant = require_merchant_scope(db, institution_id=institution_id, actor_user_id=actor_user_id,
                                      actor_role=actor_role, merchant_id=merchant_id)
    cats = db.execute(select(ProductCategory).where(
        ProductCategory.institution_id == institution_id, ProductCategory.merchant_id == merchant_id,
        ProductCategory.status == ACTIVE).order_by(ProductCategory.display_order, ProductCategory.name)).scalars().all()
    prods = db.execute(select(Product).where(
        Product.institution_id == institution_id, Product.merchant_id == merchant_id,
        Product.status == ACTIVE).order_by(Product.name)).scalars().all()
    return {"merchant": {"id": merchant.id, "name": merchant.name, "status": merchant.status,
                         "accepting_orders": merchant.accepting_orders},
            "categories": [{"id": c.id, "name": c.name, "products": [
                {"id": p.id, "name": p.name, "description": p.description, "price_cu": p.price_cu,
                 "stock_quantity": p.stock_quantity, "availability": p.availability} for p in prods if p.category_id == c.id]} for c in cats]}


def count_products(db: Session, *, institution_id: str) -> int:
    from sqlalchemy import func
    return int(db.execute(select(func.count()).select_from(Product).where(Product.institution_id == institution_id)).scalar_one())


def list_products(db: Session, *, institution_id: str) -> list[dict]:
    rows = db.execute(select(Product, Merchant.name).join(Merchant, Merchant.id == Product.merchant_id).where(
        Product.institution_id == institution_id).order_by(Merchant.name, Product.name)).all()
    return [{"id": p.id, "merchant_id": p.merchant_id, "merchant": mname, "name": p.name, "price_cu": p.price_cu, "stock_quantity": p.stock_quantity, "availability": p.availability,
             "status": p.status} for p, mname in rows]


# -- orders ---------------------------------------------------------------------------------------------

def _load_order(db: Session, institution_id: str, order_id: str, *, for_update: bool = False) -> Order:
    stmt = select(Order).where(Order.institution_id == institution_id, Order.id == order_id)
    if for_update:
        stmt = stmt.with_for_update()
    o = db.execute(stmt).scalar_one_or_none()
    if o is None:
        raise NotFoundError("Order not found", code="ORDER_NOT_FOUND")
    return o


def create_order(db: Session, *, institution_id: str, merchant_id: str, customer_id: str,
                 items: list[tuple[str, int]], actor_user_id: str, actor_role: str, device_id: Optional[str] = None,
                 client_request_key: Optional[str] = None) -> tuple[OrderView, bool]:
    """Create the authoritative Order. The client supplies only product ids and quantities; the server
    derives prices, line totals and the order total and snapshots the unit price on every line.
    Returns (order, replayed). No wallet, ledger or payment is touched."""
    if actor_role == users.STUDENT and customer_id != actor_user_id:
        raise ForbiddenError("Students may only create orders for themselves", code="CUSTOMER_SCOPE_VIOLATION")
    require_merchant_scope(db, institution_id=institution_id, actor_user_id=actor_user_id, actor_role=actor_role,
                           merchant_id=merchant_id)
    merchant = get_merchant(db, institution_id=institution_id, merchant_id=merchant_id)
    if merchant.status != ACTIVE or not merchant.accepting_orders:
        raise ConflictError("Merchant is not active", code="MERCHANT_INACTIVE")
    users.require_active_customer(db, institution_id=institution_id, user_id=customer_id)
    if device_id:
        devices.require_active_kiosk_for_merchant(db, institution_id=institution_id, device_id=device_id,
                                                  merchant_id=merchant_id)
    merged: dict[str, int] = {}
    for product_id, qty in items:
        if not isinstance(qty, int) or isinstance(qty, bool) or qty < 1 or qty > MAX_QUANTITY_PER_LINE:
            raise ValidationFailure("Quantity must be a whole number between 1 and %d" % MAX_QUANTITY_PER_LINE,
                                    code="INVALID_QUANTITY")
        merged[product_id] = merged.get(product_id, 0) + qty
    if not merged:
        raise ValidationFailure("An order needs at least one item", code="EMPTY_ORDER")

    if client_request_key:
        existing = db.execute(select(Order).where(Order.institution_id == institution_id,
                                                  Order.client_request_key == client_request_key)).scalar_one_or_none()
        if existing is not None:
            return _replay_or_conflict(db, existing, merchant_id, customer_id, merged)

    products = {p.id: p for p in db.execute(select(Product).where(
        Product.institution_id == institution_id, Product.merchant_id == merchant_id,
        Product.id.in_(list(merged)))).scalars()}
    lines, total = [], 0
    for product_id, qty in merged.items():
        p = products.get(product_id)
        if p is None:
            raise NotFoundError("Product not found for this merchant", code="PRODUCT_NOT_FOUND")
        if p.status != ACTIVE or p.availability == UNAVAILABLE:
            raise ConflictError(f"{p.name} is not available", code="PRODUCT_UNAVAILABLE")
        if p.availability == SOLD_OUT or p.stock_quantity <= 0:
            raise ConflictError(f"{p.name} is sold out", code="PRODUCT_SOLD_OUT")
        if qty > p.stock_quantity:
            raise ConflictError(f"Only {p.stock_quantity} unit(s) of {p.name} are available", code="INSUFFICIENT_STOCK")
        line_total = p.price_cu * qty
        total += line_total
        if total > MAX_CU:
            raise ValidationFailure("Order total out of range", code="INVALID_AMOUNT")
        lines.append((p, qty, line_total))

    order = Order(institution_id=institution_id, merchant_id=merchant_id, campus_user_id=customer_id,
                  device_id=device_id, reference=opaque_reference("ORD"), status=ORDER_CREATED, total_cu=total,
                  client_request_key=client_request_key)
    try:
        with db.begin_nested():
            db.add(order)
            db.flush()
    except IntegrityError:
        if client_request_key:  # concurrent creation with the same key: replay the winner
            existing = db.execute(select(Order).where(Order.institution_id == institution_id,
                                                      Order.client_request_key == client_request_key)).scalar_one()
            return _replay_or_conflict(db, existing, merchant_id, customer_id, merged)
        raise
    for p, qty, line_total in lines:
        db.add(OrderItem(institution_id=institution_id, order_id=order.id, product_id=p.id,
                         product_name_snapshot=p.name, unit_price_cu_snapshot=p.price_cu, quantity=qty,
                         line_total_cu=line_total))
    db.flush()
    audit.record_event(db, institution_id=institution_id, actor_id=actor_user_id, actor_role=actor_role,
                       source_device_id=device_id, event_type="ORDER_CREATED", entity_type="Order", entity_id=order.id,
                       reference=order.reference, new={"total_cu": total, "customer_id": customer_id, "lines": len(lines)})
    return _ov(db, order), False


def _replay_or_conflict(db: Session, existing: Order, merchant_id: str, customer_id: str,
                        merged: dict[str, int]) -> tuple[OrderView, bool]:
    view = _ov(db, existing)
    same_items = {i.product_id: i.quantity for i in view.items} == merged
    if existing.merchant_id != merchant_id or existing.campus_user_id != customer_id or not same_items:
        raise ConflictError("Request key already used for a different order", code="IDEMPOTENCY_KEY_REUSED")
    return view, True


def get_order(db: Session, *, institution_id: str, order_id: str, actor_user_id: str, actor_role: str) -> OrderView:
    o = _load_order(db, institution_id, order_id)
    if actor_role == users.STUDENT and o.campus_user_id != actor_user_id:
        raise ForbiddenError("This order belongs to another student", code="ORDER_SCOPE_VIOLATION")
    require_merchant_scope(db, institution_id=institution_id, actor_user_id=actor_user_id, actor_role=actor_role,
                           merchant_id=o.merchant_id)
    return _ov(db, o)


def cancel_order(db: Session, *, institution_id: str, order_id: str, actor_user_id: str, actor_role: str) -> OrderView:
    """Cancel an UNPAID order. No financial effect (Invariant 5). Paid-order cancellation is MG-15 (OPEN): refused."""
    o = _load_order(db, institution_id, order_id, for_update=True)
    if actor_role == users.STUDENT and o.campus_user_id != actor_user_id:
        raise ForbiddenError("This order belongs to another student", code="ORDER_SCOPE_VIOLATION")
    require_merchant_scope(db, institution_id=institution_id, actor_user_id=actor_user_id, actor_role=actor_role,
                           merchant_id=o.merchant_id)
    if o.status == ORDER_PAID:
        raise ConflictError("Paid-order cancellation is not available (policy OPEN)", code="PAID_ORDER_CANCELLATION_OPEN")
    if o.status == ORDER_CANCELLED:
        return _ov(db, o)
    o.status = ORDER_CANCELLED
    db.flush()
    audit.record_event(db, institution_id=institution_id, actor_id=actor_user_id, actor_role=actor_role,
                       event_type="ORDER_CANCELLED", entity_type="Order", entity_id=o.id, previous={"status": ORDER_CREATED},
                       new={"status": ORDER_CANCELLED}, reference=o.reference)
    return _ov(db, o)


def lock_order_for_payment(db: Session, *, institution_id: str, order_id: str) -> OrderView:
    """Row-lock the order (serialises concurrent payment attempts on it) and return its view."""
    return _ov(db, _load_order(db, institution_id, order_id, for_update=True))


def mark_order_paid(db: Session, *, institution_id: str, order_id: str, actor_id: Optional[str],
                    actor_role: Optional[str] = None) -> OrderView:
    """Called by Payments inside the payment transaction once the PURCHASE has been recorded."""
    o = _load_order(db, institution_id, order_id, for_update=True)
    if o.status != ORDER_CREATED:
        raise ConflictError("Order is not payable", code="ORDER_NOT_PAYABLE")
    items = db.execute(select(OrderItem).where(OrderItem.institution_id == institution_id, OrderItem.order_id == o.id)
        .order_by(OrderItem.product_id)).scalars().all()
    for item in items:
        product = db.execute(select(Product).where(Product.institution_id == institution_id, Product.id == item.product_id).with_for_update()).scalar_one()
        if product.status != ACTIVE or product.availability != AVAILABLE or product.stock_quantity < item.quantity:
            raise ConflictError(f"Insufficient stock for {item.product_name_snapshot}", code="INSUFFICIENT_STOCK")
        product.stock_quantity -= item.quantity
        if product.stock_quantity == 0:
            product.availability = SOLD_OUT
    o.status = ORDER_PAID
    db.add(Fulfillment(institution_id=institution_id, order_id=o.id, merchant_id=o.merchant_id, status=F_PAID,
                       paid_at=utcnow()))
    db.flush()
    audit.record_event(db, institution_id=institution_id, actor_id=actor_id, actor_role=actor_role,
                       event_type="ORDER_PAID", entity_type="Order", entity_id=o.id, reference=o.reference,
                       previous={"status": ORDER_CREATED}, new={"status": ORDER_PAID})
    return _ov(db, o)


def list_orders(db: Session, *, institution_id: str, actor_user_id: str, actor_role: str,
                merchant_id: Optional[str] = None, fulfillment_status: Optional[str] = None, limit: int = 100) -> list[OrderView]:
    if actor_role == users.MERCHANT_STAFF:
        merchant_id = staff_merchant_id(db, institution_id=institution_id, campus_user_id=actor_user_id) or "-"
    stmt = select(Order).where(Order.institution_id == institution_id)
    if merchant_id:
        stmt = stmt.where(Order.merchant_id == merchant_id)
    if fulfillment_status:
        stmt = stmt.join(Fulfillment, Fulfillment.order_id == Order.id).where(Fulfillment.status == fulfillment_status)
    rows = db.execute(stmt.order_by(Order.created_at.desc()).limit(min(max(limit, 1), 300))).scalars().all()
    return [_ov(db, o) for o in rows]


def order_summary(db: Session, *, institution_id: str) -> dict:
    from sqlalchemy import func
    rows = db.execute(select(Order.status, func.count()).where(Order.institution_id == institution_id).group_by(Order.status))
    return {s: int(n) for s, n in rows}


# -- fulfillment -----------------------------------------------------------------------------------------

def advance_fulfillment(db: Session, *, institution_id: str, order_id: str, to_status: str, actor_user_id: str,
                        actor_role: str) -> OrderView:
    """PAID -> PREPARING -> READY -> COLLECTED. Touches no financial state."""
    o = _load_order(db, institution_id, order_id)
    require_merchant_scope(db, institution_id=institution_id, actor_user_id=actor_user_id, actor_role=actor_role,
                           merchant_id=o.merchant_id)
    f = db.execute(select(Fulfillment).where(Fulfillment.institution_id == institution_id,
                                             Fulfillment.order_id == order_id).with_for_update()).scalar_one_or_none()
    if f is None:
        raise ConflictError("Order has no fulfillment (it is not paid)", code="ORDER_NOT_PAID")
    if _FULFILLMENT_NEXT.get(f.status) != to_status:
        raise ConflictError(f"Invalid fulfillment transition {f.status} -> {to_status}",
                            code="INVALID_FULFILLMENT_TRANSITION")
    previous, f.status, f.updated_by = f.status, to_status, actor_user_id
    setattr(f, {F_PREPARING: "preparing_at", F_READY: "ready_at", F_COLLECTED: "collected_at"}[to_status], utcnow())
    db.flush()
    audit.record_event(db, institution_id=institution_id, actor_id=actor_user_id, actor_role=actor_role,
                       event_type=_FULFILLMENT_AUDIT[to_status], entity_type="Fulfillment", entity_id=f.id,
                       reference=o.reference, previous={"status": previous}, new={"status": to_status})
    return _ov(db, o)


def describe_order(db: Session, *, institution_id: str, order_id: str) -> OrderView:
    """System read of an order (no actor scoping) for internal collaborators such as receipt issuance."""
    return _ov(db, _load_order(db, institution_id, order_id))
