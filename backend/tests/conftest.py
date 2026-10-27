"""Shared fixtures. The schema is created ONLY by Alembic migrations (never create_all)."""
import os
import shutil
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("CAMPUSPAY_PAYMENT_AUTH", "pin")  # legacy regression suite; kiosk tests select fingerprint mode
os.environ.setdefault("SECRET_KEY", "test-only-signing-key-not-a-real-secret")
os.environ.setdefault("CAMPUSPAY_BCRYPT_ROUNDS", "4")  # fast hashing in tests only
os.environ["CAMPUSPAY_DEMO_FUNDING"] = "true"
for _k in ("CAMPUSPAY_PIN_MAX_FAILED_ATTEMPTS", "CAMPUSPAY_PIN_LOCK_DURATION_SECONDS", "CAMPUSPAY_LEGACY_MANUAL_PAYMENT"):
    os.environ.pop(_k, None)

BACKEND = Path(__file__).resolve().parents[1]


def alembic_upgrade(url: str, revision: str = "head") -> None:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    cfg.attributes["url"] = url
    command.upgrade(cfg, revision)


@pytest.fixture(scope="session")
def template_db(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("tpl") / "template.db"
    alembic_upgrade(f"sqlite:///{path}")
    return path


@pytest.fixture()
def app(template_db, tmp_path):
    from app.main import create_app
    db_file = tmp_path / "test.db"
    shutil.copy(template_db, db_file)
    application = create_app(f"sqlite:///{db_file}")
    yield application
    application.state.engine.dispose()


@pytest.fixture()
def client(app):
    return TestClient(app)


@pytest.fixture()
def world(app):
    from tests.helpers import build_world
    return build_world(app)
