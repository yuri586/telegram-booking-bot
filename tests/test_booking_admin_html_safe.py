from __future__ import annotations

from datetime import date, time
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot

from plugins.booking.handlers_admin_services import (
    _notify_users_about_service_cleanup,
    _service_card_text,
)
from plugins.booking.handlers_admin_timeslots import (
    _notify_users_about_slot_cleanup,
    _slot_card_text,
)


def test_service_card_text_escapes_title_and_description() -> None:
    text = _service_card_text(
        title="A & B <online>",
        description="Описание <тест> & проверка",
        price=None,
        slots_count=1,
        bookings_count=2,
        active_bookings_count=1,
    )

    assert "A &amp; B &lt;online&gt;" in text
    assert "Описание &lt;тест&gt; &amp; проверка" in text


def test_slot_card_text_escapes_service_title() -> None:
    text = _slot_card_text(
        service_title="Алгебра & Геометрия <онлайн>",
        slot_day=date(2026, 3, 20),
        slot_time=time(12, 0),
        is_active=True,
        is_booked=False,
    )

    assert "Алгебра &amp; Геометрия &lt;онлайн&gt;" in text


@pytest.mark.asyncio
async def test_service_cleanup_notification_escapes_service_title() -> None:
    send_message_mock = AsyncMock()
    bot = cast(Bot, SimpleNamespace(send_message=send_message_mock))

    await _notify_users_about_service_cleanup(
        bot,
        [1],
        service_title="A & B <online>",
    )

    send_message_mock.assert_awaited_once()

    await_args = send_message_mock.await_args
    assert await_args is not None

    sent_text = await_args.kwargs["text"]
    assert "A &amp; B &lt;online&gt;" in sent_text


@pytest.mark.asyncio
async def test_slot_cleanup_notification_escapes_service_title() -> None:
    send_message_mock = AsyncMock()
    bot = cast(Bot, SimpleNamespace(send_message=send_message_mock))

    await _notify_users_about_slot_cleanup(
        bot,
        [1],
        service_title="A & B <online>",
        slot_day=date(2026, 3, 20),
        slot_time=time(12, 0),
    )

    send_message_mock.assert_awaited_once()

    await_args = send_message_mock.await_args
    assert await_args is not None

    sent_text = await_args.kwargs["text"]
    assert "A &amp; B &lt;online&gt;" in sent_text