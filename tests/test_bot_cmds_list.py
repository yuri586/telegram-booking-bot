from __future__ import annotations

from typing import cast

from aiogram.types import BotCommand

import common.bot_cmds_list as bot_cmds_list
from common.capabilities import Caps


def _names(commands: list[BotCommand]) -> list[str]:
    return [cmd.command for cmd in commands]


def test_user_private_commands_hide_admin_only(monkeypatch) -> None:
    monkeypatch.setattr(
        bot_cmds_list,
        "load_enabled_plugin_user_commands",
        lambda c: [
            BotCommand(command="booking", description="Записаться"),
            BotCommand(command="mybookings", description="Мои записи"),
        ],
    )
    monkeypatch.setattr(
        bot_cmds_list,
        "load_enabled_plugin_admin_commands",
        lambda c: [
            BotCommand(command="bookings", description="Записи (админ)"),
        ],
    )

    commands = bot_cmds_list.user_private_commands(cast(Caps, object()))

    assert _names(commands) == ["start", "help", "booking", "mybookings"]


def test_admin_private_commands_include_user_and_admin(monkeypatch) -> None:
    monkeypatch.setattr(
        bot_cmds_list,
        "load_enabled_plugin_user_commands",
        lambda c: [
            BotCommand(command="booking", description="Записаться"),
            BotCommand(command="mybookings", description="Мои записи"),
        ],
    )
    monkeypatch.setattr(
        bot_cmds_list,
        "load_enabled_plugin_admin_commands",
        lambda c: [
            BotCommand(command="bookings", description="Записи (админ)"),
        ],
    )

    commands = bot_cmds_list.admin_private_commands(cast(Caps, object()))

    assert _names(commands) == [
        "start",
        "help",
        "booking",
        "mybookings",
        "admin",
        "bookings",
    ]