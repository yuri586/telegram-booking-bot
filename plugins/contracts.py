from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from aiogram import Router
from aiogram.types import BotCommand

from common.capabilities import Caps


@dataclass(frozen=True)
class PluginCapabilities:
    name: str
    is_enabled: Callable[[Caps], bool]
    get_routers: Callable[[], list[Router]]

    # legacy / backward-compatible
    get_commands: Callable[[], list[BotCommand]] = field(default=lambda: [])

    # explicit split
    get_user_commands: Callable[[], list[BotCommand]] = field(default=lambda: [])
    get_admin_commands: Callable[[], list[BotCommand]] = field(default=lambda: [])

    get_admin_buttons: Callable[[], list[str]] = field(default=lambda: [])
    get_menu_buttons: Callable[[], list[tuple[str, str]]] = field(default=lambda: [])


# Временный alias для безопасного перехода.
PluginSpec = PluginCapabilities