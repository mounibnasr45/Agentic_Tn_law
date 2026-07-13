"""Async engine and session factory.

Driver: psycopg3 (`postgresql+psycopg://`), not asyncpg. LangGraph's Postgres
checkpointer (P5) is built on psycopg3, and running two async drivers against one
database means two pools, two sets of connection semantics, and two things to tune.
asyncpg's throughput edge is irrelevant at this scale; one driver is the cleaner answer.
"""
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.database_url,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_pre_ping=True,  # a pooled connection killed by the server is recycled, not raised
            echo=settings.db_echo,
        )
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            get_engine(),
            # Without this, touching any attribute after commit triggers a lazy refresh,
            # which in async SQLAlchemy raises MissingGreenlet — the single most common
            # way an async SQLAlchemy app breaks in production.
            expire_on_commit=False,
        )
    return _sessionmaker


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency. Commits on success, rolls back on any exception."""
    async with get_sessionmaker()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None
