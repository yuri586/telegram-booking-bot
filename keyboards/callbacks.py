from __future__ import annotations

from aiogram.filters.callback_data import CallbackData


class MenuCB(CallbackData, prefix="m"):
    level: int
    page: str = "main"
    section: int | None = None
    item: int | None = None
    p: int = 1
    action: str | None = None


class BookingCB(CallbackData, prefix="b"):
    action: str
    service: int | None = None
    day: str | None = None
    slot: int | None = None
    booking: int | None = None


class AdminCB(CallbackData, prefix="ac"):
    action: str
    section: int | None = None
    item: int | None = None
    p: int = 1
    mode: int = 0


class SlotAdminCB(CallbackData, prefix="ts"):
    action: str
    service: int | None = None
    slot: int | None = None
    p: int = 1
    mode: int = 0


class ServiceAdminCB(CallbackData, prefix="svc"):
    action: str
    service: int | None = None
    show: int = 0


class BookingAdminCB(CallbackData, prefix="abk"):
    action: str
    booking: int | None = None
    p: int = 1
    mode: int = 0
    day_mode: int = 2
    value: int | None = None

class BannerAdminCB(CallbackData, prefix="bnr"):
    action: str
    page: str | None = None

class LeadCB(CallbackData, prefix="lead"):
    action: str
    request_type: str | None = None