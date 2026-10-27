from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base
from core.tenancy import TenantScoped
from shared.clock import utcnow
from shared.ids import new_id


class Merchant(TenantScoped, Base):
    __tablename__ = "merchants"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    institution_id: Mapped[str] = mapped_column(ForeignKey("institutions.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE", nullable=False)
    accepting_orders: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class MerchantStaff(TenantScoped, Base):
    """Assignment of a MERCHANT_STAFF Campus User to the merchant they operate (one merchant per staff user in P1)."""

    __tablename__ = "merchant_staff"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    institution_id: Mapped[str] = mapped_column(ForeignKey("institutions.id"), nullable=False, index=True)
    campus_user_id: Mapped[str] = mapped_column(ForeignKey("campus_users.id"), unique=True, nullable=False)
    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchants.id"), nullable=False)


class ProductCategory(TenantScoped, Base):
    __tablename__ = "product_categories"
    __table_args__ = (UniqueConstraint("institution_id", "merchant_id", "name", name="uq_category_merchant_name"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    institution_id: Mapped[str] = mapped_column(ForeignKey("institutions.id"), nullable=False, index=True)
    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchants.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Product(TenantScoped, Base):
    __tablename__ = "products"
    __table_args__ = (CheckConstraint("price_cu > 0", name="ck_products_price_positive"), CheckConstraint("stock_quantity >= 0", name="ck_products_stock_nonnegative"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    institution_id: Mapped[str] = mapped_column(ForeignKey("institutions.id"), nullable=False, index=True)
    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchants.id"), nullable=False, index=True)
    category_id: Mapped[str] = mapped_column(ForeignKey("product_categories.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    price_cu: Mapped[int] = mapped_column(BigInteger, nullable=False)
    stock_quantity: Mapped[int] = mapped_column(Integer, default=25, nullable=False)
    availability: Mapped[str] = mapped_column(String(16), default="AVAILABLE", nullable=False)  # AVAILABLE|SOLD_OUT|UNAVAILABLE
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", nullable=False)  # ACTIVE|INACTIVE
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    updated_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)


class Order(TenantScoped, Base):
    """Authoritative server-side Order (commerce object). Separate from Payment, Receipt and Fulfillment."""

    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("institution_id", "reference", name="uq_orders_inst_reference"),
        UniqueConstraint("institution_id", "client_request_key", name="uq_orders_inst_request_key"),
        CheckConstraint("total_cu > 0", name="ck_orders_total_positive"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    institution_id: Mapped[str] = mapped_column(ForeignKey("institutions.id"), nullable=False, index=True)
    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchants.id"), nullable=False, index=True)
    campus_user_id: Mapped[str] = mapped_column(ForeignKey("campus_users.id"), nullable=False, index=True)
    device_id: Mapped[Optional[str]] = mapped_column(ForeignKey("devices.id"), nullable=True)
    reference: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="CREATED")  # CREATED|PAID|CANCELLED
    total_cu: Mapped[int] = mapped_column(BigInteger, nullable=False)
    client_request_key: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class OrderItem(TenantScoped, Base):
    """Line item with an immutable price snapshot: later menu-price changes never alter a historical order."""

    __tablename__ = "order_items"
    __table_args__ = (CheckConstraint("quantity > 0 AND unit_price_cu_snapshot > 0", name="ck_order_items_positive"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    institution_id: Mapped[str] = mapped_column(ForeignKey("institutions.id"), nullable=False, index=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), nullable=False, index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), nullable=False)
    product_name_snapshot: Mapped[str] = mapped_column(String(200), nullable=False)
    unit_price_cu_snapshot: Mapped[int] = mapped_column(BigInteger, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    line_total_cu: Mapped[int] = mapped_column(BigInteger, nullable=False)


class Fulfillment(TenantScoped, Base):
    """Physical preparation/collection state. Independent of payment: PAID -> PREPARING -> READY -> COLLECTED."""

    __tablename__ = "fulfillments"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    institution_id: Mapped[str] = mapped_column(ForeignKey("institutions.id"), nullable=False, index=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), unique=True, nullable=False)
    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchants.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PAID")
    paid_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    preparing_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    ready_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    collected_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    updated_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
