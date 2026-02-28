"""Alembic environment configuration.

Configured for async SQLAlchemy (asyncpg driver).
Database URL and metadata are pulled from the application's own
config and models so there is a single source of truth.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# -- App imports -------------------------------------------------------
# Importing settings gives us the DATABASE_URL from the environment.
from app.config import settings

# Importing app.models registers all ORM models on Base.metadata,
# which Alembic needs to generate accurate autogenerate diffs.
import app.models  # noqa: F401
from app.models.base import Base

# ----------------------------------------------------------------------

config = context.config

# Wire up Python logging from alembic.ini if present.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Swap asyncpg driver for psycopg2 so Alembic can run sync DDL.
# asyncpg URLs: postgresql+asyncpg://...
# Alembic needs a sync driver for DDL operations only.
_sync_url = settings.database_url.replace(
    "postgresql+asyncpg://", "postgresql+psycopg2://"
)

# Override the INI-file URL with the one from our settings.
config.set_main_option("sqlalchemy.url", _sync_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Emit SQL to stdout without connecting (for dry-run / CI diffs)."""
    context.configure(
        url=_sync_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations using an async engine (for online mode)."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
