from __future__ import annotations

from datetime import date, datetime, time

import pytest

import database.orm_query as orm_query
import plugins.booking.handlers_admin_timeslots as admin_timeslots
from database.orm_query import (
    orm_add_service,
    orm_add_timeslot,
    orm_add_timeslots_bulk,
    orm_get_timeslots_by_day,
)


@pytest.mark.asyncio
async def test_get_timeslots_by_day_uses_booking_business_now(session, monkeypatch):
    fixed_now = datetime(2026, 3, 20, 15, 0)
    monkeypatch.setattr(orm_query, "booking_now", lambda: fixed_now)

    service = await orm_add_service(session, title="Тест", description=None, price=None)
    await orm_add_timeslot(
        session,
        service_id=service.id,
        day=fixed_now.date(),
        start_time=time(14, 0),
    )
    await orm_add_timeslot(
        session,
        service_id=service.id,
        day=fixed_now.date(),
        start_time=time(16, 0),
    )

    slots = await orm_get_timeslots_by_day(
        session,
        service_id=service.id,
        day=fixed_now.date(),
    )

    assert [slot.start_time for slot in slots] == [time(16, 0)]


@pytest.mark.asyncio
async def test_bulk_add_timeslots_filters_past_by_booking_business_now(session, monkeypatch):
    fixed_now = datetime(2026, 3, 20, 15, 0)
    monkeypatch.setattr(orm_query, "booking_now", lambda: fixed_now)

    service = await orm_add_service(session, title="Тест", description=None, price=None)

    created, duplicates, past = await orm_add_timeslots_bulk(
        session,
        service_id=service.id,
        day=fixed_now.date(),
        times=[time(14, 0), time(16, 0)],
    )

    assert created == [time(16, 0)]
    assert duplicates == []
    assert past == [time(14, 0)]


def test_slot_in_past_uses_booking_business_now(monkeypatch):
    fixed_now = datetime(2026, 3, 20, 15, 0)
    monkeypatch.setattr(admin_timeslots, "booking_now", lambda: fixed_now)

    assert admin_timeslots._slot_in_past(date(2026, 3, 20), time(14, 0)) is True
    assert admin_timeslots._slot_in_past(date(2026, 3, 20), time(16, 0)) is False