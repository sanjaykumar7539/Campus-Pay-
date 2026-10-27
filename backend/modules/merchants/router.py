from typing import Optional

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from core.errors import ok
from core.security import require_roles, tenant_db
from core.tenancy import Principal
from modules.merchants import service
from modules.merchants.service import OrderView
from modules.users import service as users
from modules.users.service import IdentitySignal

router = APIRouter(prefix="/api/v1", tags=["merchants"])
STAFF = ("ADMIN", "MERCHANT_STAFF")
SHOPPERS = ("ADMIN", "MERCHANT_STAFF", "STUDENT")


class CategoryCreate(BaseModel):
    merchant_id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    display_order: int = 0


class CategoryUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    display_order: Optional[int] = None
    status: Optional[str] = Field(default=None, pattern="^(ACTIVE|INACTIVE)$")


class ProductCreate(BaseModel):
    category_id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=1000)
    price_cu: int = Field(gt=0, description="Whole Campus Units (₹1 = 1 CU)")
    availability: str = Field(default="AVAILABLE", pattern="^(AVAILABLE|SOLD_OUT|UNAVAILABLE)$")
    stock_quantity: int = Field(default=25, ge=0)


class ProductUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=1000)
    price_cu: Optional[int] = Field(default=None, gt=0)
    availability: Optional[str] = Field(default=None, pattern="^(AVAILABLE|SOLD_OUT|UNAVAILABLE)$")
    status: Optional[str] = Field(default=None, pattern="^(ACTIVE|INACTIVE)$")
    stock_quantity: Optional[int] = Field(default=None, ge=0)


class MerchantUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    category: Optional[str] = Field(default=None, min_length=1, max_length=100)
    status: Optional[str] = Field(default=None, pattern="^(ACTIVE|INACTIVE)$")


class OrderLine(BaseModel):
    product_id: str = Field(min_length=1, max_length=64)
    quantity: int = Field(ge=1, le=1000)


class IdentityIn(BaseModel):
    kind: str = Field(default="CAMPUS_ID", max_length=32)
    value: str = Field(min_length=1, max_length=128)


class OrderCreate(BaseModel):
    """The client sends product ids and quantities ONLY. Any price/total field is rejected."""
    model_config = ConfigDict(extra="forbid")
    merchant_id: str = Field(min_length=1, max_length=64)
    identity: IdentityIn
    items: list[OrderLine] = Field(min_length=1, max_length=100)
    client_request_key: Optional[str] = Field(default=None, min_length=8, max_length=128)


def order_out(o: OrderView) -> dict:
    return {"id": o.id, "reference": o.reference, "status": o.status, "merchant_id": o.merchant_id,
            "customer_id": o.customer_id, "device_id": o.device_id, "total_cu": o.total_cu,
            "created_at": o.created_at.isoformat(),
            "items": [{"product_id": i.product_id, "name": i.name, "unit_price_cu": i.unit_price_cu,
                       "quantity": i.quantity, "line_total_cu": i.line_total_cu} for i in o.items],
            "fulfillment": None if o.fulfillment is None else {
                "status": o.fulfillment.status, "paid_at": o.fulfillment.paid_at.isoformat(),
                "preparing_at": o.fulfillment.preparing_at and o.fulfillment.preparing_at.isoformat(),
                "ready_at": o.fulfillment.ready_at and o.fulfillment.ready_at.isoformat(),
                "collected_at": o.fulfillment.collected_at and o.fulfillment.collected_at.isoformat()}}


@router.get("/merchants")
def list_merchants(principal: Principal = Depends(require_roles(*SHOPPERS)), db: Session = Depends(tenant_db)):
    rows = service.list_merchants(db, institution_id=principal.institution_id, actor_user_id=principal.user_id,
                                  actor_role=principal.role)
    return ok([{"id": m.id, "name": m.name, "category": m.category, "status": m.status,
                "accepting_orders": m.accepting_orders} for m in rows])


@router.patch("/merchants/{merchant_id}")
def update_merchant(merchant_id: str, body: MerchantUpdate, principal: Principal = Depends(require_roles("ADMIN")),
                    db: Session = Depends(tenant_db)):
    m = service.update_merchant(db, institution_id=principal.institution_id, merchant_id=merchant_id,
                                actor_id=principal.user_id, **body.model_dump(exclude_unset=True))
    db.commit()
    return ok({"id": m.id, "name": m.name, "category": m.category, "status": m.status})


@router.get("/merchants/{merchant_id}/menu")
def merchant_menu(merchant_id: str, principal: Principal = Depends(require_roles(*SHOPPERS)), db: Session = Depends(tenant_db)):
    return ok(service.get_menu(db, institution_id=principal.institution_id, merchant_id=merchant_id,
                               actor_user_id=principal.user_id, actor_role=principal.role))


@router.get("/products")
def list_products(principal: Principal = Depends(require_roles("ADMIN", "MERCHANT_STAFF")), db: Session = Depends(tenant_db)):
    rows = service.list_products(db, institution_id=principal.institution_id)
    if principal.role == "MERCHANT_STAFF":
        own = service.staff_merchant_id(db, institution_id=principal.institution_id, campus_user_id=principal.user_id)
        rows = [r for r in rows if r.get("merchant_id") == own]
    return ok(rows)


@router.post("/categories", status_code=201)
def create_category(body: CategoryCreate, principal: Principal = Depends(require_roles(*STAFF)), db: Session = Depends(tenant_db)):
    out = service.create_category(db, institution_id=principal.institution_id, merchant_id=body.merchant_id, name=body.name,
                                  display_order=body.display_order, actor_user_id=principal.user_id, actor_role=principal.role)
    db.commit()
    return ok(out, "Category created")


@router.patch("/categories/{category_id}")
def update_category(category_id: str, body: CategoryUpdate, principal: Principal = Depends(require_roles(*STAFF)),
                    db: Session = Depends(tenant_db)):
    out = service.update_category(db, institution_id=principal.institution_id, category_id=category_id,
                                  actor_user_id=principal.user_id, actor_role=principal.role, **body.model_dump(exclude_unset=True))
    db.commit()
    return ok(out)


def _pout(p: service.ProductView) -> dict:
    return {"id": p.id, "merchant_id": p.merchant_id, "category_id": p.category_id, "name": p.name,
            "description": p.description, "price_cu": p.price_cu, "stock_quantity": p.stock_quantity, "availability": p.availability, "status": p.status}


@router.post("/products", status_code=201)
def create_product(body: ProductCreate, principal: Principal = Depends(require_roles(*STAFF)), db: Session = Depends(tenant_db)):
    p = service.create_product(db, institution_id=principal.institution_id, category_id=body.category_id, name=body.name,
                               price_cu=body.price_cu, description=body.description, availability=body.availability, stock_quantity=body.stock_quantity,
                               actor_user_id=principal.user_id, actor_role=principal.role)
    db.commit()
    return ok(_pout(p), "Product created")


@router.patch("/products/{product_id}")
def update_product(product_id: str, body: ProductUpdate, principal: Principal = Depends(require_roles(*STAFF)),
                   db: Session = Depends(tenant_db)):
    p = service.update_product(db, institution_id=principal.institution_id, product_id=product_id,
                               actor_user_id=principal.user_id, actor_role=principal.role, **body.model_dump(exclude_unset=True))
    db.commit()
    return ok(_pout(p))


@router.post("/orders", status_code=201)
def create_order(body: OrderCreate, x_device_id: Optional[str] = Header(default=None),
                 principal: Principal = Depends(require_roles(*SHOPPERS)), db: Session = Depends(tenant_db)):
    """Server-authoritative order: identify customer, price from the catalog, snapshot prices. No wallet impact."""
    identity = IdentitySignal("CAMPUS_ID", principal.username) if principal.role == "STUDENT" else IdentitySignal(body.identity.kind, body.identity.value)
    customer = users.resolve_customer(db, institution_id=principal.institution_id, signal=identity)
    order, replayed = service.create_order(
        db, institution_id=principal.institution_id, merchant_id=body.merchant_id, customer_id=customer.id,
        items=[(i.product_id, i.quantity) for i in body.items], actor_user_id=principal.user_id,
        actor_role=principal.role, device_id=x_device_id, client_request_key=body.client_request_key)
    db.commit()
    data = order_out(order)
    data["customer"] = {"display_name": customer.name, "campus_id": customer.unique_identifier}
    data["replayed"] = replayed
    return ok(data, "Order created")


@router.get("/orders/{order_id}")
def get_order(order_id: str, principal: Principal = Depends(require_roles(*SHOPPERS)), db: Session = Depends(tenant_db)):
    return ok(order_out(service.get_order(db, institution_id=principal.institution_id, order_id=order_id,
                                          actor_user_id=principal.user_id, actor_role=principal.role)))


@router.post("/orders/{order_id}/cancel")
def cancel_order(order_id: str, principal: Principal = Depends(require_roles(*SHOPPERS)), db: Session = Depends(tenant_db)):
    o = service.cancel_order(db, institution_id=principal.institution_id, order_id=order_id,
                             actor_user_id=principal.user_id, actor_role=principal.role)
    db.commit()
    return ok(order_out(o), "Order cancelled (no financial effect)")


@router.get("/merchant/orders")
def merchant_orders(merchant_id: Optional[str] = None, fulfillment_status: Optional[str] = None, limit: int = 100,
                    principal: Principal = Depends(require_roles(*STAFF)), db: Session = Depends(tenant_db)):
    rows = service.list_orders(db, institution_id=principal.institution_id, actor_user_id=principal.user_id,
                               actor_role=principal.role, merchant_id=merchant_id,
                               fulfillment_status=fulfillment_status, limit=limit)
    return ok([order_out(o) for o in rows])


def _transition(order_id: str, to_status: str, principal: Principal, db: Session):
    o = service.advance_fulfillment(db, institution_id=principal.institution_id, order_id=order_id, to_status=to_status,
                                    actor_user_id=principal.user_id, actor_role=principal.role)
    db.commit()
    return ok(order_out(o))


@router.post("/orders/{order_id}/fulfillment/prepare")
def prepare(order_id: str, principal: Principal = Depends(require_roles(*STAFF)), db: Session = Depends(tenant_db)):
    return _transition(order_id, service.F_PREPARING, principal, db)


@router.post("/orders/{order_id}/fulfillment/ready")
def ready(order_id: str, principal: Principal = Depends(require_roles(*STAFF)), db: Session = Depends(tenant_db)):
    return _transition(order_id, service.F_READY, principal, db)


@router.post("/orders/{order_id}/fulfillment/collect")
def collect(order_id: str, principal: Principal = Depends(require_roles(*STAFF)), db: Session = Depends(tenant_db)):
    return _transition(order_id, service.F_COLLECTED, principal, db)
