"""Inventory quantities for automatic sold-out handling.

Revision ID: 0004_inventory_controls
Revises: 0003_account_settings
"""
import sqlalchemy as sa
from alembic import op

revision = "0004_inventory_controls"
down_revision = "0003_account_settings"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("products", sa.Column("stock_quantity", sa.Integer(), nullable=False, server_default="25"))
    with op.batch_alter_table("products") as b:
        b.create_check_constraint("ck_products_stock_nonnegative", "stock_quantity >= 0")

def downgrade() -> None:
    raise RuntimeError("Inventory migration is forward-only; restore a backup to roll back")
