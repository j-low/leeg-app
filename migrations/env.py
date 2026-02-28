"""Alembic environment configuration.

Uses a synchronous psycopg2 connection for migrations (Alembic is a
CLI tool, not a hot path -- sync is appropriate and simpler here).
The app itself uses asyncpg at runtime via app/db.py.

Database URL and metadata come from the app's own config/models so
there is a single source of truth.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# -- App imports -------------------------------------------------------
from app.config import settings

# Importing app.models registers all ORM models on Base.metadata so
# Alembic autogenerate can detect additions, removals, and changes.
import app.models  # noqa: F401
from app.models.base import Base

# ----------------------------------------------------------------------

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Swap asyncpg → psycopg2 so Alembic can use a sync connection.
_sync_url = settings.database_url.replace(
    "postgresql+asyncpg://", "postgresql+psycopg2://"
)
config.set_main_option("sqlalchemy.url", _sync_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Emit SQL to stdout without connecting (dry-run / CI diff)."""
    context.configure(
        url=_sync_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Connect and run migrations against the live database."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
