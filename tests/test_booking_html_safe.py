from __future__ import annotations

from datetime import date, time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import plugins.booking.handlers_admin_booking as admin_booking
import plugins.booking.handlers_user_booking as user_booking


def _make_booking():
    service = SimpleNamespace(title="Первая <b>консультация</b> & тест")
    slot = SimpleNamespace(day=date(2026, 3, 20), start_time=time(10, 30))
    return SimpleNamespace(
        id=1,
        tg_id=123456,
        service=service,
        service_id=10,
        slot=slot,
        customer_name="Иван <Петров> & Co",
        customer_phone="+7999<123>&45",
        status="new",
        payment_status="unpaid",
    )


def test_user_booking_summary_escapes_dynamic_fields():
    booking = _make_booking()

    data = user_booking._booking_summary(booking)

    assert data["service_title"] == "Первая &lt;b&gt;консультация&lt;/b&gt; &amp; тест"
    assert data["customer_name"] == "Иван &lt;Петров&gt; &amp; Co"
    assert data["customer_phone"] == "+7999&lt;123&gt;&amp;45"


def test_admin_booking_text_escapes_dynamic_fields():
    booking = _make_booking()

    text = admin_booking._booking_text(booking)

    assert '<b>Запись #1</b>' in text
    assert "Первая &lt;b&gt;консультация&lt;/b&gt; &amp; тест" in text
    assert "Иван &lt;Петров&gt; &amp; Co" in text
    assert "+7999&lt;123&gt;&amp;45" in text


@pytest.mark.asyncio
async def test_status_change_notification_escapes_service_title():
    booking = _make_booking()
    booking.status = "confirmed"

    bot = AsyncMock()

    await admin_booking._notify_user_about_status_change(bot, booking)

    bot.send_message.assert_awaited_once()
    kwargs = bot.send_message.await_args.kwargs
    assert kwargs["chat_id"] == booking.tg_id
    assert "Первая &lt;b&gt;консультация&lt;/b&gt; &amp; тест" in kwargs["text"]