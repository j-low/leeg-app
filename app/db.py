# SQLAlchemy async engine, session factory, and FastAPI dependency
# All pipeline tool calls and route handlers use get_db() for DB access.

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

# Pool tuning: modest defaults suitable for a single-server t3.medium deployment.
# Increase pool_size/max_overflow if load tests (Phase 11) show contention.
engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,  # Discard stale connections before use
)

async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,  # Keep ORM objects usable after commit without re-query
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yields a scoped async DB session per request.

    Usage in route:
        async def my_route(db: AsyncSession = Depends(get_db)): ...
    """
    async with async_session() as session:
        yield session


async def init_db() -> None:
    """Create all tables if they don't exist.

    Used in tests and local dev. In production, Alembic migrations are
    the source of truth -- do not call this in the production app startup.
    """
    # Import here to ensure all models are registered on Base.metadata
    import app.models  # noqa: F401

    from app.models.base import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
