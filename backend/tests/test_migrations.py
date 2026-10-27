"""Migrations are the only way the schema is created; the MVP upgrade path preserves data exactly or refuses."""
import sqlite3

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import DBAPIError

from tests.conftest import alembic_upgrade


def _fresh(tmp_path, revision="head"):
    path = tmp_path / "m.db"
    alembic_upgrade(f"sqlite:///{path}", revision)
    return path


def test_fresh_database_gets_the_full_p1_schema_and_guards(tmp_path):
    path = _fresh(tmp_path)
    c = sqlite3.connect(path)
    tables = {r[0] for r in c.execute("select name from sqlite_master where type='table'")}
    assert {"institutions", "campus_users", "wallets", "wallet_transactions", "ledger_entries", "credentials",
            "payment_pin_credentials", "merchants", "merchant_staff", "product_categories", "products", "orders",
            "order_items", "fulfillments", "payments", "receipts", "devices", "audit_logs"} <= tables
    triggers = {r[0] for r in c.execute("select name from sqlite_master where type='trigger'")}
    assert {"trg_ledger_entries_no_update", "trg_ledger_entries_no_delete", "trg_audit_logs_no_update",
            "trg_wallet_matches_ledger_upd", "trg_wallet_matches_ledger_ins"} <= triggers
    assert c.execute("select version_num from alembic_version").fetchone()[0] == "0007_android_printing"
    assert {"kiosk_sessions", "scanner_agents", "fingerprint_enrollments", "fingerprint_challenges", "scanner_captures"} <= tables


def test_orm_models_and_migrated_schema_do_not_drift(tmp_path):
    import app.models_registry  # noqa: F401
    from core.database import Base
    path = _fresh(tmp_path)
    insp = inspect(create_engine(f"sqlite:///{path}"))
    for table in Base.metadata.sorted_tables:
        assert insp.has_table(table.name), f"model table {table.name} missing from migrations"
        db_cols = {c["name"] for c in insp.get_columns(table.name)}
        assert {c.name for c in table.columns} == db_cols, f"column drift in {table.name}"


def test_downgrade_is_refused_for_the_financial_migration(tmp_path):
    from alembic import command
    from alembic.config import Config
    from tests.conftest import BACKEND
    _fresh(tmp_path)
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    cfg.attributes["url"] = f"sqlite:///{tmp_path / 'm.db'}"
    with pytest.raises(RuntimeError, match="forward-only"):
        command.downgrade(cfg, "0001_mvp_baseline")


def _mvp_db(tmp_path, *, txn_amount=5000, balance=45000):
    """A database exactly as the MVP left it (schema at revision 0001) with representative data (paise)."""
    path = _fresh(tmp_path, "0001_mvp_baseline")
    c = sqlite3.connect(path)
    c.executescript(f"""
    INSERT INTO institutions VALUES ('inst-1','E.G.S. Pillay Engineering College','ACTIVE','2026-09-01 10:00:00');
    INSERT INTO campus_users VALUES ('u-a','inst-1','Arun Kumar','STUDENT','EGS-STD-0001','ACTIVE','2026-09-01');
    INSERT INTO campus_users VALUES ('u-b','inst-1','Divya Shree','STUDENT','EGS-STD-0002','ACTIVE','2026-09-01');
    INSERT INTO wallets VALUES ('w-a','inst-1','u-a',{balance},'ACTIVE','2026-09-01','2026-09-01');
    INSERT INTO wallets VALUES ('w-b','inst-1','u-b',0,'ACTIVE','2026-09-01','2026-09-01');
    INSERT INTO merchants VALUES ('m-1','inst-1','Main Canteen','Canteen','ACTIVE','2026-09-01');
    INSERT INTO payments VALUES ('p-1','inst-1','u-a','m-1','w-a',{txn_amount},'COMPLETED',NULL,'ref-1','Lunch','2026-09-02 12:00:00');
    INSERT INTO payments VALUES ('p-2',NULL,NULL,NULL,NULL,100,'FAILED','STUDENT_NOT_FOUND','ref-2',NULL,'2026-09-02 12:05:00');
    INSERT INTO wallet_transactions VALUES ('t-1','inst-1','w-a',NULL,'RECHARGE',50000,0,50000,'COMPLETED','2026-09-01 11:00:00');
    INSERT INTO wallet_transactions VALUES ('t-2','inst-1','w-a','p-1','DEBIT',{txn_amount},50000,{50000 - txn_amount},'COMPLETED','2026-09-02 12:00:00');
    INSERT INTO audit_logs VALUES ('a-1','inst-1','system','PAYMENT_COMPLETED','Payment','p-1',NULL,'2026-09-02 12:00:00');
    """)
    c.commit()
    c.close()
    return path


def test_mvp_database_upgrade_converts_paise_to_campus_units_and_builds_the_ledger(tmp_path):
    path = _mvp_db(tmp_path)
    alembic_upgrade(f"sqlite:///{path}")
    c = sqlite3.connect(path)
    assert c.execute("select available_cu from wallets where id='w-a'").fetchone()[0] == 450
    assert c.execute("select available_cu from wallets where id='w-b'").fetchone()[0] == 0
    rows = c.execute("select customer_sequence,event_type,direction,amount_cu,position_before_cu,position_after_cu,origin,"
                     "reference_type,reference_id from ledger_entries order by customer_sequence").fetchall()
    assert rows == [(1, "RECHARGE", "CREDIT", 500, 0, 500, "DEMO", "DEMO_FUNDING", "LEGACY:t-1"),
                    (2, "PURCHASE", "DEBIT", 50, 500, 450, "STANDARD", "PAYMENT", "p-1")]
    wt = c.execute("select amount_cu,balance_before_cu,balance_after_cu,ledger_entry_id is not null from wallet_transactions order by created_at").fetchall()
    assert wt == [(500, 0, 500, 1), (50, 500, 450, 1)]
    pay = c.execute("select amount_cu,kind,institution_id,completed_at is not null from payments order by id").fetchall()
    assert pay[0] == (50, "LEGACY_MANUAL", "inst-1", 1) and pay[1][2] == "inst-1"
    assert c.execute("select code from institutions").fetchone()[0] == "E-G-S-PILLAY-ENGINEERING-COLLEGE"
    assert c.execute("select count(*) from audit_logs").fetchone()[0] == 1  # history preserved
    cols = {r[1] for r in c.execute("pragma table_info(wallets)")}
    assert "balance_minor" not in cols and "available_cu" in cols
    # identifier is now unique per institution, not globally
    c.execute("INSERT INTO institutions (id,name,status,created_at,code) VALUES ('inst-2','Other','ACTIVE','2026-09-03','OTHER')")
    c.execute("INSERT INTO campus_users VALUES ('u-x','inst-2','Same ID other tenant','STUDENT','EGS-STD-0001','ACTIVE','2026-09-03')")
    with pytest.raises(sqlite3.IntegrityError):
        c.execute("INSERT INTO campus_users VALUES ('u-y','inst-1','Dup','STUDENT','EGS-STD-0001','ACTIVE','2026-09-03')")
    # guards installed on the migrated data too
    with pytest.raises(sqlite3.IntegrityError):
        c.execute("UPDATE wallets SET available_cu = 99999 WHERE id='w-a'")
    with pytest.raises(sqlite3.IntegrityError):
        c.execute("DELETE FROM ledger_entries")
    c.close()


def test_upgrade_refuses_money_that_is_not_a_whole_number_of_campus_units(tmp_path):
    path = _mvp_db(tmp_path, txn_amount=5050, balance=44950)
    with pytest.raises(RuntimeError, match="not a whole number of Campus Units"):
        alembic_upgrade(f"sqlite:///{path}")


def test_upgrade_refuses_a_wallet_that_disagrees_with_its_history(tmp_path):
    path = _mvp_db(tmp_path, balance=99900)
    with pytest.raises(RuntimeError, match="disagrees with its transaction history"):
        alembic_upgrade(f"sqlite:///{path}")


def test_seed_creates_the_demo_world_and_is_rerunnable(tmp_path):
    from app.seed import seed
    url = f"sqlite:///{tmp_path / 'seed.db'}"
    lines = []
    result = seed(url, out=lines.append)
    assert result and set(result["pins"]) == {f"EGS-STD-000{i}" for i in range(1, 6)}
    assert seed(url, out=lines.append) is None  # second run: nothing to do
    c = sqlite3.connect(tmp_path / "seed.db")
    assert c.execute("select count(*) from devices").fetchone()[0] == 4
    assert c.execute("select count(*) from merchants").fetchone()[0] == 4
    assert c.execute("select count(*) from ledger_entries where origin='DEMO'").fetchone()[0] == 5
    assert "password" not in " ".join(r[0] for r in c.execute("select password_hash from credentials")).lower()
