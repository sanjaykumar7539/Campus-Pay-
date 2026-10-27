"""Invalidate earlier sessions when login credentials are changed.

Revision ID: 0003_account_settings
Revises: 0002_p1_campus_commerce
"""
import sqlalchemy as sa
from alembic import op

revision = "0003_account_settings"
down_revision = "0002_p1_campus_commerce"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("credentials", sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    raise RuntimeError("Account security migration is forward-only; restore a backup to roll back")
