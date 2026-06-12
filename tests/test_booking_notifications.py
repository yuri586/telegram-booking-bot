from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot, types
from aiogram.fsm.context import FSMContext

import database.orm_query as orm_query
import plugins.booking.handlers_user_booking as user_booking
import plugins.booking.reminders as reminders
from database.models import Booking
from database.orm_query import (
    orm_add_service,
    orm_add_timeslot,
    orm_admin_set_booking_status,
    orm_create_booking_for_slot,
    orm_get_booking,
    orm_get_due_booking_reminders,
    orm_mark_booking_reminder_sent,
    orm_update_service,
)


class FakeState:
    def __init__(self, data: dict):
        self._data = data
        self.cleared = False

    async def get_data(self) -> dict:
        return self._data

    async def clear(self) -> None:
        self.cleared = True

class _SessionCtx:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False

class FakeMessage:
    def __init__(self, tg_id: int):
        self.from_user = SimpleNamespace(id=tg_id)
        self.answers: list[tuple[str, object | None]] = []

    async def answer(self, text: str, reply_markup=None) -> None:
        self.answers.append((text, reply_markup))



def test_booking_summary_prefers_price_snapshot_over_live_service_price():
    booking = SimpleNamespace(
        service_price_snapshot=Decimal("1500.00"),
        service_title_snapshot="Тестовая услуга",
        service=SimpleNamespace(title="Тестовая услуга", price=Decimal("2000.00")),
        service_id=1,
        slot=None,
        customer_name="Юрий",
        customer_phone="+79991234567",
        status="new",
    )

    data = user_booking._booking_summary(booking)

    assert data["price_text"] == "1500 ₽"


def test_booking_summary_falls_back_to_live_service_price_when_snapshot_missing():
    booking = SimpleNamespace(
        service_price_snapshot=None,
        service_title_snapshot="Тестовая услуга",
        service=SimpleNamespace(title="Тестовая услуга", price=Decimal("2000.00")),
        service_id=1,
        slot=None,
        customer_name="Юрий",
        customer_phone="+79991234567",
        status="new",
    )

    data = user_booking._booking_summary(booking)

    assert data["price_text"] == "2000 ₽"

@pytest.mark.asyncio
async def test_finish_booking_with_phone_notifies_admins_once(session, monkeypatch):
    booking = SimpleNamespace(id=123, status="new")

    fake_notify = AsyncMock()
    monkeypatch.setattr(user_booking, "_notify_admins_about_new_booking", fake_notify)

    async def fake_finalize_booking(*args, **kwargs):
        return True, "ok", booking

    monkeypatch.setattr(user_booking, "_finalize_booking", fake_finalize_booking)
    monkeypatch.setattr(user_booking, "ui_labels", lambda: {})
    monkeypatch.setattr(user_booking, "kb_booking_success", lambda labels: None)
    monkeypatch.setattr(user_booking, "kb_booking_resume", lambda labels: None)

    state = FakeState(
        {
            # если в _finish_booking_with_phone у тебя ключи называются иначе,
            # поставь здесь реальные имена из функции
            "service_id": 1,
            "day": "2026-03-20",
            "slot_id": 10,
            "customer_name": "Юрий",
        }
    )
    message = FakeMessage(tg_id=7001)
    bot = SimpleNamespace()

    await user_booking._finish_booking_with_phone(
        message=cast(types.Message, message),
        state=cast(FSMContext, state),
        session=session,
        phone="+79991234567",
        bot=cast(Bot, bot),
    )

    fake_notify.assert_awaited_once_with(bot, booking)
    assert state.cleared is True

@pytest.mark.asyncio
async def test_finalize_booking_rejects_inactive_service(session):
    service = await orm_add_service(
        session,
        title="Тестовая услуга",
        description=None,
        price=None,
    )
    slot = await orm_add_timeslot(
        session,
        service_id=service.id,
        day=date.today() + timedelta(days=1),
        start_time=time(12, 0),
    )

    await orm_update_service(session, service.id, is_active=False)

    ok, text, booking = await user_booking._finalize_booking(
        session=session,
        tg_id=9001,
        service_id=service.id,
        day_iso=slot.day.isoformat(),
        slot_id=slot.id,
        customer_name="Юрий",
        customer_phone="+79991234567",
    )

    assert ok is False
    assert text == "Эта услуга сейчас недоступна."
    assert booking is None


@pytest.mark.asyncio
async def test_finalize_booking_rejects_slot_from_another_service(session):
    service_1 = await orm_add_service(session, title="Услуга 1", description=None, price=None)
    service_2 = await orm_add_service(session, title="Услуга 2", description=None, price=None)

    slot = await orm_add_timeslot(
        session,
        service_id=service_2.id,
        day=date.today() + timedelta(days=1),
        start_time=time(15, 0),
    )

    ok, text, booking = await user_booking._finalize_booking(
        session=session,
        tg_id=9002,
        service_id=service_1.id,
        day_iso=slot.day.isoformat(),
        slot_id=slot.id,
        customer_name="Юрий",
        customer_phone="+79991234567",
    )

    assert ok is False
    assert text == "Данные записи устарели. Выберите услугу заново."
    assert booking is None

@pytest.mark.asyncio
async def test_finalize_booking_returns_booking_with_service_and_slot(session):
    service = await orm_add_service(
        session,
        title="Тестовая услуга",
        description=None,
        price=None,
    )
    slot = await orm_add_timeslot(
        session,
        service_id=service.id,
        day=date.today() + timedelta(days=1),
        start_time=time(17, 30),
    )

    ok, text, booking = await user_booking._finalize_booking(
        session=session,
        tg_id=9003,
        service_id=service.id,
        day_iso=slot.day.isoformat(),
        slot_id=slot.id,
        customer_name="Юрий",
        customer_phone="+79991234567",
    )

    assert ok is True
    assert booking is not None
    assert booking.service is not None
    assert booking.slot is not None
    assert booking.service.title == "Тестовая услуга"
    assert booking.slot.id == slot.id

@pytest.mark.asyncio
async def test_finalize_booking_rejects_slot_past_by_business_time(session, monkeypatch):
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
        start_time=time(12, 0),
    )

    monkeypatch.setattr(
        user_booking,
        "booking_now",
        lambda: datetime(2026, 3, 20, 12, 1),
    )

    ok, text, booking = await user_booking._finalize_booking(
        session=session,
        tg_id=9004,
        service_id=service.id,
        day_iso=slot.day.isoformat(),
        slot_id=slot.id,
        customer_name="Юрий",
        customer_phone="+79991234567",
    )

    assert ok is False
    assert text == "Это время уже недоступно. Выберите другое."
    assert booking is None


@pytest.mark.asyncio
async def test_finalize_booking_allows_slot_future_by_business_time(session, monkeypatch):
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
        start_time=time(12, 0),
    )

    monkeypatch.setattr(
        user_booking,
        "booking_now",
        lambda: datetime(2026, 3, 20, 11, 59),
    )

    monkeypatch.setattr(
        orm_query,
        "booking_now",
        lambda: datetime(2026, 3, 20, 11, 59),
    )

    ok, text, booking = await user_booking._finalize_booking(
        session=session,
        tg_id=9005,
        service_id=service.id,
        day_iso=slot.day.isoformat(),
        slot_id=slot.id,
        customer_name="Юрий",
        customer_phone="+79991234567",
    )

    assert ok is True
    assert booking is not None
    assert booking.slot is not None
    assert booking.slot.id == slot.id

@pytest.mark.asyncio
async def test_due_booking_reminder_selects_confirmed_booking_within_60_minutes(session, monkeypatch):
    monkeypatch.setattr(
        orm_query,
        "booking_now",
        lambda: datetime(2026, 3, 20, 11, 0),
    )

    service = await orm_add_service(session, title="Тест", description=None, price=None)
    slot = await orm_add_timeslot(
        session,
        service_id=service.id,
        day=date(2026, 3, 20),
        start_time=time(11, 45),
    )

    booking = await orm_create_booking_for_slot(session, tg_id=101, slot_id=slot.id)
    assert booking is not None

    ok, reason, confirmed = await orm_admin_set_booking_status(
        session,
        booking_id=booking.id,
        target_status="confirmed",
    )
    assert ok is True
    assert reason == "updated"
    assert confirmed is not None

    due = await orm_get_due_booking_reminders(session, lead_minutes=60)
    assert [b.id for b in due] == [booking.id]


@pytest.mark.asyncio
async def test_due_booking_reminder_skips_booking_if_too_early(session, monkeypatch):
    monkeypatch.setattr(
        orm_query,
        "booking_now",
        lambda: datetime(2026, 3, 20, 11, 0),
    )

    service = await orm_add_service(session, title="Тест", description=None, price=None)
    slot = await orm_add_timeslot(
        session,
        service_id=service.id,
        day=date(2026, 3, 20),
        start_time=time(13, 30),
    )

    booking = await orm_create_booking_for_slot(session, tg_id=102, slot_id=slot.id)
    assert booking is not None

    ok, _, confirmed = await orm_admin_set_booking_status(
        session,
        booking_id=booking.id,
        target_status="confirmed",
    )
    assert ok is True
    assert confirmed is not None

    due = await orm_get_due_booking_reminders(session, lead_minutes=60)
    assert due == []


@pytest.mark.asyncio
async def test_due_booking_reminder_skips_already_sent(session, monkeypatch):
    fixed_now = datetime(2026, 3, 20, 11, 0)

    monkeypatch.setattr(orm_query, "booking_now", lambda: fixed_now)

    service = await orm_add_service(session, title="Тест", description=None, price=None)
    slot = await orm_add_timeslot(
        session,
        service_id=service.id,
        day=date(2026, 3, 20),
        start_time=time(11, 45),
    )

    booking = await orm_create_booking_for_slot(session, tg_id=103, slot_id=slot.id)
    assert booking is not None

    ok, _, confirmed = await orm_admin_set_booking_status(
        session,
        booking_id=booking.id,
        target_status="confirmed",
    )
    assert ok is True
    assert confirmed is not None

    first_mark = await orm_mark_booking_reminder_sent(session, booking_id=booking.id)
    second_mark = await orm_mark_booking_reminder_sent(session, booking_id=booking.id)

    assert first_mark is True
    assert second_mark is False

    due = await orm_get_due_booking_reminders(session, lead_minutes=60)
    assert due == []


@pytest.mark.asyncio
async def test_send_due_booking_reminders_marks_booking_on_success(session, monkeypatch):
    monkeypatch.setattr(
        orm_query,
        "booking_now",
        lambda: datetime(2026, 3, 20, 11, 0),
    )
    monkeypatch.setattr(reminders, "session_maker", lambda: _SessionCtx(session))

    service = await orm_add_service(session, title="Тест", description=None, price=None)
    slot = await orm_add_timeslot(
        session,
        service_id=service.id,
        day=date(2026, 3, 20),
        start_time=time(11, 45),
    )

    booking = await orm_create_booking_for_slot(session, tg_id=104, slot_id=slot.id)
    assert booking is not None

    ok, _, confirmed = await orm_admin_set_booking_status(
        session,
        booking_id=booking.id,
        target_status="confirmed",
    )
    assert ok is True
    assert confirmed is not None

    bot = SimpleNamespace(send_message=AsyncMock())

    await reminders.send_due_booking_reminders(cast(Bot, bot))

    bot.send_message.assert_awaited_once()

    booking_after = await orm_get_booking(session, booking.id)
    assert booking_after is not None
    assert booking_after.reminder_sent_at is not None


@pytest.mark.asyncio
async def test_send_due_booking_reminders_does_not_mark_when_send_fails(session, monkeypatch):
    monkeypatch.setattr(
        orm_query,
        "booking_now",
        lambda: datetime(2026, 3, 20, 11, 0),
    )
    monkeypatch.setattr(reminders, "session_maker", lambda: _SessionCtx(session))

    service = await orm_add_service(session, title="Тест", description=None, price=None)
    slot = await orm_add_timeslot(
        session,
        service_id=service.id,
        day=date(2026, 3, 20),
        start_time=time(11, 45),
    )

    booking = await orm_create_booking_for_slot(session, tg_id=105, slot_id=slot.id)
    assert booking is not None

    ok, _, confirmed = await orm_admin_set_booking_status(
        session,
        booking_id=booking.id,
        target_status="confirmed",
    )
    assert ok is True
    assert confirmed is not None

    bot = SimpleNamespace(send_message=AsyncMock(side_effect=RuntimeError("boom")))

    await reminders.send_due_booking_reminders(cast(Bot, bot))

    booking_after = await orm_get_booking(session, booking.id)
    assert booking_after is not None
    assert booking_after.reminder_sent_at is None

def test_build_booking_reminder_text_prefers_service_title_snapshot() -> None:
    booking = SimpleNamespace(
        service_title_snapshot="Старая услуга",
        service=SimpleNamespace(title="Новая услуга"),
        service_id=1,
        slot=SimpleNamespace(day=date(2026, 3, 20), start_time=time(12, 0)),
    )

    text = reminders.build_booking_reminder_text(cast(Booking, booking))

    assert "Старая услуга" in text
    assert "Новая услуга" not in text


def test_build_booking_reminder_text_falls_back_to_live_service_title_for_legacy_booking() -> None:
    booking = SimpleNamespace(
        service_title_snapshot=None,
        service=SimpleNamespace(title="Живая услуга"),
        service_id=1,
        slot=SimpleNamespace(day=date(2026, 3, 20), start_time=time(12, 0)),
    )

    text = reminders.build_booking_reminder_text(cast(Booking, booking))

    assert "Живая услуга" in text


def test_build_booking_reminder_text_escapes_service_title() -> None:
    booking = SimpleNamespace(
        service_title_snapshot="A & B <online>",
        service=SimpleNamespace(title="ignored"),
        service_id=1,
        slot=SimpleNamespace(day=date(2026, 3, 20), start_time=time(12, 0)),
    )

    text = reminders.build_booking_reminder_text(cast(Booking, booking))

    assert "A &amp; B &lt;online&gt;" in text