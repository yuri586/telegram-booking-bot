from __future__ import annotations

from aiogram import Router
from aiogram.types import BotCommand

from common.capabilities import Caps
from keyboards.callbacks import BookingCB
from plugins.contracts import PluginCapabilities


def _enabled(caps: Caps) -> bool:
    return caps.booking


def _routers() -> list[Router]:
    from plugins.booking.handlers_admin_booking import bookings_admin_router
    from plugins.booking.handlers_admin_services import services_admin_router
    from plugins.booking.handlers_admin_timeslots import timeslots_admin_router
    from plugins.booking.handlers_user_booking import booking_user_router

    return [
        booking_user_router,
        services_admin_router,
        timeslots_admin_router,
        bookings_admin_router,
    ]


def _user_commands() -> list[BotCommand]:
    return [
        BotCommand(command="booking", description="Записаться"),
        BotCommand(command="mybookings", description="Мои записи"),
    ]


def _admin_commands() -> list[BotCommand]:
    return [
        BotCommand(command="bookings", description="Записи (админ)"),
    ]


def _admin_buttons() -> list[str]:
    return ["Услуги", "Расписание", "Записи"]


def _menu_buttons() -> list[tuple[str, str]]:
    return [
        ("📅 Записаться", BookingCB(action="services").pack()),
        ("📖 Мои записи", BookingCB(action="my").pack()),
    ]


plugin = PluginCapabilities(
    name="booking",
    is_enabled=_enabled,
    get_routers=_routers,
    get_user_commands=_user_commands,
    get_admin_commands=_admin_commands,
    get_admin_buttons=_admin_buttons,
    get_menu_buttons=_menu_buttons,
)