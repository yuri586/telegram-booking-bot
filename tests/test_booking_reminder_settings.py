from __future__ import annotations

from datetime import date, datetime, time

import pytest

import database.orm_query as orm_query
import plugins.booking.reminders as reminders
from database.orm_query import (
    orm_add_service,
    orm_add_timeslot,
    orm_admin_set_booking_status,
    orm_create_booking_for_slot,
    orm_get_booking_reminder_lead_minutes,
    orm_get_due_booking_reminders,
    orm_set_booking_reminder_lead_minutes,
)


class _SessionCtx:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_get_booking_reminder_lead_minutes_returns_default_when_missing(session):
    value = await orm_get_booking_reminder_lead_minutes(session)
    assert value == 60


@pytest.mark.asyncio
async def test_set_booking_reminder_lead_minutes_updates_value(session):
    ok = await orm_set_booking_reminder_lead_minutes(session, 1440)
    assert ok is True

    value = await orm_get_booking_reminder_lead_minutes(session)
    assert value == 1440


@pytest.mark.asyncio
async def test_set_booking_reminder_lead_minutes_rejects_invalid_value(session):
    ok = await orm_set_booking_reminder_lead_minutes(session, 999)
    assert ok is False


@pytest.mark.asyncio
async def test_due_booking_reminders_use_saved_lead_minutes(session, monkeypatch):
    monkeypatch.setattr(
        orm_query,
        "booking_now",
        lambda: datetime(2026, 3, 20, 10, 0),
    )

    await orm_set_booking_reminder_lead_minutes(session, 180)

    service = await orm_add_service(session, title="Тест", description=None, price=None)

    slot_due = await orm_add_timeslot(
        session,
        service_id=service.id,
        day=date(2026, 3, 20),
        start_time=time(12, 30),
    )
    slot_not_due = await orm_add_timeslot(
        session,
        service_id=service.id,
        day=date(2026, 3, 20),
        start_time=time(14, 30),
    )

    booking_due = await orm_create_booking_for_slot(session, tg_id=1001, slot_id=slot_due.id)
    booking_not_due = await orm_create_booking_for_slot(session, tg_id=1002, slot_id=slot_not_due.id)

    assert booking_due is not None
    assert booking_not_due is not None

    ok, _, confirmed_1 = await orm_admin_set_booking_status(
        session,
        booking_id=booking_due.id,
        target_status="confirmed",
    )
    assert ok is True
    assert confirmed_1 is not None

    ok, _, confirmed_2 = await orm_admin_set_booking_status(
        session,
        booking_id=booking_not_due.id,
        target_status="confirmed",
    )
    assert ok is True
    assert confirmed_2 is not None

    lead_minutes = await orm_get_booking_reminder_lead_minutes(session)
    due = await orm_get_due_booking_reminders(session, lead_minutes=lead_minutes)

    due_ids = [booking.id for booking in due]
    assert booking_due.id in due_ids
    assert booking_not_due.id not in due_ids


@pytest.mark.asyncio
async def test_send_due_booking_reminders_reads_lead_minutes_from_db(session, monkeypatch):
    monkeypatch.setattr(
        orm_query,
        "booking_now",
        lambda: datetime(2026, 3, 20, 10, 0),
    )
    monkeypatch.setattr(reminders, "session_maker", lambda: _SessionCtx(session))

    await orm_set_booking_reminder_lead_minutes(session, 180)

    service = await orm_add_service(session, title="Тест", description=None, price=None)
    slot = await orm_add_timeslot(
        session,
        service_id=service.id,
        day=date(2026, 3, 20),
        start_time=time(12, 30),
    )

    booking = await orm_create_booking_for_slot(session, tg_id=1001, slot_id=slot.id)
    assert booking is not None

    ok, _, confirmed = await orm_admin_set_booking_status(
        session,
        booking_id=booking.id,
        target_status="confirmed",
    )
    assert ok is True
    assert confirmed is not None

    sent_messages: list[tuple[int, str]] = []

    class FakeBot:
        async def send_message(self, chat_id: int, text: str, reply_markup=None) -> None:
            sent_messages.append((chat_id, text))

    await reminders.send_due_booking_reminders(FakeBot())  # type: ignore[arg-type]

    assert len(sent_messages) == 1
    assert sent_messages[0][0] == 1001