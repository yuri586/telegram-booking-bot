from __future__ import annotations

from aiogram import Router

from common.capabilities import Caps
from plugins.contracts import PluginCapabilities


def _enabled(caps: Caps) -> bool:
    return caps.shop


def _routers() -> list[Router]:
    from plugins.shop.handlers_admin_private import admin_router as shop_admin_router

    return [shop_admin_router]


def _admin_buttons() -> list[str]:
    return ["Товары"]


plugin = PluginCapabilities(
    name="shop",
    is_enabled=_enabled,
    get_routers=_routers,
    get_admin_buttons=_admin_buttons,
)