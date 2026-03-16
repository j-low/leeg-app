"""
Shared pytest fixtures for Phase 11 testing.

Key design decisions:
- Each test gets a fresh in-memory SQLite DB (via aiosqlite) to ensure isolation.
- Minimal FastAPI apps are constructed per test class (no SlowAPI middleware) to
  avoid rate-limit counters accumulating across test runs.
- External services (Redis, Anthropic, Twilio, Celery) are always mocked.
"""
from collections.abc import AsyncGenerator

import pytest_asyncio
import app.models  # noqa: F401 — registers all ORM models on Base.metadata
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


# ── Engine / session helpers ──────────────────────────────────────────────────

async def build_engine():
    """Create an in-memory SQLite engine with all tables."""
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine


def make_session_override(engine):
    """Return a FastAPI-compatible async generator dependency that yields sessions."""
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def get_test_db() -> AsyncGenerator[AsyncSession, None]:
        async with factory() as session:
            yield session

    return get_test_db


# ── Per-test app builder ──────────────────────────────────────────────────────

def make_app(*routers, db_override=None):
    """
    Build a minimal FastAPI app containing only the given routers.

    Intentionally does NOT include SlowAPI middleware, so rate-limit decorators
    on individual routes become no-ops (no app.state.limiter configured).

    Args:
        *routers: FastAPI APIRouter instances to include.
        db_override: async generator dependency to replace ``get_db``.
    """
    from fastapi import FastAPI
    from app.db import get_db

    application = FastAPI()
    for router in routers:
        application.include_router(router)

    if db_override is not None:
        application.dependency_overrides[get_db] = db_override

    return application


# ── Shared fixtures ───────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def engine():
    """Per-test SQLite engine, all tables created, disposed after test."""
    eng = await build_engine()
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def db_session(engine) -> AsyncGenerator[AsyncSession, None]:
    """Direct AsyncSession for asserting DB state in tests."""
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
