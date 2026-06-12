from __future__ import annotations

from aiogram import Router
from aiogram.types import BotCommand

from common.capabilities import Caps
from plugins.booking.plugin import plugin as booking_plugin
from plugins.contracts import PluginCapabilities
from plugins.groups.plugin import plugin as groups_plugin
from plugins.leads.plugin import plugin as leads_plugin
from plugins.shop.plugin import plugin as shop_plugin

PLUGINS: list[PluginCapabilities] = [
    booking_plugin,
    leads_plugin,
    groups_plugin,
    shop_plugin,
]

def _plugin_user_commands(plugin: PluginCapabilities) -> list[BotCommand]:
    return [*plugin.get_commands(), *plugin.get_user_commands()]


def _plugin_admin_commands(plugin: PluginCapabilities) -> list[BotCommand]:
    return list(plugin.get_admin_commands())


def _plugin_all_commands(plugin: PluginCapabilities) -> list[BotCommand]:
    return [*_plugin_user_commands(plugin), *_plugin_admin_commands(plugin)]

def _raise_duplicate(kind: str, value: str, plugin_name: str) -> None:
    raise RuntimeError(
        f"Plugin registry conflict: duplicate {kind} '{value}' from plugin '{plugin_name}'"
    )


def _validate_unique_commands(plugins: list[PluginCapabilities]) -> None:
    seen: dict[str, str] = {}

    for plugin in plugins:
        for command in _plugin_all_commands(plugin):
            if command.command in seen:
                _raise_duplicate("command", command.command, plugin.name)
            seen[command.command] = plugin.name


def _validate_unique_admin_buttons(plugins: list[PluginCapabilities]) -> None:
    seen: dict[str, str] = {}

    for plugin in plugins:
        for button in plugin.get_admin_buttons():
            if button in seen:
                _raise_duplicate("admin button", button, plugin.name)
            seen[button] = plugin.name


def _validate_unique_menu_buttons(plugins: list[PluginCapabilities]) -> None:
    seen: dict[str, str] = {}

    for plugin in plugins:
        for text, _callback in plugin.get_menu_buttons():
            if text in seen:
                _raise_duplicate("menu button", text, plugin.name)
            seen[text] = plugin.name

def load_enabled_plugins(caps: Caps) -> list[PluginCapabilities]:
    return [plugin for plugin in PLUGINS if plugin.is_enabled(caps)]


# Временная совместимость со старым именем.
def enabled_plugins(caps: Caps) -> list[PluginCapabilities]:
    return load_enabled_plugins(caps)


def load_enabled_plugin_routers(caps: Caps) -> list[Router]:
    routers: list[Router] = []
    for plugin in load_enabled_plugins(caps):
        routers.extend(plugin.get_routers())
    return routers


def load_enabled_plugin_commands(caps: Caps) -> list[BotCommand]:
    plugins = load_enabled_plugins(caps)
    _validate_unique_commands(plugins)

    commands: list[BotCommand] = []
    for plugin in plugins:
        commands.extend(_plugin_all_commands(plugin))
    return commands

def load_enabled_plugin_user_commands(caps: Caps) -> list[BotCommand]:
    plugins = load_enabled_plugins(caps)
    _validate_unique_commands(plugins)

    commands: list[BotCommand] = []
    for plugin in plugins:
        commands.extend(_plugin_user_commands(plugin))
    return commands


def load_enabled_plugin_admin_commands(caps: Caps) -> list[BotCommand]:
    plugins = load_enabled_plugins(caps)
    _validate_unique_commands(plugins)

    commands: list[BotCommand] = []
    for plugin in plugins:
        commands.extend(_plugin_admin_commands(plugin))
    return commands

def load_enabled_plugin_admin_buttons(caps: Caps) -> list[str]:
    plugins = load_enabled_plugins(caps)
    _validate_unique_admin_buttons(plugins)

    buttons: list[str] = []
    for plugin in plugins:
        buttons.extend(plugin.get_admin_buttons())
    return buttons


def load_enabled_plugin_menu_buttons(caps: Caps) -> list[tuple[str, str]]:
    plugins = load_enabled_plugins(caps)
    _validate_unique_menu_buttons(plugins)

    buttons: list[tuple[str, str]] = []
    for plugin in plugins:
        buttons.extend(plugin.get_menu_buttons())
    return buttons