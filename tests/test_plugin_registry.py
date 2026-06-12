# tests/test_plugin_registry.py
from __future__ import annotations

from aiogram import Router
from aiogram.types import BotCommand, KeyboardButton, ReplyKeyboardMarkup

import plugins.registry as plugin_registry
from common.bot_cmds_list import private_commands
from common.capabilities import Caps
from keyboards.admin_reply import admin_kb
from plugins.contracts import PluginCapabilities
from plugins.registry import (
    load_enabled_plugin_admin_buttons,
    load_enabled_plugin_commands,
    load_enabled_plugin_menu_buttons,
    load_enabled_plugin_routers,
    load_enabled_plugins,
)


def _caps(
    *,
    booking: bool = False,
    leads: bool = False,
    groups: bool = False,
    shop: bool = False,
    debug_mw: bool = False,
) -> Caps:
    return Caps(
        booking=booking,
        leads=leads,
        groups=groups,
        shop=shop,
        debug_mw=debug_mw,
    )


def _command_names(commands: list[BotCommand]) -> list[str]:
    return [cmd.command for cmd in commands]


def _reply_button_texts(kb: ReplyKeyboardMarkup) -> list[str]:
    texts: list[str] = []
    for row in kb.keyboard:
        for btn in row:
            if isinstance(btn, KeyboardButton):
                texts.append(btn.text)
    return texts

def _always_enabled(_caps: Caps) -> bool:
    return True


def _empty_routers() -> list[Router]:
    return []


def _make_plugin(
    *,
    name: str,
    commands: list[str] | None = None,
    admin_buttons: list[str] | None = None,
    menu_buttons: list[tuple[str, str]] | None = None,
) -> PluginCapabilities:
    return PluginCapabilities(
        name=name,
        is_enabled=_always_enabled,
        get_routers=_empty_routers,
        get_commands=lambda: [
            BotCommand(command=cmd, description=f"{cmd} desc")
            for cmd in (commands or [])
        ],
        get_admin_buttons=lambda: list(admin_buttons or []),
        get_menu_buttons=lambda: list(menu_buttons or []),
    )

def test_load_enabled_plugins_empty():
    c = _caps()

    plugins = load_enabled_plugins(c)

    assert [plugin.name for plugin in plugins] == []


def test_load_enabled_plugins_booking_only():
    c = _caps(booking=True)

    plugins = load_enabled_plugins(c)

    assert [plugin.name for plugin in plugins] == ["booking"]


def test_load_enabled_plugins_booking_and_shop():
    c = _caps(booking=True, shop=True)

    plugins = load_enabled_plugins(c)

    assert [plugin.name for plugin in plugins] == ["booking", "shop"]


def test_load_enabled_plugin_routers_empty():
    c = _caps()

    routers = load_enabled_plugin_routers(c)

    assert routers == []


def test_load_enabled_plugin_routers_booking_enabled():
    c = _caps(booking=True)

    routers = load_enabled_plugin_routers(c)

    assert len(routers) >= 1


def test_load_enabled_plugin_commands_empty():
    c = _caps()

    commands = load_enabled_plugin_commands(c)

    assert commands == []


def test_load_enabled_plugin_commands_booking_enabled():
    c = _caps(booking=True)

    commands = load_enabled_plugin_commands(c)

    assert _command_names(commands) == ["booking", "mybookings", "bookings"]


def test_load_enabled_plugin_admin_buttons_empty():
    c = _caps()

    buttons = load_enabled_plugin_admin_buttons(c)

    assert buttons == []


def test_load_enabled_plugin_admin_buttons_booking_and_shop():
    c = _caps(booking=True, shop=True)

    buttons = load_enabled_plugin_admin_buttons(c)

    assert buttons == ["Услуги", "Расписание", "Записи", "Товары"]


def test_load_enabled_plugin_menu_buttons_empty():
    c = _caps()

    buttons = load_enabled_plugin_menu_buttons(c)

    assert buttons == []


def test_load_enabled_plugin_menu_buttons_booking_enabled():
    c = _caps(booking=True)

    buttons = load_enabled_plugin_menu_buttons(c)

    assert [text for text, _ in buttons] == ["📅 Записаться", "📖 Мои записи"]


def test_private_commands_core_only():
    c = _caps()

    commands = private_commands(c)

    assert _command_names(commands) == ["start", "help", "admin"]


def test_private_commands_core_plus_booking():
    c = _caps(booking=True)

    commands = private_commands(c)

    assert _command_names(commands) == [
        "start",
        "help",
        "admin",
        "booking",
        "mybookings",
        "bookings",
    ]


def test_admin_kb_core_only():
    c = _caps()

    kb = admin_kb(c)

    assert _reply_button_texts(kb) == ["Разделы", "Страницы"]


def test_admin_kb_core_plus_booking_and_shop():
    c = _caps(booking=True, shop=True)

    kb = admin_kb(c)

    assert _reply_button_texts(kb) == [
    "Разделы",
    "Страницы",
    "Услуги",
    "Расписание",
    "Записи",
    "Товары",
    ]

def test_load_enabled_plugin_commands_raises_on_duplicate_command(monkeypatch):
    plugins = [
        _make_plugin(name="plugin_a", commands=["booking"]),
        _make_plugin(name="plugin_b", commands=["booking"]),
    ]
    monkeypatch.setattr(plugin_registry, "PLUGINS", plugins)

    c = _caps(booking=True, shop=True, groups=True)

    import pytest

    with pytest.raises(RuntimeError, match="duplicate command 'booking'"):
        load_enabled_plugin_commands(c)


def test_load_enabled_plugin_admin_buttons_raises_on_duplicate_button(monkeypatch):
    plugins = [
        _make_plugin(name="plugin_a", admin_buttons=["Услуги"]),
        _make_plugin(name="plugin_b", admin_buttons=["Услуги"]),
    ]
    monkeypatch.setattr(plugin_registry, "PLUGINS", plugins)

    c = _caps(booking=True, shop=True, groups=True)

    import pytest

    with pytest.raises(RuntimeError, match="duplicate admin button 'Услуги'"):
        load_enabled_plugin_admin_buttons(c)


def test_load_enabled_plugin_menu_buttons_raises_on_duplicate_text(monkeypatch):
    plugins = [
        _make_plugin(name="plugin_a", menu_buttons=[("📅 Записаться", "cb1")]),
        _make_plugin(name="plugin_b", menu_buttons=[("📅 Записаться", "cb2")]),
    ]
    monkeypatch.setattr(plugin_registry, "PLUGINS", plugins)

    c = _caps(booking=True, shop=True, groups=True)

    import pytest

    with pytest.raises(RuntimeError, match="duplicate menu button '📅 Записаться'"):
        load_enabled_plugin_menu_buttons(c)

def test_load_enabled_plugins_leads_only():
    c = _caps(leads=True)

    plugins = load_enabled_plugins(c)

    assert [plugin.name for plugin in plugins] == ["leads"]


def test_load_enabled_plugin_menu_buttons_leads_enabled():
    c = _caps(leads=True)

    buttons = load_enabled_plugin_menu_buttons(c)

    assert [text for text, _ in buttons] == ["📝 Оставить заявку"]