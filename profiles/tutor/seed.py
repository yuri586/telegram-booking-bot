# profiles/tutor/seed.py
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from database.seed_core import seed_from_content
from profiles.tutor.content import (
    TUTOR_BANNERS,
    TUTOR_ITEMS,
    TUTOR_SECTIONS,
    TUTOR_SERVICES,
    TUTOR_SLOT_DAYS_AHEAD,
    TUTOR_SLOT_TIMES,
)


async def seed(session: AsyncSession) -> None:
    await seed_from_content(
        session,
        banners=TUTOR_BANNERS,
        sections=TUTOR_SECTIONS,
        items=TUTOR_ITEMS,
        services=TUTOR_SERVICES,
        slot_times=TUTOR_SLOT_TIMES,
        slot_days_ahead=TUTOR_SLOT_DAYS_AHEAD,
    )