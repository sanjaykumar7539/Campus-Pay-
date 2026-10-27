"""PostgreSQL-only checks: native-enum -> VARCHAR migration, MVP data upgrade, and database-level financial guards."""
import os
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from tests.conftest import alembic_upgrade

PG_ADMIN_URL = os.getenv("CAMPUSPAY_TEST_POSTGRES_URL")
pytestmark = [pytest.mark.postgres, pytest.mark.skipif(not PG_ADMIN_URL, reason="CAMPUSPAY_TEST_POSTGRES_URL not set")]


@pytest.fixture()
def pg_url():
    name = f"cp_mig_{uuid.uuid4().hex[:10]}"
    admin = create_engine(PG_ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f"CREATE DATABASE {name}"))
    yield PG_ADMIN_URL.rsplit("/", 1)[0] + "/" + name
    with admin.connect() as c:
        c.execute(text(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)"))


MVP_DATA = """
INSERT INTO institutions VALUES ('inst-1','E.G.S. Pillay Engineering College','ACTIVE','2026-09-01 10:00:00');
INSERT INTO campus_users VALUES ('u-a','inst-1','Arun Kumar','STUDENT','EGS-STD-0001','ACTIVE','2026-09-01');
INSERT INTO wallets VALUES ('w-a','inst-1','u-a',45000,'ACTIVE','2026-09-01','2026-09-01');
INSERT INTO merchants VALUES ('m-1','inst-1','Main Canteen','Canteen','ACTIVE','2026-09-01');
INSERT INTO payments VALUES ('p-1','inst-1','u-a','m-1','w-a',5000,'COMPLETED',NULL,'ref-1','Lunch','2026-09-02 12:00:00');
INSERT INTO payments VALUES ('p-2',NULL,NULL,NULL,NULL,100,'FAILED','STUDENT_NOT_FOUND','ref-2',NULL,'2026-09-02 12:05:00');
INSERT INTO wallet_transactions VALUES ('t-1','inst-1','w-a',NULL,'RECHARGE',50000,0,50000,'COMPLETED','2026-09-01 11:00:00');
INSERT INTO wallet_transactions VALUES ('t-2','inst-1','w-a','p-1','DEBIT',5000,50000,45000,'COMPLETED','2026-09-02 12:00:00');
"""


def test_mvp_postgres_database_upgrades_preserving_data(pg_url):
    alembic_upgrade(pg_url, "0001_mvp_baseline")
    eng = create_engine(pg_url)
    with eng.begin() as c:
        for stmt in [s for s in MVP_DATA.strip().split(";\n") if s.strip()]:
            c.execute(text(stmt))
    alembic_upgrade(pg_url)
    with eng.connect() as c:
        assert c.execute(text("SELECT available_cu FROM wallets WHERE id='w-a'")).scalar() == 450
        rows = c.execute(text("SELECT event_type, direction, amount_cu, position_after_cu, origin FROM ledger_entries ORDER BY customer_sequence")).fetchall()
        assert [tuple(r) for r in rows] == [("RECHARGE", "CREDIT", 500, 500, "DEMO"), ("PURCHASE", "DEBIT", 50, 450, "STANDARD")]
        assert c.execute(text("SELECT amount_cu, kind FROM payments WHERE id='p-1'")).fetchone() == (50, "LEGACY_MANUAL")
        assert c.execute(text("SELECT COUNT(*) FROM pg_type WHERE typname IN ('entitystatus','userrole','paymentstatus','wallettxntype')")).scalar() == 0
        # global uniqueness is gone: same campus identifier is legal in another institution
        c.execute(text("INSERT INTO institutions (id,name,status,created_at,code) VALUES ('inst-2','Other','ACTIVE','2026-09-03','OTHER')"))
        c.execute(text("INSERT INTO campus_users VALUES ('u-x','inst-2','Other','STUDENT','EGS-STD-0001','ACTIVE','2026-09-03')"))
        c.commit()
    eng.dispose()


def test_database_triggers_guard_wallet_ledger_and_audit(pg_url):
    alembic_upgrade(pg_url)
    eng = create_engine(pg_url)
    with eng.begin() as c:
        c.execute(text("INSERT INTO institutions (id,name,status,created_at,code) VALUES ('i','I','ACTIVE',now(),'I')"))
        c.execute(text("INSERT INTO campus_users VALUES ('u','i','U','STUDENT','X1','ACTIVE',now())"))
        c.execute(text("INSERT INTO wallets (id,institution_id,campus_user_id,available_cu,status,created_at,updated_at) VALUES ('w','i','u',0,'ACTIVE',now(),now())"))
        c.execute(text("INSERT INTO ledger_entries (id,institution_id,campus_user_id,customer_sequence,event_type,direction,amount_cu,position_before_cu,"
                       "position_after_cu,origin,reference_type,reference_id,created_at) VALUES ('l','i','u',1,'RECHARGE','CREDIT',100,0,100,'DEMO','DEMO_FUNDING','r',now())"))
        c.execute(text("UPDATE wallets SET available_cu = 100 WHERE id='w'"))  # equals ledger position: allowed
        c.execute(text("INSERT INTO audit_logs (id,institution_id,event_type,entity_type,entity_id,created_at) VALUES ('a','i','E','T','1',now())"))
    for stmt in ("UPDATE wallets SET available_cu = 5000 WHERE id='w'", "UPDATE ledger_entries SET amount_cu = 1", "DELETE FROM ledger_entries",
                 "UPDATE audit_logs SET event_type='X'", "DELETE FROM audit_logs", "INSERT INTO wallets (id,institution_id,campus_user_id,available_cu,status,created_at,updated_at) VALUES ('w2','i','u',7,'ACTIVE',now(),now())"):
        with pytest.raises(DBAPIError):
            with eng.begin() as c:
                c.execute(text(stmt))
    eng.dispose()
