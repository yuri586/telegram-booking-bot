from __future__ import annotations

import os

os.environ.setdefault("TOKEN", "test-token")

from datetime import date, datetime, time

import pytest
from sqlalchemy import select

import database.orm_query as orm_query
from database.models import Service, TimeSlot
from database.orm_query import orm_add_timeslots_bulk
from plugins.booking.handlers_admin_timeslots import (
    _expand_range_token,
    _generate_days,
    _parse_bulk_times_input,
    _parse_weekdays,
)


def test_expand_range_token_ok():
    times_list, error = _expand_range_token("10:00-12:00/30")

    assert error is None
    assert times_list == [
        time(10, 0),
        time(10, 30),
        time(11, 0),
        time(11, 30),
    ]


def test_expand_range_token_invalid():
    times_list, error = _expand_range_token("10:00-12:00/qq")

    assert times_list == []
    assert error == "10:00-12:00/qq"


def test_parse_bulk_times_input_plain_list():
    times_list, invalid = _parse_bulk_times_input("10:00 10:30 11:00")

    assert times_list == [time(10, 0), time(10, 30), time(11, 0)]
    assert invalid == []


def test_parse_bulk_times_input_mixed_and_invalid():
    raw = "10:00-11:00/30 12:00 abc 25:99"
    times_list, invalid = _parse_bulk_times_input(raw)

    assert times_list == [
        time(10, 0),
        time(10, 30),
        time(12, 0),
    ]
    assert invalid == ["abc", "25:99"]


def test_parse_bulk_times_input_dedup_and_sort():
    raw = "11:00 10:30 10:00 10:30 10:00"
    times_list, invalid = _parse_bulk_times_input(raw)

    assert times_list == [
        time(10, 0),
        time(10, 30),
        time(11, 0),
    ]
    assert invalid == []


@pytest.mark.asyncio
async def test_orm_add_timeslots_bulk_creates_and_skips_duplicates(session, monkeypatch):
    import database.orm_query as orm_query

    monkeypatch.setattr(
        orm_query,
        "booking_now",
        lambda: datetime(2026, 3, 19, 9, 0),
    )

    service = Service(title="Bulk test service", description=None, price=None, is_active=True)
    session.add(service)
    await session.commit()
    await session.refresh(service)

    existing = TimeSlot(
        service_id=service.id,
        day=date(2026, 3, 20),
        start_time=time(10, 30),
        is_active=True,
        is_booked=False,
    )
    session.add(existing)
    await session.commit()

    created_times, duplicate_times, past_times = await orm_add_timeslots_bulk(
        session,
        service_id=service.id,
        day=date(2026, 3, 20),
        times=[time(10, 0), time(10, 30), time(11, 0)],
    )

    assert created_times == [time(10, 0), time(11, 0)]
    assert duplicate_times == [time(10, 30)]
    assert past_times == []

    result = await session.execute(
        select(TimeSlot)
        .where(
            TimeSlot.service_id == service.id,
            TimeSlot.day == date(2026, 3, 20),
        )
        .order_by(TimeSlot.start_time.asc())
    )
    slots = list(result.scalars().all())

    assert [slot.start_time for slot in slots] == [
        time(10, 0),
        time(10, 30),
        time(11, 0),
    ]


@pytest.mark.asyncio
async def test_orm_add_timeslots_bulk_filters_past_times_for_today(session, monkeypatch):
    service = Service(title="Today bulk service", description=None, price=None, is_active=True)
    session.add(service)
    await session.commit()
    await session.refresh(service)

    fixed_now = datetime(2026, 3, 20, 15, 0)
    monkeypatch.setattr(orm_query, "booking_now", lambda: fixed_now)

    past_time = time(14, 0)
    future_time = time(16, 0)
    target_day = fixed_now.date()

    created_times, duplicate_times, past_times = await orm_add_timeslots_bulk(
        session,
        service_id=service.id,
        day=target_day,
        times=[past_time, future_time],
    )

    assert duplicate_times == []
    assert created_times == [future_time]
    assert past_times == [past_time]

    result = await session.execute(
        select(TimeSlot)
        .where(
            TimeSlot.service_id == service.id,
            TimeSlot.day == target_day,
        )
        .order_by(TimeSlot.start_time.asc())
    )
    slots = list(result.scalars().all())

    assert [slot.start_time for slot in slots] == [future_time]


@pytest.mark.asyncio
async def test_orm_add_timeslots_bulk_dedups_input_times(session, monkeypatch):
    import database.orm_query as orm_query

    monkeypatch.setattr(
        orm_query,
        "booking_now",
        lambda: datetime(2026, 3, 20, 9, 0),
    )

    service = Service(title="Dedup bulk service", description=None, price=None, is_active=True)
    session.add(service)
    await session.commit()
    await session.refresh(service)

    created_times, duplicate_times, past_times = await orm_add_timeslots_bulk(
        session,
        service_id=service.id,
        day=date(2026, 3, 21),
        times=[time(10, 0), time(10, 0), time(10, 30), time(10, 30)],
    )

    assert created_times == [time(10, 0), time(10, 30)]
    assert duplicate_times == []
    assert past_times == []

def test_parse_weekdays_custom_days():
    result = _parse_weekdays("пн ср пт")
    assert result == [0, 2, 4]


def test_parse_weekdays_weekdays_keyword():
    result = _parse_weekdays("будни")
    assert result == [0, 1, 2, 3, 4]


def test_parse_weekdays_weekends_keyword():
    result = _parse_weekdays("выходные")
    assert result == [5, 6]


def test_parse_weekdays_invalid():
    result = _parse_weekdays("пн xyz пт")
    assert result is None


def test_generate_days_by_weekdays():
    start = date(2026, 3, 1)
    end = date(2026, 3, 10)
    weekdays = [0, 2, 4]  # пн ср пт

    result = _generate_days(start, end, weekdays)

    assert result == [
        date(2026, 3, 2),   # пн
        date(2026, 3, 4),   # ср
        date(2026, 3, 6),   # пт
        date(2026, 3, 9),   # пн
    ]


@pytest.mark.asyncio
async def test_range_flow_like_creation_by_weekdays(session):
    service = Service(title="Range bulk service", description=None, price=None, is_active=True)
    session.add(service)
    await session.commit()
    await session.refresh(service)

    start = date(2026, 3, 1)
    end = date(2026, 3, 10)
    weekdays = _parse_weekdays("пн ср пт")
    assert weekdays is not None
    assert weekdays == [0, 2, 4]

    days = _generate_days(start, end, weekdays)
    assert days == [
        date(2026, 3, 2),
        date(2026, 3, 4),
        date(2026, 3, 6),
        date(2026, 3, 9),
    ]

    times_list = [time(10, 0), time(10, 30)]

    total_created: list[tuple[date, time]] = []
    total_duplicates: list[tuple[date, time]] = []
    total_past: list[tuple[date, time]] = []

    for day in days:
        created_times, duplicate_times, past_times = await orm_add_timeslots_bulk(
            session,
            service_id=service.id,
            day=day,
            times=times_list,
        )

        total_created.extend((day, t) for t in created_times)
        total_duplicates.extend((day, t) for t in duplicate_times)
        total_past.extend((day, t) for t in past_times)

    assert len(total_created) == 8
    assert total_duplicates == []
    assert total_past == []

    result = await session.execute(
        select(TimeSlot)
        .where(TimeSlot.service_id == service.id)
        .order_by(TimeSlot.day.asc(), TimeSlot.start_time.asc())
    )
    slots = list(result.scalars().all())

    assert [(slot.day, slot.start_time) for slot in slots] == [
        (date(2026, 3, 2), time(10, 0)),
        (date(2026, 3, 2), time(10, 30)),
        (date(2026, 3, 4), time(10, 0)),
        (date(2026, 3, 4), time(10, 30)),
        (date(2026, 3, 6), time(10, 0)),
        (date(2026, 3, 6), time(10, 30)),
        (date(2026, 3, 9), time(10, 0)),
        (date(2026, 3, 9), time(10, 30)),
    ]
def test_parse_weekdays_supports_vsk():
    result = _parse_weekdays("пн вск")
    assert result == [0, 6]