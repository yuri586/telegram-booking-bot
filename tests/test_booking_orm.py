from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal

from database.orm_query import (
    orm_add_service,
    orm_add_timeslot,
    orm_admin_set_booking_status,
    orm_cancel_user_booking,
    orm_create_booking_for_slot,
    orm_get_booking,
    orm_get_bookings_page,
    orm_get_timeslot,
    orm_get_timeslots_by_day,
    orm_get_user_booking,
    orm_set_booking_payment_status,
    orm_update_service,
    orm_update_timeslot_datetime,
)


async def _make_service_with_slot(session):
    service = await orm_add_service(session, title="Тестовая услуга", description=None, price=None)
    slot = await orm_add_timeslot(
        session,
        service_id=service.id,
        day=date.today() + timedelta(days=1),
        start_time=time(10, 30),
    )
    return service, slot


async def test_create_booking_marks_slot_booked(session):
    _, slot = await _make_service_with_slot(session)

    booking = await orm_create_booking_for_slot(session, tg_id=1001, slot_id=slot.id)
    assert booking is not None
    assert booking.slot_id == slot.id
    assert booking.status == "new"

    slot_after = await orm_get_timeslot(session, slot.id)
    assert slot_after is not None
    assert slot_after.is_booked is True

async def test_booking_keeps_service_title_snapshot_after_service_rename(session):
    service, slot = await _make_service_with_slot(session)

    booking = await orm_create_booking_for_slot(session, tg_id=1101, slot_id=slot.id)
    assert booking is not None
    assert booking.service_title_snapshot == "Тестовая услуга"

    await orm_update_service(
        session,
        service.id,
        title="Переименованная услуга",
    )

    booking_after = await orm_get_booking(session, booking.id)
    assert booking_after is not None
    assert booking_after.service_title_snapshot == "Тестовая услуга"
    assert booking_after.service is not None
    assert booking_after.service.title == "Переименованная услуга"

async def test_booking_keeps_service_price_snapshot_after_service_price_change(session):
    service = await orm_add_service(
        session,
        title="Тестовая услуга",
        description=None,
        price=Decimal("1500"),
    )
    slot = await orm_add_timeslot(
        session,
        service_id=service.id,
        day=date.today() + timedelta(days=1),
        start_time=time(10, 30),
    )

    booking = await orm_create_booking_for_slot(session, tg_id=1201, slot_id=slot.id)
    assert booking is not None
    assert booking.service_price_snapshot == Decimal("1500.00")

    await orm_update_service(
        session,
        service.id,
        price=Decimal("2000"),
    )

    booking_after = await orm_get_booking(session, booking.id)
    assert booking_after is not None
    assert booking_after.service_price_snapshot == Decimal("1500.00")
    assert booking_after.service is not None
    assert booking_after.service.price == Decimal("2000.00")
    
async def test_cannot_double_book_same_slot(session):
    _, slot = await _make_service_with_slot(session)

    first = await orm_create_booking_for_slot(session, tg_id=1001, slot_id=slot.id)
    second = await orm_create_booking_for_slot(session, tg_id=1002, slot_id=slot.id)

    assert first is not None
    assert second is None

async def test_cannot_book_same_datetime_across_different_services(session, monkeypatch):
    import database.orm_query as orm_query

    monkeypatch.setattr(
        orm_query,
        "booking_now",
        lambda: datetime(2026, 3, 20, 9, 0),
    )

    service_1 = await orm_add_service(
        session,
        title="Первая консультация",
        description=None,
        price=None,
    )
    service_2 = await orm_add_service(
        session,
        title="Индивидуальная консультация",
        description=None,
        price=None,
    )

    slot_1 = await orm_add_timeslot(
    session,
    service_id=service_1.id,
    day=date(2026, 3, 20),
    start_time=time(11, 0),
    )
    slot_2 = await orm_add_timeslot(
        session,
        service_id=service_2.id,
        day=date(2026, 3, 20),
        start_time=time(11, 0),
    )

    slot_1_id = slot_1.id
    slot_2_id = slot_2.id

    booking_1 = await orm_create_booking_for_slot(
        session,
        tg_id=1001,
        slot_id=slot_1_id,
    )
    booking_2 = await orm_create_booking_for_slot(
        session,
        tg_id=1002,
        slot_id=slot_2_id,
    )

    assert booking_1 is not None
    assert booking_2 is None

    slot_1_after = await orm_get_timeslot(session, slot_1_id)
    slot_2_after = await orm_get_timeslot(session, slot_2_id)

    assert slot_1_after is not None
    assert slot_2_after is not None
    assert slot_1_after.is_booked is True
    assert slot_2_after.is_booked is False

async def test_user_cancel_releases_slot_and_updates_status(session):
    _, slot = await _make_service_with_slot(session)
    booking = await orm_create_booking_for_slot(session, tg_id=2001, slot_id=slot.id)
    assert booking is not None

    cancelled, reason  = await orm_cancel_user_booking(session, booking_id=booking.id, tg_id=2001)
    assert cancelled is True
    assert reason == "cancelled"

    booking_after = await orm_get_user_booking(session, booking_id=booking.id, tg_id=2001)
    assert booking_after is not None
    assert booking_after.status == "cancelled_by_user"

    slot_after = await orm_get_timeslot(session, slot.id)
    assert slot_after is not None
    assert slot_after.is_booked is False


async def test_admin_status_changes_and_releases_slot_on_cancel(session):
    _, slot = await _make_service_with_slot(session)
    booking = await orm_create_booking_for_slot(session, tg_id=3001, slot_id=slot.id)
    assert booking is not None

    ok, reason, confirmed = await orm_admin_set_booking_status(
        session,
        booking_id=booking.id,
        target_status="confirmed",
    )
    assert ok is True
    assert reason == "updated"
    assert confirmed is not None
    assert confirmed.status == "confirmed"

    ok, reason, cancelled = await orm_admin_set_booking_status(
        session,
        booking_id=booking.id,
        target_status="cancelled_by_admin",
    )
    assert ok is True
    assert reason == "updated"
    assert cancelled is not None
    assert cancelled.status == "cancelled_by_admin"

    slot_after = await orm_get_timeslot(session, slot.id)
    assert slot_after is not None
    assert slot_after.is_booked is False


async def test_admin_cannot_finish_new_booking(session):
    _, slot = await _make_service_with_slot(session)

    booking = await orm_create_booking_for_slot(session, tg_id=4001, slot_id=slot.id)
    assert booking is not None
    assert booking.status == "new"

    ok, reason, updated = await orm_admin_set_booking_status(
        session,
        booking_id=booking.id,
        target_status="done",
    )

    assert ok is False
    assert reason == "bad_transition"
    assert updated is not None
    assert updated.status == "new"


async def test_cannot_change_payment_status_for_cancelled_booking(session):
    _, slot = await _make_service_with_slot(session)

    booking = await orm_create_booking_for_slot(session, tg_id=5001, slot_id=slot.id)
    assert booking is not None
    booking_id = booking.id
    assert booking.payment_status == "unpaid"

    ok, reason, cancelled = await orm_admin_set_booking_status(
        session,
        booking_id=booking_id,
        target_status="cancelled_by_admin",
    )
    assert ok is True
    assert reason == "updated"
    assert cancelled is not None
    assert cancelled.status == "cancelled_by_admin"

    changed = await orm_set_booking_payment_status(
        session,
        booking_id=booking_id,
        payment_status="paid",
    )
    assert changed is False

    booking_after = await orm_get_booking(session, booking_id)
    assert booking_after is not None
    assert booking_after.payment_status == "unpaid"

async def test_user_cannot_cancel_started_booking(session, monkeypatch):
    import database.orm_query as orm_query

    monkeypatch.setattr(
        orm_query,
        "booking_now",
        lambda: datetime(2026, 3, 20, 9, 0),
    )

    service = await orm_add_service(
        session,
        title="Тестовая услуга",
        description=None,
        price=None,
    )
    slot = await orm_add_timeslot(
        session,
        service_id=service.id,
        day=date(2026, 3, 20),
        start_time=time(10, 0),
    )

    booking = await orm_create_booking_for_slot(session, tg_id=6001, slot_id=slot.id)
    assert booking is not None

    monkeypatch.setattr(
        orm_query,
        "booking_now",
        lambda: datetime(2026, 3, 20, 12, 0),
    )

    cancelled, reason = await orm_cancel_user_booking(
        session,
        booking_id=booking.id,
        tg_id=6001,
    )

    assert cancelled is False
    assert reason == "too_late"

async def test_admin_cannot_finish_booking_before_slot_start(session):
    _, slot = await _make_service_with_slot(session)

    booking = await orm_create_booking_for_slot(session, tg_id=7001, slot_id=slot.id)
    assert booking is not None

    ok, reason, confirmed = await orm_admin_set_booking_status(
        session,
        booking_id=booking.id,
        target_status="confirmed",
    )
    assert ok is True
    assert confirmed is not None
    assert confirmed.status == "confirmed"

    ok, reason, updated = await orm_admin_set_booking_status(
        session,
        booking_id=booking.id,
        target_status="done",
    )

    assert ok is False
    assert reason == "too_early"
    assert updated is not None
    assert updated.status == "confirmed"


async def test_payment_status_update_is_atomic_against_stale_cancelled_state(session):
    _, slot = await _make_service_with_slot(session)
    slot_id = slot.id

    booking = await orm_create_booking_for_slot(session, tg_id=8001, slot_id=slot_id)
    assert booking is not None
    booking_id = booking.id
    assert booking.payment_status == "unpaid"

    ok, reason, cancelled = await orm_admin_set_booking_status(
        session,
        booking_id=booking_id,
        target_status="cancelled_by_admin",
    )
    assert ok is True
    assert reason == "updated"
    assert cancelled is not None
    assert cancelled.status == "cancelled_by_admin"

    changed = await orm_set_booking_payment_status(
        session,
        booking_id=booking_id,
        payment_status="paid",
    )

    assert changed is False

    booking_after = await orm_get_booking(session, booking_id)
    assert booking_after is not None
    assert booking_after.status == "cancelled_by_admin"
    assert booking_after.payment_status == "unpaid"

    slot_after = await orm_get_timeslot(session, slot_id)
    assert slot_after is not None


async def test_cannot_update_timeslot_datetime_when_any_booking_exists(session):
    _, slot = await _make_service_with_slot(session)
    slot_id = slot.id
    old_day = slot.day
    old_time = slot.start_time

    booking = await orm_create_booking_for_slot(session, tg_id=8001, slot_id=slot_id)
    assert booking is not None
    booking_id = booking.id

    cancelled, reason = await orm_cancel_user_booking(
        session,
        booking_id=booking_id,
        tg_id=8001,
    )
    assert cancelled is True
    assert reason == "cancelled"

    updated = await orm_update_timeslot_datetime(
        session,
        slot_id=slot_id,
        day=old_day + timedelta(days=2),
        start_time=time(15, 0),
    )
    assert updated is False

    slot_after = await orm_get_timeslot(session, slot_id)
    assert slot_after is not None
    assert slot_after.day == old_day
    assert slot_after.start_time == old_time

async def test_admin_bookings_page_upcoming_excludes_today_past_slot(session, monkeypatch):
    import database.orm_query as orm_query

    monkeypatch.setattr(
        orm_query,
        "booking_now",
        lambda: datetime(2026, 3, 20, 9, 0),
    )

    service = await orm_add_service(session, title="Тестовая услуга", description=None, price=None)

    past_slot = await orm_add_timeslot(
        session,
        service_id=service.id,
        day=date(2026, 3, 20),
        start_time=time(10, 0),
    )
    future_slot = await orm_add_timeslot(
        session,
        service_id=service.id,
        day=date(2026, 3, 20),
        start_time=time(15, 0),
    )

    past_booking = await orm_create_booking_for_slot(session, tg_id=9001, slot_id=past_slot.id)
    future_booking = await orm_create_booking_for_slot(session, tg_id=9002, slot_id=future_slot.id)

    assert past_booking is not None
    assert future_booking is not None

    monkeypatch.setattr(
        orm_query,
        "booking_now",
        lambda: datetime(2026, 3, 20, 12, 0),
    )

    page = await orm_get_bookings_page(session, page=1, per_page=10, mode=4, day_mode=0)

    booking_ids = [booking.id for booking in page.items]
    assert future_booking.id in booking_ids
    assert past_booking.id not in booking_ids

async def test_admin_bookings_page_is_sorted_by_slot_datetime(session, monkeypatch):
    import database.orm_query as orm_query

    fake_now = datetime(2026, 3, 20, 9, 0)
    monkeypatch.setattr(orm_query, "booking_now", lambda: fake_now)

    service = await orm_add_service(session, title="Тестовая услуга", description=None, price=None)

    slot_b = await orm_add_timeslot(
        session,
        service_id=service.id,
        day=date(2026, 3, 21),
        start_time=time(9, 0),
    )
    slot_c = await orm_add_timeslot(
        session,
        service_id=service.id,
        day=date(2026, 3, 20),
        start_time=time(15, 0),
    )
    slot_a = await orm_add_timeslot(
        session,
        service_id=service.id,
        day=date(2026, 3, 20),
        start_time=time(13, 0),
    )

    booking_b = await orm_create_booking_for_slot(session, tg_id=9101, slot_id=slot_b.id)
    booking_c = await orm_create_booking_for_slot(session, tg_id=9102, slot_id=slot_c.id)
    booking_a = await orm_create_booking_for_slot(session, tg_id=9103, slot_id=slot_a.id)

    assert booking_a is not None
    assert booking_b is not None
    assert booking_c is not None

    page = await orm_get_bookings_page(session, page=1, per_page=10, mode=4, day_mode=2)

    actual = [
        (booking.slot.day, booking.slot.start_time)
        for booking in page.items
        if booking.slot is not None
    ]

    assert actual == [
        (date(2026, 3, 20), time(13, 0)),
        (date(2026, 3, 20), time(15, 0)),
        (date(2026, 3, 21), time(9, 0)),
    ]

async def test_cannot_update_timeslot_datetime_when_slot_is_booked(session):
    _, slot = await _make_service_with_slot(session)
    slot_id = slot.id
    old_day = slot.day
    old_time = slot.start_time

    booking = await orm_create_booking_for_slot(session, tg_id=9001, slot_id=slot_id)
    assert booking is not None

    updated = await orm_update_timeslot_datetime(
        session,
        slot_id=slot_id,
        day=old_day + timedelta(days=1),
        start_time=time(15, 0),
    )
    assert updated is False

    slot_after = await orm_get_timeslot(session, slot_id)
    assert slot_after is not None
    assert slot_after.day == old_day
    assert slot_after.start_time == old_time

async def test_cannot_create_booking_for_past_today_slot(session, monkeypatch):
    import database.orm_query as orm_query

    monkeypatch.setattr(
        orm_query,
        "booking_now",
        lambda: datetime(2026, 3, 20, 12, 1),
    )

    service = await orm_add_service(session, title="Тест", description=None, price=None)
    slot = await orm_add_timeslot(
        session,
        service_id=service.id,
        day=date(2026, 3, 20),
        start_time=time(12, 0),
    )

    booking = await orm_create_booking_for_slot(session, tg_id=9999, slot_id=slot.id)

    assert booking is None

async def test_timeslots_by_day_excludes_slot_at_current_minute(session, monkeypatch):
    import database.orm_query as orm_query

    monkeypatch.setattr(
        orm_query,
        "booking_now",
        lambda: datetime(2026, 3, 20, 12, 0),
    )

    service = await orm_add_service(
        session,
        title="Тестовая услуга",
        description=None,
        price=None,
    )

    slot_at_now = await orm_add_timeslot(
        session,
        service_id=service.id,
        day=date(2026, 3, 20),
        start_time=time(12, 0),
    )
    slot_after_now = await orm_add_timeslot(
        session,
        service_id=service.id,
        day=date(2026, 3, 20),
        start_time=time(12, 1),
    )

    slots = await orm_get_timeslots_by_day(
        session,
        service_id=service.id,
        day=date(2026, 3, 20),
    )

    slot_ids = [slot.id for slot in slots]

    assert slot_at_now.id not in slot_ids
    assert slot_after_now.id in slot_ids
    assert [slot.start_time for slot in slots] == [time(12, 1)]