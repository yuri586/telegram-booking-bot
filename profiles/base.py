# profiles/base.py
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from profiles.ui_contract import ProfileUI

SeedFn = Callable[[AsyncSession], Awaitable[None]]


@dataclass(frozen=True)
class DemoProfile:
    slug: str
    seed: SeedFn
    ui: ProfileUI