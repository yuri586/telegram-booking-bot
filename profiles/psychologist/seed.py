# profiles/psychologist/seed.py
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from database.seed_core import seed_from_content
from profiles.psychologist.content import (
    PSYCHOLOGIST_BANNERS,
    PSYCHOLOGIST_ITEMS,
    PSYCHOLOGIST_SECTIONS,
    PSYCHOLOGIST_SERVICES,
    PSYCHOLOGIST_SLOT_DAYS_AHEAD,
    PSYCHOLOGIST_SLOT_TIMES,
)


async def seed(session: AsyncSession) -> None:
    await seed_from_content(
        session,
        banners=PSYCHOLOGIST_BANNERS,
        sections=PSYCHOLOGIST_SECTIONS,
        items=PSYCHOLOGIST_ITEMS,
        services=PSYCHOLOGIST_SERVICES,
        slot_times=PSYCHOLOGIST_SLOT_TIMES,
        slot_days_ahead=PSYCHOLOGIST_SLOT_DAYS_AHEAD,
    )