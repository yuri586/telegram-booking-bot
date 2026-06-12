from __future__ import annotations

from aiogram import Router

from common.capabilities import Caps
from keyboards.callbacks import LeadCB
from plugins.contracts import PluginCapabilities


def _enabled(caps: Caps) -> bool:
    return caps.leads


def _routers() -> list[Router]:
    from plugins.leads.handlers_user_leads import lead_user_router

    return [lead_user_router]


def _menu_buttons() -> list[tuple[str, str]]:
    return [
        ("📝 Оставить заявку", LeadCB(action="start").pack()),
    ]


plugin = PluginCapabilities(
    name="leads",
    is_enabled=_enabled,
    get_routers=_routers,
    get_menu_buttons=_menu_buttons,
)