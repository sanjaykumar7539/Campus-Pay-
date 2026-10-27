"""Database infrastructure: engine/session factory and ORM base.

Technical capability only (no business logic). PostgreSQL is the documented
target (docs/DATABASE.md §2); SQLite is a local/demo adapter.

SQLite note: SQLite has no row locks, so each transaction is opened with
``BEGIN IMMEDIATE`` which serialises writers. That makes local behaviour
deterministic but it is NOT evidence of production concurrency safety; the
PostgreSQL concurrency suite is the reference (see tests/test_concurrency_postgres.py).
"""
from __future__ import annotations

from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


def make_engine(url: str, *, foreign_keys: bool = True) -> Engine:
    if url.startswith("sqlite"):
        engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 30})

        @event.listens_for(engine, "connect")
        def _sqlite_connect(dbapi_connection, _record):  # pragma: no cover - trivial
            dbapi_connection.isolation_level = None  # we emit BEGIN ourselves
            cur = dbapi_connection.cursor()
            cur.execute("PRAGMA foreign_keys=ON" if foreign_keys else "PRAGMA foreign_keys=OFF")
            cur.execute("PRAGMA busy_timeout=30000")
            cur.close()

        @event.listens_for(engine, "begin")
        def _sqlite_begin(conn):  # pragma: no cover - trivial
            conn.exec_driver_sql("BEGIN IMMEDIATE")

        return engine
    return create_engine(url, pool_pre_ping=True)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:  # pragma: no cover - helper
    db = factory()
    try:
        yield db
    finally:
        db.close()
