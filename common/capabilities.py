from __future__ import annotations

from dataclasses import dataclass

from config import settings


@dataclass(frozen=True)
class Caps:
    booking: bool
    leads: bool
    groups: bool
    shop: bool
    debug_mw: bool


def caps() -> Caps:
    return Caps(
        booking=settings.ENABLE_BOOKING,
        leads=settings.ENABLE_LEADS,
        groups=settings.ENABLE_GROUPS,
        shop=settings.ENABLE_SHOP,
        debug_mw=settings.ENABLE_DEBUG_MW,
    )