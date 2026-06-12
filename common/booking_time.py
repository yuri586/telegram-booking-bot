from __future__ import annotations

import os
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

_BOOKING_TIMEZONE = "BOOKING_TIMEZONE"
_DEFAULT_BOOKING_TIMEZONE = "UTC"

_TIMEZONE_LABELS = {
    "Europe/Moscow": "МСК",
    "Asia/Yekaterinburg": "YEKT",
    "UTC": "UTC",
}


def booking_tz_name() -> str:
    return os.getenv(_BOOKING_TIMEZONE, _DEFAULT_BOOKING_TIMEZONE).strip() or _DEFAULT_BOOKING_TIMEZONE


def booking_tz() -> ZoneInfo:
    return ZoneInfo(booking_tz_name())


def booking_timezone_label() -> str:
    tz_name = booking_tz_name()
    return _TIMEZONE_LABELS.get(tz_name, tz_name)


def booking_time_note() -> str:
    return f"Все времена указаны по часовому поясу: {booking_timezone_label()}"


def booking_now() -> datetime:
    return datetime.now(booking_tz()).replace(tzinfo=None)


def booking_today() -> date:
    return booking_now().date()


def booking_slot_dt(day: date, start_time: time) -> datetime:
    return datetime.combine(day, start_time)