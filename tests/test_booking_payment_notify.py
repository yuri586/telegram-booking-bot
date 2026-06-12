from __future__ import annotations

from datetime import date, time, timedelta
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot
from aiogram.types import InlineKeyboardButton

import plugins.booking.handlers_admin_booking as admin_booking
from database.orm_query import (
    orm_add_service,
    orm_add_timeslot,
    orm_admin_set_booking_status,
    orm_create_booking_for_slot,
    orm_get_booking,
    orm_set_booking_payment_status,
)


@pytest.mark.asyncio
async def test_notify_user_about_payment_marked_sends_message_with_my_bookings_button(session):
    service = await orm_add_service(session, title="Тестовая услуга", description=None, price=None)
    slot = await orm_add_timeslot(
        session,
        service_id=service.id,
        day=date.today() + timedelta(days=1),
        start_time=time(12, 0),
    )

    booking = await orm_create_booking_for_slot(session, tg_id=555001, slot_id=slot.id)
    assert booking is not None

    ok, _, confirmed = await orm_admin_set_booking_status(
        session,
        booking_id=booking.id,
        target_status="confirmed",
    )
    assert ok is True
    assert confirmed is not None
    paid_changed = await orm_set_booking_payment_status(
        session,
        booking_id=booking.id,
        payment_status="paid",
    )
    assert paid_changed is True

    paid_booking = await orm_get_booking(session, booking.id)
    assert paid_booking is not None
    assert paid_booking.payment_status == "paid"

    bot = SimpleNamespace(send_message=AsyncMock())

    await admin_booking._notify_user_about_payment_marked(cast(Bot, bot), paid_booking)

    bot.send_message.assert_awaited_once()
    kwargs = bot.send_message.await_args.kwargs

    assert kwargs["chat_id"] == paid_booking.tg_id
    assert "Оплата по вашей записи обновлена" in kwargs["text"]
    assert "Оплата: 💳 оплачено" in kwargs["text"]

    reply_markup = kwargs["reply_markup"]
    button_texts = [
        button.text
        for row in reply_markup.inline_keyboard
        for button in row
        if isinstance(button, InlineKeyboardButton)
    ]
    assert "📖 Мои записи" in button_texts


def test_payment_rule_hint_mentions_user_notification_for_unpaid_booking():
    booking = SimpleNamespace(status="confirmed", payment_status="unpaid")
    hint = admin_booking._payment_rule_hint(booking)
    assert "клиент получит уведомление" in hint


def test_payment_rule_hint_for_paid_booking_is_still_stable():
    booking = SimpleNamespace(status="confirmed", payment_status="paid")
    hint = admin_booking._payment_rule_hint(booking)
    assert hint == "ℹ️ Примечание: оплата уже отмечена."