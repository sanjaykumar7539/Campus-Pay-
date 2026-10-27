"""MVP baseline schema (exactly what the MVP `create_all()` produced).

Existing MVP demo databases have no alembic_version table: adopt them with
    alembic stamp 0001_mvp_baseline
    alembic upgrade head
Fresh databases simply run `alembic upgrade head`.

Revision ID: 0001_mvp_baseline
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_mvp_baseline"
down_revision = None
branch_labels = None
depends_on = None

_status = lambda: sa.Enum("ACTIVE", "INACTIVE", "SUSPENDED", name="entitystatus")


def upgrade() -> None:
    op.create_table("institutions",
        sa.Column("id", sa.String(), primary_key=True), sa.Column("name", sa.String(), nullable=False),
        sa.Column("status", _status(), nullable=False), sa.Column("created_at", sa.DateTime()))
    op.create_table("campus_users",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("institution_id", sa.String(), sa.ForeignKey("institutions.id"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("role", sa.Enum("STUDENT", "MERCHANT_STAFF", "ADMIN", name="userrole"), nullable=False),
        sa.Column("unique_identifier", sa.String(), nullable=False, unique=True),
        sa.Column("status", _status(), nullable=False), sa.Column("created_at", sa.DateTime()))
    op.create_table("wallets",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("institution_id", sa.String(), sa.ForeignKey("institutions.id"), nullable=False),
        sa.Column("campus_user_id", sa.String(), sa.ForeignKey("campus_users.id"), nullable=False, unique=True),
        sa.Column("balance_minor", sa.BigInteger(), nullable=False),
        sa.Column("status", _status(), nullable=False),
        sa.Column("created_at", sa.DateTime()), sa.Column("updated_at", sa.DateTime()))
    op.create_table("merchants",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("institution_id", sa.String(), sa.ForeignKey("institutions.id"), nullable=False),
        sa.Column("name", sa.String(), nullable=False), sa.Column("category", sa.String(), nullable=True),
        sa.Column("status", _status(), nullable=False), sa.Column("created_at", sa.DateTime()))
    op.create_table("payments",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("institution_id", sa.String(), sa.ForeignKey("institutions.id"), nullable=True),
        sa.Column("campus_user_id", sa.String(), sa.ForeignKey("campus_users.id"), nullable=True),
        sa.Column("merchant_id", sa.String(), sa.ForeignKey("merchants.id"), nullable=True),
        sa.Column("wallet_id", sa.String(), sa.ForeignKey("wallets.id"), nullable=True),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.Enum("INITIATED", "COMPLETED", "FAILED", name="paymentstatus"), nullable=False),
        sa.Column("failure_reason", sa.String(), nullable=True),
        sa.Column("reference", sa.String(), nullable=False, unique=True),
        sa.Column("item_description", sa.String(), nullable=True), sa.Column("created_at", sa.DateTime()))
    op.create_table("wallet_transactions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("institution_id", sa.String(), sa.ForeignKey("institutions.id"), nullable=False),
        sa.Column("wallet_id", sa.String(), sa.ForeignKey("wallets.id"), nullable=False),
        sa.Column("payment_id", sa.String(), sa.ForeignKey("payments.id"), nullable=True),
        sa.Column("type", sa.Enum("RECHARGE", "DEBIT", "REVERSAL", name="wallettxntype"), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("balance_before_minor", sa.BigInteger(), nullable=False),
        sa.Column("balance_after_minor", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(), nullable=False), sa.Column("created_at", sa.DateTime()))
    op.create_table("audit_logs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("institution_id", sa.String(), sa.ForeignKey("institutions.id"), nullable=True),
        sa.Column("actor_id", sa.String(), nullable=True), sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("entity_type", sa.String(), nullable=False), sa.Column("entity_id", sa.String(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True), sa.Column("created_at", sa.DateTime()))


def downgrade() -> None:
    for t in ("audit_logs", "wallet_transactions", "payments", "merchants", "wallets", "campus_users", "institutions"):
        op.drop_table(t)
    if op.get_bind().dialect.name == "postgresql":
        for e in ("wallettxntype", "paymentstatus", "userrole", "entitystatus"):
            op.execute(f"DROP TYPE IF EXISTS {e}")
