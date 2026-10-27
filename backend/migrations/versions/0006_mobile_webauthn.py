"""Mobile passkeys and single-use server verification challenges."""
from alembic import op
import sqlalchemy as sa
revision = "0006_mobile_webauthn"
down_revision = "0005_fingerprint_kiosk"
branch_labels = depends_on = None

def upgrade():
    op.add_column("fingerprint_challenges", sa.Column("auth_method", sa.String(16), nullable=False, server_default="SCANNER"))
    op.create_table("mobile_credentials",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("institution_id", sa.String(), sa.ForeignKey("institutions.id"), nullable=False),
        sa.Column("campus_user_id", sa.String(), sa.ForeignKey("campus_users.id"), nullable=False),
        sa.Column("credential_id", sa.String(2048), unique=True, nullable=False),
        sa.Column("public_key", sa.String(8192), nullable=False),
        sa.Column("sign_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False))
    op.create_table("mobile_ceremonies",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("institution_id", sa.String(), sa.ForeignKey("institutions.id"), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=False), sa.Column("target_id", sa.String(), nullable=False),
        sa.Column("purpose", sa.String(16), nullable=False), sa.Column("challenge", sa.String(128), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False), sa.Column("used", sa.Integer(), nullable=False))
    for table in ("mobile_credentials", "mobile_ceremonies"):
        op.create_index("ix_"+table+"_institution_id", table, ["institution_id"])
    op.create_index("ix_mobile_credentials_campus_user_id", "mobile_credentials", ["campus_user_id"])

def downgrade():
    raise RuntimeError("forward-only migration; restore a verified backup.")
