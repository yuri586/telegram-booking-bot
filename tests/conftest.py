# ruff: noqa: E402, I001
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import os

os.environ.setdefault("TOKEN", "123456:TEST")
os.environ.setdefault("ADMIN_IDS", "1")
os.environ.setdefault("DEMO_PROFILE", "photographer")
os.environ.setdefault("ENV", "dev")
os.environ.setdefault("LOG_LEVEL", "INFO")
os.environ.setdefault("BOOKING_TIMEZONE", "UTC")

os.environ.setdefault("ENABLE_BOOKING", "0")
os.environ.setdefault("ENABLE_SHOP", "0")
os.environ.setdefault("ENABLE_GROUPS", "0")
os.environ.setdefault("DEBUG", "0")
os.environ.setdefault("DEBUG_SQL", "0")
os.environ.setdefault("SEED_DEMO", "0")

from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from database.models import Base

@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as session:
        yield session

    await engine.dispose()
