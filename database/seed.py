# database/seed.py
from __future__ import annotations

import asyncio

from config import settings
from database.engine import session_maker
from database.orm_query import orm_has_seeded_profile_data
from profiles.registry import get_profile


async def seed() -> None:
    profile = get_profile(settings.DEMO_PROFILE)

    async with session_maker() as session:
        has_existing_data = await orm_has_seeded_profile_data(session)
        if has_existing_data:
            raise RuntimeError(
                "Demo seed requires an empty DB. "
                "One profile = one DB. "
                "Use a fresh DB_URL for another profile."
            )

        await profile.seed(session)

    print(f"✔ Seeded demo profile: {profile.slug}")


if __name__ == "__main__":
    asyncio.run(seed())