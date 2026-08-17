"""Async DB engine + FastAPI dependency."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TypeAlias

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.common.logging import get_logger
from src.storage.models import Base

log = get_logger(__name__)

DBSession: TypeAlias = AsyncSession

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def _make_engine(db_url: str) -> AsyncEngine:
    connect_args: dict = {}
    if db_url.startswith("sqlite"):
        connect_args["timeout"] = 30
    return create_async_engine(db_url, future=True, connect_args=connect_args)


async def init_db(db_url: str) -> None:
    global _engine, _sessionmaker
    _engine = _make_engine(db_url)
    _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)

    async with _engine.begin() as conn:
        if db_url.startswith("sqlite"):
            await conn.exec_driver_sql("PRAGMA journal_mode=WAL")
            await conn.exec_driver_sql("PRAGMA foreign_keys=ON")
        await conn.run_sync(Base.metadata.create_all)

    log.info("db_ready", extra={"context": {"url": _sanitize(db_url)}})


def _sanitize(url: str) -> str:
    if "@" in url:
        head, tail = url.split("@", 1)
        prefix = head.rsplit("//", 1)[0] + "//"
        return prefix + "***@" + tail
    return url


async def get_session() -> AsyncIterator[AsyncSession]:
    if _sessionmaker is None:
        await init_db("sqlite+aiosqlite:///./data/pso.db")
    assert _sessionmaker is not None
    async with _sessionmaker() as session:
        yield session


async def dispose() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None
