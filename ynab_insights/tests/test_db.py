"""Smoke tests for the async engine and session machinery."""

from sqlalchemy import text

from app.db import async_session_maker, engine


async def test_engine_executes_select() -> None:
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT 1"))
        assert result.scalar() == 1


async def test_session_maker_yields_session() -> None:
    async with async_session_maker() as session:
        result = await session.execute(text("SELECT 1"))
        assert result.scalar() == 1
