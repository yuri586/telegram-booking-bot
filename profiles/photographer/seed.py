# profiles/photographer/seed.py
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from database.seed_core import seed_from_content
from profiles.photographer.content import (
    PHOTOGRAPHER_BANNERS,
    PHOTOGRAPHER_ITEMS,
    PHOTOGRAPHER_SECTIONS,
    PHOTOGRAPHER_SERVICES,
    PHOTOGRAPHER_SLOT_DAYS_AHEAD,
    PHOTOGRAPHER_SLOT_TIMES,
)


async def seed(session: AsyncSession) -> None:
    await seed_from_content(
        session,
        banners=PHOTOGRAPHER_BANNERS,
        sections=PHOTOGRAPHER_SECTIONS,
        items=PHOTOGRAPHER_ITEMS,
        services=PHOTOGRAPHER_SERVICES,
        slot_times=PHOTOGRAPHER_SLOT_TIMES,
        slot_days_ahead=PHOTOGRAPHER_SLOT_DAYS_AHEAD,
    )