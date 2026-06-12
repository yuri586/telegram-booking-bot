from __future__ import annotations

from datetime import date, time, timedelta
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot

import plugins.booking.handlers_admin_booking as admin_booking
from database.orm_query import (
    orm_add_service,
    orm_add_timeslot,
    orm_admin_set_booking_status,
    orm_create_booking_for_slot,
    orm_get_active_booking_broadcast_tg_ids,
)


@pytest.mark.asyncio
async def test_get_active_booking_broadcast_tg_ids_returns_unique_active_users(session):
    service = await orm_add_service(session, title="Тест", description=None, price=None)

    slot_1 = await orm_add_timeslot(
        session,
        service_id=service.id,
        day=date.today() + timedelta(days=1),
        start_time=time(10, 0),
    )
    slot_2 = await orm_add_timeslot(
        session,
        service_id=service.id,
        day=date.today() + timedelta(days=2),
        start_time=time(11, 0),
    )
    slot_3 = await orm_add_timeslot(
        session,
        service_id=service.id,
        day=date.today() + timedelta(days=3),
        start_time=time(12, 0),
    )
    slot_4 = await orm_add_timeslot(
        session,
        service_id=service.id,
        day=date.today() + timedelta(days=4),
        start_time=time(13, 0),
    )

    booking_1 = await orm_create_booking_for_slot(session, tg_id=1001, slot_id=slot_1.id)
    booking_2 = await orm_create_booking_for_slot(session, tg_id=1001, slot_id=slot_2.id)
    booking_3 = await orm_create_booking_for_slot(session, tg_id=1002, slot_id=slot_3.id)
    booking_4 = await orm_create_booking_for_slot(session, tg_id=1003, slot_id=slot_4.id)

    assert booking_1 is not None
    assert booking_2 is not None
    assert booking_3 is not None
    assert booking_4 is not None

    ok, _, confirmed = await orm_admin_set_booking_status(
        session,
        booking_id=booking_2.id,
        target_status="confirmed",
    )
    assert ok is True
    assert confirmed is not None

    ok, _, cancelled = await orm_admin_set_booking_status(
        session,
        booking_id=booking_3.id,
        target_status="cancelled_by_admin",
    )
    assert ok is True
    assert cancelled is not None

    tg_ids = await orm_get_active_booking_broadcast_tg_ids(session)

    assert tg_ids == [1001, 1003]


@pytest.mark.asyncio
async def test_send_booking_broadcast_counts_success_and_failure():
    bot = SimpleNamespace(
        send_message=AsyncMock(side_effect=[None, RuntimeError("boom")])
    )

    sent, failed = await admin_booking._send_booking_broadcast(
        cast(Bot, bot),
        [111, 222],
        "<b>Привет</b>",
    )

    assert sent == 1
    assert failed == 1

    first_call = bot.send_message.await_args_list[0]
    assert first_call.kwargs["chat_id"] == 111
    assert first_call.kwargs["text"] == "&lt;b&gt;Привет&lt;/b&gt;"