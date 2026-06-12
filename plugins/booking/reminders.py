from __future__ import annotations

import asyncio
import logging
from html import escape

from aiogram import Bot

from common.booking_time import booking_timezone_label
from database.engine import session_maker
from database.models import Booking
from database.orm_query import (
    orm_get_booking_reminder_lead_minutes,
    orm_get_due_booking_reminders,
    orm_mark_booking_reminder_sent,
)
from keyboards.inline import kb_booking_reminder

logger = logging.getLogger(__name__)


REMINDER_POLL_SECONDS = 30

def _h(value: str | None, default: str = "—") -> str:
    text = (value or "").strip()
    return escape(text or default)

def build_booking_reminder_text(booking: Booking) -> str:
    service_title_raw = (
        getattr(booking, "service_title_snapshot", None)
        or (booking.service.title if booking.service else None)
        or f"Услуга #{booking.service_id}"
    )
    service_title = _h(service_title_raw)

    if booking.slot:
        day_text = booking.slot.day.strftime("%d.%m.%Y")
        time_text = booking.slot.start_time.strftime("%H:%M")
    else:
        day_text = "—"
        time_text = "—"

    return (
        "⏰ Напоминание о записи\n\n"
        f"🧾 Услуга: {service_title}\n"
        f"📅 Дата: {day_text}\n"
        f"🕒 Время: {time_text} ({booking_timezone_label()})\n\n"
        "Если планы изменились, откройте раздел «Мои записи»."
    )


async def send_due_booking_reminders(bot: Bot) -> None:
    async with session_maker() as session:
        lead_minutes = await orm_get_booking_reminder_lead_minutes(session)

        due_bookings = await orm_get_due_booking_reminders(
            session,
            lead_minutes=lead_minutes,
        )

        for booking in due_bookings:
            try:
                await bot.send_message(
                    chat_id=booking.tg_id,
                    text=build_booking_reminder_text(booking),
                    reply_markup=kb_booking_reminder(),
                )
            except Exception:
                logger.exception(
                    "Failed to send reminder for booking #%s to tg_id=%s",
                    booking.id,
                    booking.tg_id,
                )
                continue

            marked = await orm_mark_booking_reminder_sent(session, booking_id=booking.id)
            if not marked:
                logger.warning(
                    "Reminder sent but not marked for booking #%s",
                    booking.id,
                )


async def run_booking_reminder_loop(bot: Bot) -> None:
    try:
        while True:
            await send_due_booking_reminders(bot)
            await asyncio.sleep(REMINDER_POLL_SECONDS)
    except asyncio.CancelledError:
        logger.info("Booking reminder loop stopped")
        raise