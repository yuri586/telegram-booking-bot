from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from database.models import Booking
from keyboards.inline import kb_admin_booking_card, kb_admin_bookings, kb_booking_my_card
from plugins.booking.handlers_admin_booking import _csv_safe_cell
from utils.paginator import Page


def _texts(kb: InlineKeyboardMarkup) -> list[str]:
    result: list[str] = []
    for row in kb.inline_keyboard:
        for button in row:
            if isinstance(button, InlineKeyboardButton):
                result.append(button.text)
    return result


def test_new_booking_card_shows_confirm_and_cancel_only():
    kb = kb_admin_booking_card(
        booking_id=1,
        status="new",
        payment_status="unpaid",
        can_done=False,
        p=1,
        mode=0,
        day_mode=2,
    )
    texts = _texts(kb)

    assert "✅ Подтвердить" in texts
    assert "❌ Отменить" in texts
    assert "🏁 Завершить" not in texts
    assert "💳 Отметить оплату" in texts


def test_confirmed_booking_card_shows_done_and_cancel():
    kb = kb_admin_booking_card(
        booking_id=1,
        status="confirmed",
        payment_status="unpaid",
        can_done=True,
        p=1,
        mode=1,
        day_mode=2,
    )
    texts = _texts(kb)

    assert "✅ Подтвердить" not in texts
    assert "🏁 Завершить" in texts
    assert "❌ Отменить" in texts
    assert "💳 Отметить оплату" in texts


def test_cancelled_booking_card_hides_payment_controls():
    kb = kb_admin_booking_card(
        booking_id=1,
        status="cancelled_by_admin",
        payment_status="paid",
        can_done=False,
        p=1,
        mode=3,
        day_mode=2,
    )
    texts = _texts(kb)

    assert "✅ Подтвердить" not in texts
    assert "🏁 Завершить" not in texts
    assert "❌ Отменить" not in texts
    assert "💳 Отметить оплату" not in texts
    assert "↩️ Снять отметку оплаты" not in texts

def test_confirmed_booking_card_hides_done_when_too_early():
    kb = kb_admin_booking_card(
        booking_id=1,
        status="confirmed",
        payment_status="unpaid",
        can_done=False,
        p=1,
        mode=1,
        day_mode=2,
    )
    texts = _texts(kb)

    assert "🏁 Завершить" not in texts
    assert "❌ Отменить" in texts

def test_confirmed_booking_card_shows_done_when_allowed():
    kb = kb_admin_booking_card(
        booking_id=1,
        status="confirmed",
        payment_status="unpaid",
        can_done=True,
        p=1,
        mode=1,
        day_mode=2,
    )
    texts = _texts(kb)

    assert "🏁 Завершить" in texts

def test_user_booking_card_hides_cancel_when_not_allowed():
    kb = kb_booking_my_card(
        booking_id=1,
        labels={"to_my_bookings": "📖 Мои записи", "home_main": "🏠 Главное меню"},
        can_cancel=False,
    )
    texts = _texts(kb)

    assert "❌ Отменить запись" not in texts


def test_admin_bookings_list_shows_export_button():
    page = Page[Booking](
        items=[],
        page=1,
        per_page=10,
        total=0,
        pages=1,
    )

    kb = kb_admin_bookings(
        page,
        mode=4,
        day_mode=2,
    )
    texts = _texts(kb)

    assert "⬇️ Выгрузить CSV" in texts




def test_csv_safe_cell_prefixes_formula_like_strings() -> None:
    assert _csv_safe_cell("=SUM(A1:A2)") == "'=SUM(A1:A2)"
    assert _csv_safe_cell("+123") == "'+123"
    assert _csv_safe_cell("-10") == "'-10"
    assert _csv_safe_cell("@evil") == "'@evil"


def test_csv_safe_cell_keeps_normal_values() -> None:
    assert _csv_safe_cell("Юрий") == "Юрий"
    assert _csv_safe_cell("123") == "123"
    assert _csv_safe_cell(123) == 123
    assert _csv_safe_cell(None) is None