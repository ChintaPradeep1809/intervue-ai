from __future__ import annotations

from alembic import context
from sqlalchemy import create_engine, pool

from app import models  # noqa: F401  (register tables)
from app.config import get_settings
from app.db import Base

config = context.config
target_metadata = Base.metadata


def sync_url() -> str:
    url = get_settings().database_url
    return (
        url.replace("sqlite+aiosqlite://", "sqlite://").replace("postgresql://", "postgresql+psycopg://", 1)
        if url.startswith("postgresql://")
        else url.replace("sqlite+aiosqlite://", "sqlite://")
    )


def run_offline() -> None:
    context.configure(url=sync_url(), target_metadata=target_metadata, literal_binds=True, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def run_online() -> None:
    engine = create_engine(sync_url(), poolclass=pool.NullPool)
    with engine.connect() as conn:
        context.configure(connection=conn, target_metadata=target_metadata, compare_type=True, render_as_batch=conn.dialect.name == "sqlite")
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_offline()
else:
    run_online()
