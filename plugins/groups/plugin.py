from __future__ import annotations

from aiogram import Router

from common.capabilities import Caps
from plugins.contracts import PluginCapabilities


def _enabled(caps: Caps) -> bool:
    return caps.groups


def _routers() -> list[Router]:
    from plugins.groups.handlers_user_group import user_group_router

    return [user_group_router]


plugin = PluginCapabilities(
    name="groups",
    is_enabled=_enabled,
    get_routers=_routers,
)