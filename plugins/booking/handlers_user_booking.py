from __future__ import annotations

import logging
import re
from datetime import date
from decimal import Decimal
from html import escape

from aiogram import Bot, F, Router, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from common.booking_time import booking_now, booking_slot_dt, booking_timezone_label

#from common.booking_time import booking_now, booking_slot_dt, booking_time_note
# время показыватся текстом-строкой
from common.ui import ui_labels
from config import settings
from database.models import Booking
from database.orm_query import (
    ACTIVE_BOOKING_STATUSES,
    booking_has_started,
    orm_cancel_user_booking,
    orm_create_booking_for_slot,
    orm_get_booking,
    orm_get_or_create_user,
    orm_get_service,
    orm_get_services,
    orm_get_timeslot,
    orm_get_timeslots_by_day,
    orm_get_timeslots_days,
    orm_get_user_booking,
    orm_get_user_bookings,
    orm_set_user_phone,
)
from filters.chat_types import ChatTypeFilter
from keyboards.callbacks import BookingAdminCB, BookingCB
from keyboards.inline import (
    kb_booking_confirm,
    kb_booking_days,
    kb_booking_empty,
    kb_booking_my_card,
    kb_booking_my_list,
    kb_booking_resume,
    kb_booking_services,
    kb_booking_success,
    kb_booking_times,
)
from plugins.booking.statuses import booking_status_label

booking_user_router = Router()
booking_user_router.message.filter(ChatTypeFilter(["private"]))
logger = logging.getLogger(__name__)

PHONE_RE = re.compile(r"^[+]?\d{7,15}$")


class BookingContactFSM(StatesGroup):
    waiting_phone = State()


def _customer_name(from_user: types.User) -> str | None:
    name = " ".join(x for x in [from_user.first_name, from_user.last_name] if x).strip()
    if not name and from_user.username:
        name = f"@{from_user.username}"
    return (name[:150] if name else None)


def _normalize_phone(raw: str) -> str | None:
    value = re.sub(r"[^\d+]", "", (raw or "").strip())
    if value.count("+") > 1 or ("+" in value and not value.startswith("+")):
        return None
    digits = value[1:] if value.startswith("+") else value
    if not digits:
        return None
    normalized = f"+{digits}" if value.startswith("+") else digits
    if not PHONE_RE.match(normalized):
        return None
    return normalized[:30]


def _h(value: str | None, default: str = "—") -> str:
    text = (value or "").strip()
    return escape(text or default)

def _price_text(price: object) -> str | None:
    if price is None:
        return None

    try:
        value = Decimal(str(price)).quantize(Decimal("0.01"))
    except (ArithmeticError, ValueError):
        return None

    formatted = f"{value:.2f}".replace(".", ",")
    if formatted.endswith(",00"):
        formatted = formatted[:-3]

    return f"{formatted} ₽"

def _time_with_tz(time_text: str) -> str:
    if time_text == "—":
        return time_text
    return f"{time_text} ({booking_timezone_label()})"

def _phone_request_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Отправить телефон", request_contact=True)],
            [KeyboardButton(text="Отмена")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder="Отправьте номер телефона",
    )


async def _finalize_booking(
    session: AsyncSession,
    *,
    tg_id: int,
    service_id: int,
    day_iso: str,
    slot_id: int,
    customer_name: str | None,
    customer_phone: str | None,
) -> tuple[bool, str, Booking | None]:
    s = await orm_get_service(session, service_id)
    if not s or not s.is_active:
        return False, "Эта услуга сейчас недоступна.", None

    slot = await orm_get_timeslot(session, slot_id)
    if not slot:
        return False, "Выбранное время не найдено.", None

    if slot.service_id != s.id:
        return False, "Данные записи устарели. Выберите услугу заново.", None

    if not slot.is_active:
        return False, "Это время больше недоступно.", None

    try:
        d = date.fromisoformat(day_iso)
    except ValueError:
        return False, "Некорректная дата записи.", None

    if slot.service_id != s.id or slot.day != d:
        return False, "Данные записи устарели. Выберите услугу заново.", None

    if not slot.is_active:
        return False, "Это время больше недоступно.", None

    slot_dt = booking_slot_dt(slot.day, slot.start_time)
    if slot_dt <= booking_now():
        return False, "Это время уже недоступно. Выберите другое.", None

    booking = await orm_create_booking_for_slot(
        session,
        tg_id=tg_id,
        slot_id=slot.id,
        customer_name=customer_name,
        customer_phone=customer_phone,
    )
    if not booking:
        return False, "Это время уже занято 😕", None

    booking = await orm_get_booking(session, booking.id)
    if not booking:
        return False, "Не удалось прочитать запись после создания.", None

    data = _booking_summary(booking)
    
    price_line = f"Цена: {data['price_text']}\n" if data["price_text"] else ""

    return (
        True,
        (
            f"✅ Запись создана!\n\n"
            f"Услуга: {data['service_title']}\n"
            f"{price_line}"
            f"Дата: {data['day_text']}\n"
            f"Время: {data['time_text']} ({booking_timezone_label()})\n"
            f"Имя: {data['customer_name']}\n"
            f"Телефон: {data['customer_phone']}\n\n"
            f"Статус: {data['status_label']}\n\n"
            "Запись отправлена на подтверждение.\n"
            "Если планы изменятся, вы сможете отменить её в разделе «Мои записи»."
        ),
        booking,
    )


async def _edit_or_send(
    msg: types.Message,
    *,
    text: str,
    kb: types.InlineKeyboardMarkup | None,
) -> None:
    try:
        if msg.photo:
            await msg.edit_caption(caption=text, reply_markup=kb)
        else:
            await msg.edit_text(text=text, reply_markup=kb)
    except TelegramBadRequest:
        await msg.answer(text, reply_markup=kb)


async def _clear_inline_markup(msg: types.Message) -> None:
    try:
        await msg.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest:
        pass


def _booking_card_text(booking) -> str:
    data = _booking_summary(booking)
    price_line = f"Цена: {data['price_text']}\n" if data["price_text"] else ""

    return (
        f"🧾 Запись #{booking.id}\n\n"
        f"Услуга: {data['service_title']}\n"
        f"{price_line}"
        f"Дата: {data['day_text']}\n"
        f"Время: {data['time_text']} ({booking_timezone_label()})\n"
        f"Статус: {data['status_label']}"
    )


def _booking_dt_text(booking) -> tuple[str, str]:
    slot = booking.slot
    if not slot:
        return "—", "—"
    return (
        slot.day.strftime("%d.%m.%Y"),
        slot.start_time.strftime("%H:%M"),
    )

def _booking_summary(booking) -> dict[str, str]:
    service_title_raw = (
        getattr(booking, "service_title_snapshot", None)
        or (booking.service.title if booking.service else None)
        or f"Услуга #{booking.service_id}"
    )
    service_title = _h(service_title_raw)
    day_text, time_text = _booking_dt_text(booking)
    customer_name = _h(booking.customer_name)
    customer_phone = _h(booking.customer_phone)
    status_label = booking_status_label(booking.status)

    snapshot_price = getattr(booking, "service_price_snapshot", None)
    live_price = getattr(booking.service, "price", None) if booking.service is not None else None
    price_text = _price_text(snapshot_price if snapshot_price is not None else live_price)

    return {
        "service_title": service_title,
        "day_text": day_text,
        "time_text": time_text,
        "price_text": price_text or "",
        "customer_name": customer_name,
        "customer_phone": customer_phone,
        "status_label": status_label,
    }

def _admin_booking_notify_kb(booking_id: int) -> types.InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text=f"🧾 Открыть запись #{booking_id}",
        callback_data=BookingAdminCB(
            action="open",
            booking=booking_id,
            p=1,
            mode=4,
            day_mode=2,
        ).pack(),
    )
    return kb.as_markup()

async def _notify_admins_about_new_booking(bot: Bot, booking) -> None:
    if not settings.ADMIN_IDS:
        return

    data = _booking_summary(booking)

    time_text = _time_with_tz(data["time_text"])
    price_line = f"Цена: {data['price_text']}\n" if data["price_text"] else ""

    text = (
        "🆕 Новая запись\n\n"
        f"Запись: #{booking.id}\n"
        f"Услуга: {data['service_title']}\n"
        f"{price_line}"
        f"Дата: {data['day_text']}\n"
        f"Время: {time_text}\n\n"
        f"Клиент: {data['customer_name']}\n"
        f"Телефон: {data['customer_phone']}\n"
        f"TG ID: <code>{booking.tg_id}</code>"
    )

    for admin_id in settings.ADMIN_IDS:
        try:
            await bot.send_message(
                chat_id=admin_id,
                text=text,
                reply_markup=_admin_booking_notify_kb(booking.id),
            )
        except Exception:
            logger.exception(
                "Failed to notify admin %s about new booking #%s",
                admin_id,
                booking.id,
            )

async def _notify_admins_about_user_cancel(bot: Bot, booking) -> None:
    if not settings.ADMIN_IDS:
        return

    data = _booking_summary(booking)

    time_text = _time_with_tz(data["time_text"])
    price_line = f"Цена: {data['price_text']}\n" if data["price_text"] else ""

    text = (
        "❌ Клиент отменил запись\n\n"
        f"Запись: #{booking.id}\n"
        f"Услуга: {data['service_title']}\n"
        f"{price_line}"
        f"Дата: {data['day_text']}\n"
        f"Время: {time_text}\n\n"
        f"Клиент: {data['customer_name']}\n"
        f"Телефон: {data['customer_phone']}\n"
        f"TG ID: <code>{booking.tg_id}</code>"
    )

    for admin_id in settings.ADMIN_IDS:
        try:
            await bot.send_message(
                chat_id=admin_id,
                text=text,
                reply_markup=_admin_booking_notify_kb(booking.id),
            )
        except Exception:
            logger.exception(
                "Failed to notify admin %s about cancelled booking #%s",
                admin_id,
                booking.id,
            )

async def show_services_screen(msg: types.Message, session: AsyncSession) -> None:
    """Для inline-кнопок: редактируем текущий ‘экран’."""
    services = await orm_get_services(session, include_inactive=False)

    if not services:
        text = "Сейчас нет доступных услуг для записи."
        kb = None
    else:
        text = (
            "📅 Выберите услугу для записи\n"
            f"🕒 Все времена указаны по {booking_timezone_label()}"
        )
        labels = ui_labels()
        kb = kb_booking_services(services, labels)

    try:
        if msg.photo:
            await msg.edit_caption(caption=text, reply_markup=kb)
        else:
            await msg.edit_text(text=text, reply_markup=kb)
    except TelegramBadRequest:
        # если экран редактировать нельзя — шлём новым сообщением
        await msg.answer(text, reply_markup=kb)


@booking_user_router.message(Command("booking"))
async def booking_cmd(message: types.Message, session: AsyncSession):
    services = await orm_get_services(session, include_inactive=False)
    if not services:
        labels = ui_labels()
        await message.answer(
            "Сейчас нет доступных услуг для записи.",
            reply_markup=kb_booking_empty(labels),
        )
        return

    labels = ui_labels()
    await message.answer("📅 Выберите услугу для записи:", reply_markup=kb_booking_services(services, labels))


@booking_user_router.message(Command("mybookings"))
async def mybookings_cmd(message: types.Message, session: AsyncSession) -> None:
    from_user = message.from_user
    if not from_user:
        await message.answer("Не удалось определить пользователя.")
        return

    labels = ui_labels()

    bookings = await orm_get_user_bookings(session, tg_id=from_user.id, active_only=True)
    if not bookings:
        services = await orm_get_services(session, include_inactive=False)
        kb = kb_booking_services(services, labels) if services else kb_booking_empty(labels)
        await message.answer(
            "У вас пока нет активных записей.",
            reply_markup=kb,
        )
        return

    await message.answer("📖 Ваши активные записи:", reply_markup=kb_booking_my_list(bookings, labels))


@booking_user_router.message(F.text.casefold() == "букинг")
async def booking_text(message: types.Message, session: AsyncSession) -> None:
    services = await orm_get_services(session, include_inactive=False)
    if not services:
        labels = ui_labels()
        await message.answer(
            "Сейчас нет доступных услуг для записи.",
            reply_markup=kb_booking_empty(labels),
        )
        return

    labels = ui_labels()
    await message.answer("📅 Выберите услугу для записи:", reply_markup=kb_booking_services(services, labels))


@booking_user_router.callback_query(BookingCB.filter())
async def booking_callbacks(
    call: types.CallbackQuery,
    callback_data: BookingCB,
    session: AsyncSession,
    state: FSMContext,
    bot: Bot,
):
    msg = call.message
    if not isinstance(msg, types.Message):
        await call.answer()
        return

    action = callback_data.action

    labels = ui_labels()

    if not call.from_user:
        await call.answer("Не удалось определить пользователя.", show_alert=True)
        return

    current_state = await state.get_state()
    if current_state == BookingContactFSM.waiting_phone.state:
        if action in {"services", "my"}:
            await state.clear()
        else:
            await call.answer(
                "Сначала отправьте номер телефона или нажмите «Отмена».",
                show_alert=True,
            )
            return

    # 1) список услуг
    if action == "services":
        services = await orm_get_services(session, include_inactive=False)
        if not services:
            await _edit_or_send(
                msg,
                text="Сейчас нет доступных услуг для записи.",
                kb=kb_booking_empty(labels),
            )
            await call.answer()
            return
        await _edit_or_send(msg, text="📅 Выберите услугу для записи:", kb=kb_booking_services(services, labels))
        await call.answer()
        return

    # 1.1) мои записи
    if action == "my":
        bookings = await orm_get_user_bookings(session, tg_id=call.from_user.id, active_only=True)
        if not bookings:
            services = await orm_get_services(session, include_inactive=False)
            kb = kb_booking_services(services, labels) if services else kb_booking_empty(labels)
            await _edit_or_send(
                msg,
                text="У вас пока нет активных записей.",
                kb=kb,
            )
            await call.answer()
            return

        await _edit_or_send(msg, text="📖 Ваши активные записи:", kb=kb_booking_my_list(bookings, labels))
        await call.answer()
        return

    # 1.2) карточка одной записи
    if action == "my_open" and callback_data.booking:
        booking = await orm_get_user_booking(
            session,
            booking_id=callback_data.booking,
            tg_id=call.from_user.id,
        )
        if not booking:
            await call.answer("Запись не найдена.", show_alert=True)
            return
        can_cancel = booking.status in ACTIVE_BOOKING_STATUSES and not booking_has_started(booking)
        await _edit_or_send(msg, text=_booking_card_text(booking), kb = kb_booking_my_card(booking.id, labels, can_cancel=can_cancel))
        await call.answer()
        return

    # 1.3) отмена записи
    if action == "cancel" and callback_data.booking:
        booking = await orm_get_user_booking(
            session,
            booking_id=callback_data.booking,
            tg_id=call.from_user.id,
        )
        if not booking:
            await call.answer("Запись не найдена.", show_alert=True)
            return

        cancelled, reason = await orm_cancel_user_booking(
            session,
            booking_id=booking.id,
            tg_id=call.from_user.id,
        )
        if not cancelled:
            if reason == "too_late":
                await call.answer(
                    "Эту запись уже нельзя отменить: время встречи уже наступило.",
                    show_alert=True,
                )
            elif reason == "inactive":
                await call.answer("Запись уже неактивна.", show_alert=True)
            else:
                await call.answer("Не удалось отменить запись.", show_alert=True)
            return
        await _notify_admins_about_user_cancel(bot, booking)
        rest = await orm_get_user_bookings(session, tg_id=call.from_user.id, active_only=True)
        if rest:
            text = f"❌ Запись №{booking.id} отменена.\n\n📖 Оставшиеся активные записи:"
            kb = kb_booking_my_list(rest, labels)
        else:
            services = await orm_get_services(session, include_inactive=False)
            text = f"❌ Запись №{booking.id} отменена.\nАктивных записей больше нет."
            kb = kb_booking_services(services, labels) if services else kb_booking_empty(labels)

        await _edit_or_send(
            msg,
            text=text,
            kb=kb,
        )
        await call.answer("Запись отменена.")
        return

    # 2) список дат по услуге
    if action == "days" and callback_data.service:
        s = await orm_get_service(session, callback_data.service)
        if not s or not s.is_active:
            await call.answer("Услуга сейчас недоступна.", show_alert=True)
            return

        safe_title = _h(s.title)
        price_text = _price_text(s.price)
        price_line = f"Цена: {price_text}\n\n" if price_text else ""

        days = await orm_get_timeslots_days(session, service_id=s.id)
        if not days:
            services = await orm_get_services(session, include_inactive=False)
            kb = kb_booking_services(services, labels) if services else kb_booking_empty(labels)
            await _edit_or_send(
                msg,
                text=f"🧾 {safe_title}\n\n{price_line}Свободных дат пока нет.",
                kb=kb,
            )
            await call.answer()
            return

        await _edit_or_send(
            msg,
            text=(
                f"🧾 {safe_title}\n\n"
                f"{price_line}"
                "Выберите дату:\n"
                f"🕒 Все времена указаны по {booking_timezone_label()}"
            ),
            kb=kb_booking_days(s.id, days, labels),
        )
        await call.answer()
        return

    # 3) список времени по дате
    if action == "times" and callback_data.service and callback_data.day:
        s = await orm_get_service(session, callback_data.service)
        if not s or not s.is_active:
            await call.answer("Услуга сейчас недоступна.", show_alert=True)
            return

        safe_title = _h(s.title)
        price_text = _price_text(s.price)
        price_line = f"Цена: {price_text}\n\n" if price_text else ""

        try:
            d = date.fromisoformat(callback_data.day)
        except ValueError:
            await call.answer("Некорректная дата.", show_alert=True)
            return

        slots = await orm_get_timeslots_by_day(session, service_id=s.id, day=d)
        if not slots:
            days = await orm_get_timeslots_days(session, service_id=s.id)
            await _edit_or_send(
                msg,
                text=(
                    f"🧾 {safe_title}\n\n"
                    f"{price_line}"
                    f"На {d.strftime('%d.%m.%Y')} сейчас нет свободного времени."
                ),
                kb=kb_booking_days(s.id, days, labels),
            )
            await call.answer()
            return

        await _edit_or_send(
            msg,
            text=(
                f"🧾 {safe_title}\n\n"
                f"{price_line}"
                f"Дата: {d.strftime('%d.%m.%Y')}\n"
                "Выберите время:\n"
                f"🕒 Все времена указаны по {booking_timezone_label()}"
            ),
            kb=kb_booking_times(s.id, callback_data.day, slots, labels),
        )
        await call.answer()
        return

    # 4) confirm: показываем экран подтверждения
    if action == "confirm" and callback_data.service and callback_data.day and callback_data.slot:
        s = await orm_get_service(session, callback_data.service)
        slot = await orm_get_timeslot(session, callback_data.slot)
        if not s or not slot:
            await call.answer("Данные записи устарели.", show_alert=True)
            return

        safe_title = _h(s.title)
        price_text = _price_text(s.price)
        price_line = f"Цена: {price_text}\n\n" if price_text else ""

        try:
            d = date.fromisoformat(callback_data.day)
        except ValueError:
            await call.answer("Некорректная дата.", show_alert=True)
            return

        if slot.service_id != s.id or slot.day != d:
            await call.answer("Данные записи устарели.", show_alert=True)
            return
        
        slot_dt = booking_slot_dt(slot.day, slot.start_time)
        if slot_dt <= booking_now():
            await call.answer("Это время уже недоступно.", show_alert=True)
            return
        
        if slot.is_booked or (not slot.is_active):
            await call.answer("Это время уже занято.", show_alert=True)
            return

        await _edit_or_send(
            msg,
            text=(
                f"Подтвердите запись.\n\n"
                f"Услуга: {safe_title}\n"
                f"{price_line}"
                f"Дата: {d.strftime('%d.%m.%Y')}\n"
                f"Время: {slot.start_time.strftime('%H:%M')} ({booking_timezone_label()})"
            ),
            kb=kb_booking_confirm(s.id, callback_data.day, slot.id, labels),
        )
        await call.answer()
        return

    # 5) commit: финально создаём запись
    if action == "commit" and callback_data.service and callback_data.day and callback_data.slot:
        user = await orm_get_or_create_user(
            session,
            tg_id=call.from_user.id,
            first_name=call.from_user.first_name,
            last_name=call.from_user.last_name,
        )
        name = _customer_name(call.from_user)
        phone = _normalize_phone(user.phone or "")

        if not phone:
            await state.set_state(BookingContactFSM.waiting_phone)
            await state.update_data(
                service_id=callback_data.service,
                day=callback_data.day,
                slot_id=callback_data.slot,
                customer_name=name,
            )

            await _clear_inline_markup(msg)

            await msg.answer(
                "Чтобы завершить запись, отправьте номер телефона.\n"
                "Можно нажать кнопку ниже или ввести номер вручную.",
                reply_markup=_phone_request_kb(),
            )
            await call.answer()
            return

        ok, text, booking = await _finalize_booking(
        session,
        tg_id=call.from_user.id,
        service_id=callback_data.service,
        day_iso=callback_data.day,
        slot_id=callback_data.slot,
        customer_name=name,
        customer_phone=phone,
        )
        if not ok:
            await call.answer(text, show_alert=True)
            return

        await state.clear()

        if booking is not None:
            await _notify_admins_about_new_booking(bot, booking)

        success_kb = kb_booking_success(labels)

        await _edit_or_send(
            msg,
            text=text,
            kb=success_kb,
        )
        await call.answer()
        return

    await call.answer("Неизвестное действие", show_alert=True)

async def _finish_booking_with_phone(
    *,
    message: types.Message,
    state: FSMContext,
    session: AsyncSession,
    phone: str,
    bot: Bot,
) -> None:
    from_user = message.from_user
    if not from_user:
        await message.answer(
            "Не удалось определить пользователя.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    data = await state.get_data()
    service_id = int(data.get("service_id") or 0)
    day_iso = str(data.get("day") or "")
    slot_id = int(data.get("slot_id") or 0)
    name = str(data.get("customer_name") or "") or _customer_name(from_user)

    labels = ui_labels()
    success_kb = kb_booking_success(labels)
    resume_kb = kb_booking_resume(labels)

    if not service_id or not day_iso or not slot_id:
        await state.clear()
        await message.answer(
            "Сессия записи устарела.",
            reply_markup=ReplyKeyboardRemove(),
        )
        await message.answer(
            "Что хотите сделать дальше?",
            reply_markup=resume_kb,
        )
        return

    await orm_set_user_phone(session, tg_id=from_user.id, phone=phone)

    ok, text, booking = await _finalize_booking(
        session,
        tg_id=from_user.id,
        service_id=service_id,
        day_iso=day_iso,
        slot_id=slot_id,
        customer_name=name,
        customer_phone=phone,
    )

    await state.clear()

    if ok and booking is not None:
        await _notify_admins_about_new_booking(bot, booking)

    if not ok:
        await message.answer(
            text,
            reply_markup=ReplyKeyboardRemove(),
        )
        await message.answer(
            "Выберите другое время или вернитесь на главную.",
            reply_markup=resume_kb,
        )
        return

    await message.answer(
        text,
        reply_markup=ReplyKeyboardRemove(),
    )
    await message.answer(
        "Что хотите сделать дальше?",
        reply_markup=success_kb,
    )


@booking_user_router.message(BookingContactFSM.waiting_phone, F.contact)
async def booking_contact_phone(
    message: types.Message,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
) -> None:
    from_user = message.from_user
    if not from_user:
        await message.answer("Не удалось определить пользователя.", reply_markup=ReplyKeyboardRemove())
        return

    contact = message.contact
    if not contact:
        await message.answer("Не удалось прочитать контакт. Попробуйте ещё раз.")
        return

    if contact.user_id and contact.user_id != from_user.id:
        await message.answer("Отправьте, пожалуйста, свой номер телефона.")
        return

    phone = _normalize_phone(contact.phone_number or "")
    if not phone:
        await message.answer("Не удалось распознать номер. Введите его вручную в формате +79991234567.")
        return

    await _finish_booking_with_phone(
        message=message,
        state=state,
        session=session,
        phone=phone,
        bot=bot,
    )


@booking_user_router.message(BookingContactFSM.waiting_phone, F.text.casefold() == "отмена")
async def booking_contact_cancel(message: types.Message, state: FSMContext) -> None:
    await state.clear()

    labels = ui_labels()
    resume_kb = kb_booking_resume(labels)

    await message.answer(
        "Хорошо, запись не завершена.",
        reply_markup=ReplyKeyboardRemove(),
    )
    await message.answer(
        "Что хотите сделать дальше?",
        reply_markup=resume_kb,
    )


@booking_user_router.message(BookingContactFSM.waiting_phone, F.text)
async def booking_contact_phone_text(
    message: types.Message,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
) -> None:
    from_user = message.from_user
    if not from_user:
        await message.answer("Не удалось определить пользователя.", reply_markup=ReplyKeyboardRemove())
        return

    phone = _normalize_phone(message.text or "")
    if not phone:
        await message.answer(
            "Некорректный номер.\n"
            "Введите номер в формате +79991234567 или нажмите кнопку «Отправить телефон».",
        )
        return

    await _finish_booking_with_phone(
        message=message,
        state=state,
        session=session,
        phone=phone,
        bot=bot,
    )


