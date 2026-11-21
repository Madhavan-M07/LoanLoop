"""Alembic environment (async, asyncpg).

Database URL, in order: `config.attributes["database_url"]` (set by tests), else
LOANLOOP_DATABASE_URL (env var or backend/.env). The URL is never logged.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import DatabaseSettings, load_env_file
from app.data.tables import metadata

config = context.config
if config.config_file_name is not None and config.attributes.get("configure_logging", True):
    fileConfig(config.config_file_name)

target_metadata = metadata


def _database_url() -> str:
    url = config.attributes.get("database_url")
    if url:
        return str(url)
    load_env_file()
    secret = DatabaseSettings().database_url
    if secret is None:
        raise SystemExit("LOANLOOP_DATABASE_URL is not set; nothing to migrate.")
    return secret.get_secret_value()


def _run(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        transaction_per_migration=True,  # a failed migration rolls back cleanly
    )
    with context.begin_transaction():
        context.run_migrations()


async def _run_async() -> None:
    engine = create_async_engine(_database_url())
    try:
        async with engine.connect() as conn:
            await conn.run_sync(_run)
            await conn.commit()
    finally:
        await engine.dispose()


if context.is_offline_mode():
    raise SystemExit("Offline (--sql) mode is not supported; run against a database.")
asyncio.run(_run_async())
