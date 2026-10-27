"""P1 campus commerce: tenant-scoped identity, Institution Ledger, Campus Units, commerce, PIN, devices, receipts.

Data-preserving upgrade of an MVP database (paise -> Campus Units, wallet_transactions -> ledger entries).
It REFUSES (raises) rather than rounds or guesses when legacy data cannot be represented exactly:
  * money that is not a whole number of Campus Units (₹1 = 1 CU),
  * a wallet whose stored balance disagrees with its transaction history,
  * unsupported legacy transaction types.
Forward-only: downgrading a financial schema is not supported; restore from backup instead.

Revision ID: 0002_p1_campus_commerce
Revises: 0001_mvp_baseline
"""
import re
import uuid

import sqlalchemy as sa
from alembic import op

revision = "0002_p1_campus_commerce"
down_revision = "0001_mvp_baseline"
branch_labels = None
depends_on = None

PAISE_PER_CU = 100
_BIG = sa.BigInteger()


def _cu(paise: int, what: str) -> int:
    if paise % PAISE_PER_CU != 0:
        raise RuntimeError(f"P1 migration refused: {what}={paise} paise is not a whole number of Campus Units")
    return paise // PAISE_PER_CU


def _slug(name: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "-", name.upper()).strip("-")[:48] or "INSTITUTION"


def upgrade() -> None:
    bind = op.get_bind()
    pg = bind.dialect.name == "postgresql"

    # 1. institutions.code (login tenant resolution) ----------------------------------------------------
    op.add_column("institutions", sa.Column("code", sa.String(64), nullable=True))
    used: set[str] = set()
    for inst_id, name in bind.execute(sa.text("SELECT id, name FROM institutions")).fetchall():
        code, n = _slug(name), 1
        while code in used:
            n += 1
            code = f"{_slug(name)}-{n}"
        used.add(code)
        bind.execute(sa.text("UPDATE institutions SET code=:c WHERE id=:i"), {"c": code, "i": inst_id})
    with op.batch_alter_table("institutions") as b:
        b.alter_column("code", existing_type=sa.String(64), nullable=False)
        b.create_unique_constraint("uq_institutions_code", ["code"])

    # 2. PostgreSQL native enums -> VARCHAR (portable; validated in the application) ----------------------------
    if pg:
        for table, col in (("institutions", "status"), ("campus_users", "role"), ("campus_users", "status"),
                           ("wallets", "status"), ("merchants", "status"), ("payments", "status"),
                           ("wallet_transactions", "type")):
            op.execute(f'ALTER TABLE {table} ALTER COLUMN {col} TYPE VARCHAR(32) USING {col}::text')
        for e in ("entitystatus", "userrole", "paymentstatus", "wallettxntype"):
            op.execute(f"DROP TYPE IF EXISTS {e}")

    # 3. new tables --------------------------------------------------------------------------------------------------
    op.create_table("ledger_entries",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("institution_id", sa.String(), sa.ForeignKey("institutions.id"), nullable=False),
        sa.Column("campus_user_id", sa.String(), sa.ForeignKey("campus_users.id"), nullable=False),
        sa.Column("customer_sequence", _BIG, nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False), sa.Column("direction", sa.String(8), nullable=False),
        sa.Column("amount_cu", _BIG, nullable=False), sa.Column("position_before_cu", _BIG, nullable=False),
        sa.Column("position_after_cu", _BIG, nullable=False), sa.Column("origin", sa.String(16), nullable=False),
        sa.Column("reference_type", sa.String(32), nullable=False), sa.Column("reference_id", sa.String(), nullable=False),
        sa.Column("external_reference", sa.String(), nullable=True), sa.Column("actor_id", sa.String(), nullable=True),
        sa.Column("actor_role", sa.String(32), nullable=True), sa.Column("source_device_id", sa.String(), nullable=True),
        sa.Column("reason", sa.String(), nullable=True), sa.Column("created_at", sa.DateTime()),
        sa.UniqueConstraint("institution_id", "campus_user_id", "customer_sequence", name="uq_ledger_customer_sequence"),
        sa.UniqueConstraint("institution_id", "event_type", "reference_type", "reference_id", name="uq_ledger_reference"),
        sa.CheckConstraint("amount_cu > 0", name="ck_ledger_amount_positive"),
        sa.CheckConstraint("position_before_cu >= 0 AND position_after_cu >= 0", name="ck_ledger_position_non_negative"),
        sa.CheckConstraint("(direction = 'CREDIT' AND position_after_cu = position_before_cu + amount_cu) OR "
                           "(direction = 'DEBIT' AND position_after_cu = position_before_cu - amount_cu)",
                           name="ck_ledger_position_arithmetic"))
    op.create_index("ix_ledger_entries_institution_id", "ledger_entries", ["institution_id"])

    op.create_table("credentials",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("institution_id", sa.String(), sa.ForeignKey("institutions.id"), nullable=False),
        sa.Column("campus_user_id", sa.String(), sa.ForeignKey("campus_users.id"), nullable=False, unique=True),
        sa.Column("username", sa.String(128), nullable=False), sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False), sa.Column("created_at", sa.DateTime()),
        sa.UniqueConstraint("institution_id", "username", name="uq_credentials_inst_username"))
    op.create_index("ix_credentials_institution_id", "credentials", ["institution_id"])

    op.create_table("payment_pin_credentials",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("institution_id", sa.String(), sa.ForeignKey("institutions.id"), nullable=False),
        sa.Column("campus_user_id", sa.String(), sa.ForeignKey("campus_users.id"), nullable=False, unique=True),
        sa.Column("pin_hash", sa.String(), nullable=False), sa.Column("failed_attempts", sa.Integer(), nullable=False),
        sa.Column("locked_until", sa.DateTime(), nullable=True), sa.Column("last_failed_at", sa.DateTime(), nullable=True),
        sa.Column("pin_set_at", sa.DateTime()), sa.Column("status", sa.String(32), nullable=False))
    op.create_index("ix_payment_pin_credentials_institution_id", "payment_pin_credentials", ["institution_id"])

    op.create_table("merchant_staff",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("institution_id", sa.String(), sa.ForeignKey("institutions.id"), nullable=False),
        sa.Column("campus_user_id", sa.String(), sa.ForeignKey("campus_users.id"), nullable=False, unique=True),
        sa.Column("merchant_id", sa.String(), sa.ForeignKey("merchants.id"), nullable=False))
    op.create_index("ix_merchant_staff_institution_id", "merchant_staff", ["institution_id"])

    op.create_table("devices",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("institution_id", sa.String(), sa.ForeignKey("institutions.id"), nullable=False),
        sa.Column("device_type", sa.String(32), nullable=False), sa.Column("name", sa.String(128), nullable=False),
        sa.Column("merchant_id", sa.String(), sa.ForeignKey("merchants.id"), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime()), sa.Column("updated_at", sa.DateTime()),
        sa.UniqueConstraint("institution_id", "name", name="uq_devices_inst_name"))
    op.create_index("ix_devices_institution_id", "devices", ["institution_id"])

    op.create_table("product_categories",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("institution_id", sa.String(), sa.ForeignKey("institutions.id"), nullable=False),
        sa.Column("merchant_id", sa.String(), sa.ForeignKey("merchants.id"), nullable=False),
        sa.Column("name", sa.String(128), nullable=False), sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False), sa.Column("created_at", sa.DateTime()),
        sa.UniqueConstraint("institution_id", "merchant_id", "name", name="uq_category_merchant_name"))
    op.create_index("ix_product_categories_institution_id", "product_categories", ["institution_id"])

    op.create_table("products",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("institution_id", sa.String(), sa.ForeignKey("institutions.id"), nullable=False),
        sa.Column("merchant_id", sa.String(), sa.ForeignKey("merchants.id"), nullable=False),
        sa.Column("category_id", sa.String(), sa.ForeignKey("product_categories.id"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False), sa.Column("description", sa.String(), nullable=True),
        sa.Column("price_cu", _BIG, nullable=False), sa.Column("availability", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False), sa.Column("created_at", sa.DateTime()),
        sa.Column("updated_at", sa.DateTime()), sa.Column("updated_by", sa.String(), nullable=True),
        sa.CheckConstraint("price_cu > 0", name="ck_products_price_positive"))
    op.create_index("ix_products_institution_id", "products", ["institution_id"])
    op.create_index("ix_products_merchant_id", "products", ["merchant_id"])

    op.create_table("orders",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("institution_id", sa.String(), sa.ForeignKey("institutions.id"), nullable=False),
        sa.Column("merchant_id", sa.String(), sa.ForeignKey("merchants.id"), nullable=False),
        sa.Column("campus_user_id", sa.String(), sa.ForeignKey("campus_users.id"), nullable=False),
        sa.Column("device_id", sa.String(), sa.ForeignKey("devices.id"), nullable=True),
        sa.Column("reference", sa.String(32), nullable=False), sa.Column("status", sa.String(16), nullable=False),
        sa.Column("total_cu", _BIG, nullable=False), sa.Column("client_request_key", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime()), sa.Column("updated_at", sa.DateTime()),
        sa.UniqueConstraint("institution_id", "reference", name="uq_orders_inst_reference"),
        sa.UniqueConstraint("institution_id", "client_request_key", name="uq_orders_inst_request_key"),
        sa.CheckConstraint("total_cu > 0", name="ck_orders_total_positive"))
    for col in ("institution_id", "merchant_id", "campus_user_id"):
        op.create_index(f"ix_orders_{col}", "orders", [col])

    op.create_table("order_items",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("institution_id", sa.String(), sa.ForeignKey("institutions.id"), nullable=False),
        sa.Column("order_id", sa.String(), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("product_id", sa.String(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("product_name_snapshot", sa.String(200), nullable=False),
        sa.Column("unit_price_cu_snapshot", _BIG, nullable=False), sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("line_total_cu", _BIG, nullable=False),
        sa.CheckConstraint("quantity > 0 AND unit_price_cu_snapshot > 0", name="ck_order_items_positive"))
    op.create_index("ix_order_items_institution_id", "order_items", ["institution_id"])
    op.create_index("ix_order_items_order_id", "order_items", ["order_id"])

    op.create_table("fulfillments",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("institution_id", sa.String(), sa.ForeignKey("institutions.id"), nullable=False),
        sa.Column("order_id", sa.String(), sa.ForeignKey("orders.id"), nullable=False, unique=True),
        sa.Column("merchant_id", sa.String(), sa.ForeignKey("merchants.id"), nullable=False),
        sa.Column("status", sa.String(16), nullable=False), sa.Column("paid_at", sa.DateTime()),
        sa.Column("preparing_at", sa.DateTime(), nullable=True), sa.Column("ready_at", sa.DateTime(), nullable=True),
        sa.Column("collected_at", sa.DateTime(), nullable=True), sa.Column("updated_by", sa.String(), nullable=True))
    op.create_index("ix_fulfillments_institution_id", "fulfillments", ["institution_id"])
    op.create_index("ix_fulfillments_merchant_id", "fulfillments", ["merchant_id"])

    # 4. campus_users: identifier unique PER INSTITUTION (not globally) ------------------------------------------------
    uq_name = "campus_users_unique_identifier_key" if pg else "uq_campus_users_unique_identifier"
    conv = {} if pg else {"naming_convention": {"uq": "uq_%(table_name)s_%(column_0_name)s"}}
    with op.batch_alter_table("campus_users", **conv) as b:
        b.drop_constraint(uq_name, type_="unique")
        b.create_unique_constraint("uq_campus_users_inst_identifier", ["institution_id", "unique_identifier"])
    op.create_index("ix_campus_users_institution_id", "campus_users", ["institution_id"])

    # 5. money: paise -> Campus Units; wallet_transactions -> Institution Ledger ------------------------------------------
    op.add_column("wallets", sa.Column("available_cu", _BIG, nullable=True))
    for col in ("ledger_entry_id",):
        op.add_column("wallet_transactions", sa.Column(col, sa.String(), nullable=True))
    for col in ("amount_cu", "balance_before_cu", "balance_after_cu"):
        op.add_column("wallet_transactions", sa.Column(col, _BIG, nullable=True))

    wallets = bind.execute(sa.text("SELECT id, institution_id, campus_user_id, balance_minor FROM wallets")).fetchall()
    for wallet_id, inst_id, user_id, balance_minor in wallets:
        txns = bind.execute(sa.text(
            "SELECT id, payment_id, type, amount_minor, balance_before_minor, balance_after_minor, created_at "
            "FROM wallet_transactions WHERE wallet_id=:w ORDER BY created_at, id"), {"w": wallet_id}).fetchall()
        position, seq = 0, 0
        for t_id, payment_id, t_type, amt, before_m, after_m, created in txns:
            if t_type not in ("RECHARGE", "DEBIT"):
                raise RuntimeError(f"P1 migration refused: unsupported legacy wallet transaction type {t_type}")
            amount, before, after = _cu(amt, "amount"), _cu(before_m, "balance_before"), _cu(after_m, "balance_after")
            credit = t_type == "RECHARGE"
            if before != position or after != (before + amount if credit else before - amount):
                raise RuntimeError(f"P1 migration refused: wallet {wallet_id} history is not a continuous chain")
            seq += 1
            entry_id = str(uuid.uuid4())
            bind.execute(sa.text(
                "INSERT INTO ledger_entries (id, institution_id, campus_user_id, customer_sequence, event_type, direction,"
                " amount_cu, position_before_cu, position_after_cu, origin, reference_type, reference_id, reason, created_at)"
                " VALUES (:id,:inst,:user,:seq,:et,:dir,:amt,:bef,:aft,:origin,:rt,:rid,:reason,:created)"),
                {"id": entry_id, "inst": inst_id, "user": user_id, "seq": seq,
                 "et": "RECHARGE" if credit else "PURCHASE", "dir": "CREDIT" if credit else "DEBIT", "amt": amount,
                 "bef": before, "aft": after, "origin": "DEMO" if credit else "STANDARD",
                 "rt": "DEMO_FUNDING" if credit else "PAYMENT",
                 "rid": f"LEGACY:{t_id}" if credit or not payment_id else payment_id,
                 "reason": "migrated from MVP wallet_transactions (MVP recharge was demo behaviour)", "created": created})
            bind.execute(sa.text("UPDATE wallet_transactions SET ledger_entry_id=:e, amount_cu=:a, balance_before_cu=:b,"
                                 " balance_after_cu=:c WHERE id=:id"),
                         {"e": entry_id, "a": amount, "b": before, "c": after, "id": t_id})
            position = after
        if position != _cu(balance_minor, "wallet balance"):
            raise RuntimeError(f"P1 migration refused: wallet {wallet_id} balance disagrees with its transaction history")
        bind.execute(sa.text("UPDATE wallets SET available_cu=:p WHERE id=:id"), {"p": position, "id": wallet_id})

    fk_name = "wallet_transactions_payment_id_fkey" if pg else "fk_wallet_transactions_payment_id_payments"
    wconv = {} if pg else {"naming_convention": {"fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"}}
    with op.batch_alter_table("wallet_transactions", **wconv) as b:
        b.drop_constraint(fk_name, type_="foreignkey")  # Wallet must not reference Payments (dependency direction)
        for col in ("amount_minor", "balance_before_minor", "balance_after_minor"):
            b.drop_column(col)
        for col in ("ledger_entry_id", "amount_cu", "balance_before_cu", "balance_after_cu"):
            b.alter_column(col, existing_type=sa.String() if col == "ledger_entry_id" else _BIG, nullable=False)
        b.create_foreign_key("fk_wallet_transactions_ledger_entry", "ledger_entries", ["ledger_entry_id"], ["id"])
        b.create_unique_constraint("uq_wallet_transactions_ledger_entry", ["ledger_entry_id"])
    op.create_index("ix_wallet_transactions_institution_id", "wallet_transactions", ["institution_id"])
    op.create_index("ix_wallet_transactions_wallet_id", "wallet_transactions", ["wallet_id"])

    with op.batch_alter_table("wallets") as b:
        b.drop_column("balance_minor")
        b.alter_column("available_cu", existing_type=_BIG, nullable=False)
        b.create_check_constraint("ck_wallets_available_non_negative", "available_cu >= 0")
    op.create_index("ix_wallets_institution_id", "wallets", ["institution_id"])

    # 6. payments ---------------------------------------------------------------------------------------------------------------
    for col, typ in (("order_id", sa.String()), ("device_id", sa.String()), ("kind", sa.String(16)),
                     ("amount_cu", _BIG), ("completed_at", sa.DateTime())):
        op.add_column("payments", sa.Column(col, typ, nullable=True))
    sole = bind.execute(sa.text("SELECT id FROM institutions")).fetchall()
    if bind.execute(sa.text("SELECT COUNT(*) FROM payments WHERE institution_id IS NULL")).scalar():
        if len(sole) != 1:
            raise RuntimeError("P1 migration refused: legacy payments without an institution and more than one institution")
        bind.execute(sa.text("UPDATE payments SET institution_id=:i WHERE institution_id IS NULL"), {"i": sole[0][0]})
    for pid, amount_minor in bind.execute(sa.text("SELECT id, amount_minor FROM payments")).fetchall():
        bind.execute(sa.text("UPDATE payments SET amount_cu=:a, kind='LEGACY_MANUAL' WHERE id=:id"),
                     {"a": _cu(amount_minor, "payment amount"), "id": pid})
    bind.execute(sa.text("UPDATE payments SET completed_at=created_at WHERE status='COMPLETED'"))

    pq_name = "payments_reference_key" if pg else "uq_payments_reference"
    pconv = {} if pg else {"naming_convention": {"uq": "uq_%(table_name)s_%(column_0_name)s"}}
    with op.batch_alter_table("payments", **pconv) as b:
        b.drop_constraint(pq_name, type_="unique")  # reference was GLOBALLY unique: a cross-tenant replay leak
        b.drop_column("amount_minor")
        b.alter_column("institution_id", existing_type=sa.String(), nullable=False)
        b.alter_column("kind", existing_type=sa.String(16), nullable=False)
        b.alter_column("amount_cu", existing_type=_BIG, nullable=False)
        b.create_foreign_key("fk_payments_order", "orders", ["order_id"], ["id"])
        b.create_unique_constraint("uq_payments_inst_reference", ["institution_id", "reference"])
        b.create_check_constraint("ck_payments_amount_positive", "amount_cu > 0")
    op.create_index("ix_payments_institution_id", "payments", ["institution_id"])
    op.create_index("uq_payments_order_completed", "payments", ["order_id"], unique=True,
                    postgresql_where=sa.text("status = 'COMPLETED'"), sqlite_where=sa.text("status = 'COMPLETED'"))

    op.create_table("receipts",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("institution_id", sa.String(), sa.ForeignKey("institutions.id"), nullable=False),
        sa.Column("payment_id", sa.String(), sa.ForeignKey("payments.id"), nullable=False, unique=True),
        sa.Column("order_id", sa.String(), nullable=True), sa.Column("receipt_number", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False), sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("issued_at", sa.DateTime()),
        sa.UniqueConstraint("institution_id", "receipt_number", name="uq_receipts_inst_number"))
    op.create_index("ix_receipts_institution_id", "receipts", ["institution_id"])
    op.create_index("ix_audit_logs_institution_id", "audit_logs", ["institution_id"])
    op.create_index("ix_merchants_institution_id", "merchants", ["institution_id"])

    _install_financial_guards(pg)


def _install_financial_guards(pg: bool) -> None:
    """Database-level enforcement of the ledger invariants (defence in depth beyond the ORM guards)."""
    if pg:
        op.execute("""CREATE FUNCTION campuspay_reject_mutation() RETURNS trigger AS $$
            BEGIN RAISE EXCEPTION '% is append-only: historical records are never rewritten or deleted', TG_TABLE_NAME; END;
            $$ LANGUAGE plpgsql""")
        for t in ("ledger_entries", "audit_logs"):
            op.execute(f"CREATE TRIGGER trg_{t}_immutable BEFORE UPDATE OR DELETE ON {t} "
                       f"FOR EACH ROW EXECUTE FUNCTION campuspay_reject_mutation()")
        op.execute("""CREATE FUNCTION campuspay_wallet_matches_ledger() RETURNS trigger AS $$
            DECLARE pos BIGINT;
            BEGIN
              SELECT position_after_cu INTO pos FROM ledger_entries
               WHERE institution_id = NEW.institution_id AND campus_user_id = NEW.campus_user_id
               ORDER BY customer_sequence DESC LIMIT 1;
              IF NEW.available_cu <> COALESCE(pos, 0) THEN
                RAISE EXCEPTION 'wallet available value must equal the Institution Ledger position';
              END IF;
              RETURN NEW;
            END; $$ LANGUAGE plpgsql""")
        op.execute("CREATE TRIGGER trg_wallet_matches_ledger BEFORE INSERT OR UPDATE OF available_cu ON wallets "
                   "FOR EACH ROW EXECUTE FUNCTION campuspay_wallet_matches_ledger()")
        return
    for t in ("ledger_entries", "audit_logs"):
        for action in ("UPDATE", "DELETE"):
            op.execute(f"CREATE TRIGGER trg_{t}_no_{action.lower()} BEFORE {action} ON {t} BEGIN "
                       f"SELECT RAISE(ABORT, '{t} is append-only: historical records are never rewritten or deleted'); END")
    cond = ("NEW.available_cu <> COALESCE((SELECT position_after_cu FROM ledger_entries WHERE institution_id = NEW.institution_id "
            "AND campus_user_id = NEW.campus_user_id ORDER BY customer_sequence DESC LIMIT 1), 0)")
    op.execute(f"CREATE TRIGGER trg_wallet_matches_ledger_upd BEFORE UPDATE OF available_cu ON wallets WHEN {cond} BEGIN "
               "SELECT RAISE(ABORT, 'wallet available value must equal the Institution Ledger position'); END")
    op.execute(f"CREATE TRIGGER trg_wallet_matches_ledger_ins BEFORE INSERT ON wallets WHEN {cond} BEGIN "
               "SELECT RAISE(ABORT, 'wallet available value must equal the Institution Ledger position'); END")


def downgrade() -> None:
    raise RuntimeError("0002_p1_campus_commerce is forward-only (financial data was converted to Campus Units); "
                       "restore from a backup taken before the upgrade.")
