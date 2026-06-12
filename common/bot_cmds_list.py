from __future__ import annotations

from aiogram.types import BotCommand

from common.capabilities import Caps, caps
from plugins.registry import (
    load_enabled_plugin_admin_commands,
    load_enabled_plugin_commands,
    load_enabled_plugin_user_commands,
)

CORE_USER_PRIVATE_COMMANDS: list[BotCommand] = [
    BotCommand(command="start", description="Старт"),
    BotCommand(command="help", description="Помощь"),
]

CORE_ADMIN_PRIVATE_COMMANDS: list[BotCommand] = [
    BotCommand(command="admin", description="Админ-панель"),
]


def _dedupe_commands(commands: list[BotCommand]) -> list[BotCommand]:
    seen: set[str] = set()
    result: list[BotCommand] = []

    for cmd in commands:
        if cmd.command in seen:
            continue
        seen.add(cmd.command)
        result.append(cmd)

    return result


def user_private_commands(c: Caps | None = None) -> list[BotCommand]:
    c = c or caps()

    cmds = list(CORE_USER_PRIVATE_COMMANDS)
    cmds.extend(load_enabled_plugin_user_commands(c))
    return _dedupe_commands(cmds)


def admin_private_commands(c: Caps | None = None) -> list[BotCommand]:
    c = c or caps()

    cmds = list(user_private_commands(c))
    cmds.extend(CORE_ADMIN_PRIVATE_COMMANDS)
    cmds.extend(load_enabled_plugin_admin_commands(c))
    return _dedupe_commands(cmds)


# backward-compatible alias:
# исторически private_commands() возвращал "полный" набор команд
def private_commands(c: Caps | None = None) -> list[BotCommand]:
    c = c or caps()

    cmds = list(CORE_USER_PRIVATE_COMMANDS)
    cmds.extend(CORE_ADMIN_PRIVATE_COMMANDS)
    cmds.extend(load_enabled_plugin_commands(c))
    return _dedupe_commands(cmds)