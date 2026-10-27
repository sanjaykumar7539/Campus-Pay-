"""Alembic environment. Schema changes are made ONLY through migrations (never `create_all`)."""
import os

from alembic import context
from sqlalchemy import create_engine, pool

import app.models_registry  # noqa: F401
from core.database import Base

config = context.config
target_metadata = Base.metadata


def _url() -> str:
    return (config.attributes.get("url") or context.get_x_argument(as_dictionary=True).get("url")
            or os.getenv("DATABASE_URL") or config.get_main_option("sqlalchemy.url") or "sqlite:///./campuspay_demo.db")


def run_migrations_offline() -> None:
    context.configure(url=_url(), target_metadata=target_metadata, literal_binds=True, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    url = _url()
    engine = create_engine(url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata,
                          render_as_batch=url.startswith("sqlite"))
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
