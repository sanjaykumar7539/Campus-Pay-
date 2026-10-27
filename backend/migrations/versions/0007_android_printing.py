"""Device-specific authentication/receipt modes and trusted print jobs."""
from alembic import op
import sqlalchemy as sa
revision="0007_android_printing"
down_revision="0006_mobile_webauthn"
branch_labels=depends_on=None

def upgrade():
    op.add_column("kiosk_sessions",sa.Column("authentication_mode",sa.String(16),nullable=False,server_default="AUTO"))
    op.add_column("kiosk_sessions",sa.Column("receipt_mode",sa.String(16),nullable=False,server_default="BROWSER"))
    op.create_table("printer_agents",sa.Column("id",sa.String(),primary_key=True),
        sa.Column("institution_id",sa.String(),sa.ForeignKey("institutions.id"),nullable=False),
        sa.Column("device_id",sa.String(),sa.ForeignKey("devices.id"),unique=True,nullable=False),
        sa.Column("token_hash",sa.String(64),unique=True,nullable=False),sa.Column("last_seen_at",sa.DateTime()))
    op.create_table("print_jobs",sa.Column("id",sa.String(),primary_key=True),
        sa.Column("institution_id",sa.String(),sa.ForeignKey("institutions.id"),nullable=False),
        sa.Column("device_id",sa.String(),sa.ForeignKey("devices.id"),nullable=False),
        sa.Column("checkout_id",sa.String(),sa.ForeignKey("fingerprint_challenges.id"),unique=True,nullable=False),
        sa.Column("snapshot",sa.JSON(),nullable=False),sa.Column("state",sa.String(16),nullable=False),
        sa.Column("claimed_at",sa.DateTime()),sa.Column("created_at",sa.DateTime(),nullable=False))
    for t in ("printer_agents","print_jobs"):op.create_index('ix_'+t+'_institution_id',t,['institution_id'])
    op.create_index('ix_print_jobs_device_id','print_jobs',['device_id'])

def downgrade():raise RuntimeError('forward-only migration; restore a verified backup')
