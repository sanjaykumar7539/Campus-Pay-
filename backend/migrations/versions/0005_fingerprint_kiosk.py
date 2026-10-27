"""Dedicated kiosk sessions, scanner authentication and two-capture authorization."""
from alembic import op
import sqlalchemy as sa

revision = "0005_fingerprint_kiosk"
down_revision = "0004_inventory_controls"
branch_labels = depends_on = None


def upgrade():
    op.add_column("merchants", sa.Column("accepting_orders", sa.Integer(), nullable=False, server_default="1"))
    def base():
        return [sa.Column("id", sa.String(), primary_key=True), sa.Column("institution_id", sa.String(), sa.ForeignKey("institutions.id"), nullable=False)]
    def device():
        return sa.Column("device_id", sa.String(), sa.ForeignKey("devices.id"), nullable=False)
    op.create_table("kiosk_sessions", *base(), device(),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False), sa.Column("revoked", sa.Integer(), nullable=False))
    op.create_table("scanner_agents", *base(), device(),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("last_seen_at", sa.DateTime(), nullable=True), sa.UniqueConstraint("device_id"))
    op.create_table("fingerprint_enrollments", *base(),
        sa.Column("campus_user_id", sa.String(), sa.ForeignKey("campus_users.id"), nullable=False),
        sa.Column("finger_ref", sa.String(128), nullable=False), sa.Column("status", sa.String(16), nullable=False),
        sa.Column("enrolled_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("institution_id", "finger_ref"), sa.UniqueConstraint("institution_id", "campus_user_id"))
    op.create_table("fingerprint_challenges", *base(), device(),
        sa.Column("session_id", sa.String(), sa.ForeignKey("kiosk_sessions.id"), nullable=True),
        sa.Column("purpose", sa.String(16), nullable=False), sa.Column("status", sa.String(24), nullable=False),
        sa.Column("nonce", sa.String(64), nullable=False),
        sa.Column("student_id", sa.String(), sa.ForeignKey("campus_users.id"), nullable=True),
        sa.Column("finger_ref", sa.String(128), nullable=True),
        sa.Column("order_id", sa.String(), sa.ForeignKey("orders.id"), nullable=True),
        sa.Column("cart", sa.JSON(), nullable=False), sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False))
    op.create_table("scanner_captures", *base(), device(),
        sa.Column("challenge_id", sa.String(), sa.ForeignKey("fingerprint_challenges.id"), nullable=False),
        sa.Column("capture_id", sa.String(128), nullable=False), sa.UniqueConstraint("device_id", "capture_id"))
    for table in ("kiosk_sessions", "scanner_agents", "fingerprint_enrollments", "fingerprint_challenges", "scanner_captures"):
        op.create_index("ix_" + table + "_institution_id", table, ["institution_id"])
    op.create_index("ix_fingerprint_challenges_device_id", "fingerprint_challenges", ["device_id"])
    op.create_index("ix_kiosk_sessions_device_id", "kiosk_sessions", ["device_id"])


def downgrade():
    raise RuntimeError("This is a forward-only migration. Restore a verified backup to roll back.")
