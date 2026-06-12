from __future__ import annotations

import csv
import logging
from html import escape
from io import StringIO

from aiogram import Bot, F, Router, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile
from sqlalchemy.ext.asyncio import AsyncSession

from common.booking_time import booking_timezone_label
from database.orm_query import (
    booking_has_started,
    orm_admin_set_booking_status,
    orm_get_active_booking_broadcast_tg_ids,
    orm_get_booking,
    orm_get_booking_reminder_lead_minutes,
    orm_get_bookings_for_export,
    orm_get_bookings_page,
    orm_set_booking_payment_status,
    orm_set_booking_reminder_lead_minutes,
)
from filters.chat_types import ChatTypeFilter, IsAdmin
from keyboards.admin_reply import ADMIN_KB
from keyboards.callbacks import BookingAdminCB
from keyboards.inline import (
    kb_admin_booking_card,
    kb_admin_bookings,
    kb_admin_broadcast_confirm,
    kb_admin_reminder_settings,
    kb_booking_payment_notice,
)
from keyboards.reply import get_keyboard
from plugins.booking.statuses import (
    booking_status_label,
    payment_status_text,
)

logger = logging.getLogger(__name__)

bookings_admin_router = Router()

FSM_FORM_KB = get_keyboard(
    "Назад",
    "Отмена",
    placeholder="Можно вернуться или отменить",
    sizes=(2,),
)


class BroadcastFSM(StatesGroup):
    waiting_text = State()
    waiting_confirm = State()


bookings_admin_router.message.filter(ChatTypeFilter(["private"]), IsAdmin())
bookings_admin_router.callback_query.filter(IsAdmin())


def _h(value: str | None, default: str = "—") -> str:
    text = (value or "").strip()
    return escape(text or default)


def _payment_rule_hint(booking) -> str:
    payment_status = getattr(booking, "payment_status", "unpaid")
    status = booking.status

    if status in {"cancelled_by_admin", "cancelled_by_user"}:
        if payment_status == "paid":
            return "ℹ️ Примечание: оплата была отмечена до отмены записи."
        return "ℹ️ Примечание: для отменённой записи оплату менять нельзя."

    if payment_status == "paid":
        return "ℹ️ Примечание: оплата уже отмечена."

    return "ℹ️ Примечание: при отметке оплаты клиент получит уведомление."

def _time_with_tz(time_text: str) -> str:
    if time_text == "—":
        return time_text
    return f"{time_text} ({booking_timezone_label()})"

def _booking_text(booking) -> str:
    service_title = _h(
        getattr(booking, "service_title_snapshot", None)
        or (booking.service.title if booking.service else None)
        or f"Услуга #{booking.service_id}"
    )
    if booking.slot:
        day = booking.slot.day.strftime("%d.%m.%Y")
        tm = _time_with_tz(booking.slot.start_time.strftime("%H:%M"))
    else:
        day = "—"
        tm = "—"

    customer_name = _h(booking.customer_name)
    customer_phone = _h(booking.customer_phone)
    payment_text = payment_status_text(getattr(booking, "payment_status", "unpaid"))
    payment_hint = _payment_rule_hint(booking)

    return (
        f"<b>Запись #{booking.id}</b>\n\n"
        f"Статус: {booking_status_label(booking.status)}\n"
        f"Оплата: {payment_text}\n"
        f"Примечание: {payment_hint.removeprefix('ℹ️ ').strip()}\n\n"
        f"Услуга: {service_title}\n"
        f"Дата: {day}\n"
        f"Время: {tm}\n\n"
        f"Клиент TG ID: <code>{booking.tg_id}</code>\n"
        f"Имя: {customer_name}\n"
        f"Телефон: {customer_phone}"
    )

def _csv_safe_cell(value: object) -> object:
    if not isinstance(value, str):
        return value

    if value.startswith(("=", "+", "-", "@")):
        return "'" + value

    return value

def _booking_export_filename(*, mode: int, day_mode: int) -> str:
    mode_part = {
        0: "new",
        1: "confirmed",
        2: "done",
        3: "cancelled",
        4: "all",
    }.get(mode, "all")

    day_part = {
        0: "upcoming",
        1: "past",
        2: "all_dates",
    }.get(day_mode, "all_dates")

    return f"bookings_{mode_part}_{day_part}.csv"


def _booking_export_bytes(bookings: list) -> bytes:
    buffer = StringIO(newline="")
    writer = csv.writer(buffer)
    tz_label = booking_timezone_label()

    writer.writerow(
        [
            "booking_id",
            "status",
            "payment_status",
            "service_title",
            "slot_day",
            f"slot_time ({tz_label})",
            "tg_id",
            "customer_name",
            "customer_phone",
        ]
    )

    for booking in bookings:
        row = [
            booking.id,
            booking.status,
            getattr(booking, "payment_status", "unpaid"),
            getattr(booking, "service_title_snapshot", None)
            or (booking.service.title if booking.service else ""),
            booking.slot.day.isoformat() if booking.slot else "",
            booking.slot.start_time.strftime("%H:%M") if booking.slot else "",
            booking.tg_id,
            booking.customer_name or "",
            booking.customer_phone or "",
        ]
        writer.writerow([_csv_safe_cell(value) for value in row])

    return buffer.getvalue().encode("utf-8-sig")


def _broadcast_preview_text(text: str, recipients_count: int) -> str:
    safe_text = escape(text.strip())
    return (
        "📣 Рассылка активным клиентам\n\n"
        f"Получателей сейчас: {recipients_count}\n\n"
        "Предпросмотр сообщения:\n\n"
        f"{safe_text}\n\n"
        "Отправить?"
    )

def _reminder_lead_label(minutes: int) -> str:
    return {
        60: "1 час",
        180: "3 часа",
        1440: "24 часа",
        2880: "48 часов",
    }.get(minutes, f"{minutes} мин")


async def _show_reminder_settings(
    msg: types.Message,
    *,
    session: AsyncSession,
    mode: int,
    day_mode: int,
    page_num: int,
    notice: str | None = None,
) -> None:
    current_minutes = await orm_get_booking_reminder_lead_minutes(session)
    text = (
        "⏰ Напоминание клиенту\n\n"
        f"Сейчас: за {_reminder_lead_label(current_minutes)} до встречи.\n\n"
        "Бот заранее напомнит клиенту о записи.\n"
        "Выберите, за сколько отправить напоминание:"
    )
    if notice:
        text = f"{notice}\n\n{text}"

    await _edit_or_send(
        msg,
        text=text,
        kb=kb_admin_reminder_settings(
            p=page_num,
            mode=mode,
            day_mode=day_mode,
            current_minutes=current_minutes,
        ),
    )

async def _send_booking_broadcast(
    bot: Bot,
    tg_ids: list[int],
    text: str,
) -> tuple[int, int]:
    safe_text = escape((text or "").strip())

    sent = 0
    failed = 0

    for tg_id in tg_ids:
        try:
            await bot.send_message(
                chat_id=tg_id,
                text=safe_text,
            )
            sent += 1
        except Exception as e:
            failed += 1
            logger.warning("Broadcast send failed for tg_id=%s: %s", tg_id, e)

    return sent, failed



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


async def _show_bookings_list(
    msg: types.Message,
    *,
    session: AsyncSession,
    mode: int,
    day_mode: int,
    page_num: int,
    notice: str | None = None,
) -> None:
    page = await orm_get_bookings_page(
        session,
        page=page_num,
        per_page=10,
        mode=mode,
        day_mode=day_mode,
    )
    text = f"🗂️ Записи клиентов\nСтраница {page.page}/{page.pages}"
    if notice:
        text = f"{notice}\n\n{text}"
    await _edit_or_send(msg, text=text, kb=kb_admin_bookings(page, mode=mode, day_mode=day_mode))


async def _show_booking_card(
    msg: types.Message,
    *,
    session: AsyncSession,
    booking_id: int,
    p: int,
    mode: int,
    day_mode: int,
) -> bool:
    booking = await orm_get_booking(session, booking_id)
    if not booking:
        return False
    can_done = booking.status == "confirmed" and booking_has_started(booking)
    await _edit_or_send(
        msg,
        text=_booking_text(booking),
        kb=kb_admin_booking_card(
            booking.id,
            status=booking.status,
            payment_status=getattr(booking, "payment_status", "unpaid"),
            can_done=can_done,
            p=p,
            mode=mode,
            day_mode=day_mode,
        )
    )
    return True


async def _notify_user_about_status_change(bot: Bot, booking) -> None:
    if booking.slot:
        day = booking.slot.day.strftime("%d.%m.%Y")
        tm = booking.slot.start_time.strftime("%H:%M")
    else:
        day = "—"
        tm = "—"

    service_title = _h(
        getattr(booking, "service_title_snapshot", None)
        or (booking.service.title if booking.service else None)
        or f"Услуга #{booking.service_id}"
    )
    payment_text = payment_status_text(getattr(booking, "payment_status", "unpaid"))

    text = (
        "ℹ️ Статус вашей записи изменён администратором.\n\n"
        f"Запись: №{booking.id}\n"
        f"Услуга: {service_title}\n"
        f"Дата: {day}\n"
        f"Время: {_time_with_tz(tm)}\n"
        f"Статус: {booking_status_label(booking.status)}\n"
        f"Оплата: {payment_text}"
    )
    try:
        await bot.send_message(chat_id=booking.tg_id, text=text)
    except Exception as e:
        logger.warning("User notify failed for booking #%s: %s", booking.id, e)

async def _notify_user_about_payment_marked(bot: Bot, booking) -> None:
    if booking.slot:
        day = booking.slot.day.strftime("%d.%m.%Y")
        tm = booking.slot.start_time.strftime("%H:%M")
    else:
        day = "—"
        tm = "—"

    service_title = _h(
        getattr(booking, "service_title_snapshot", None)
        or (booking.service.title if booking.service else None)
        or f"Услуга #{booking.service_id}"
    )

    text = (
        "💳 Оплата по вашей записи обновлена.\n\n"
        f"Запись: №{booking.id}\n"
        f"Услуга: {service_title}\n"
        f"Дата: {day}\n"
        f"Время: {_time_with_tz(tm)}\n"
        f"Статус записи: {booking_status_label(booking.status)}\n"
        f"Оплата: {payment_status_text(getattr(booking, 'payment_status', 'unpaid'))}"
    )

    try:
        await bot.send_message(
            chat_id=booking.tg_id,
            text=text,
            reply_markup=kb_booking_payment_notice(),
        )
    except Exception as e:
        logger.warning("Payment notify failed for booking #%s: %s", booking.id, e)

@bookings_admin_router.message(Command("bookings"))
@bookings_admin_router.message(F.text == "Записи")
async def bookings_entry(
    message: types.Message,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    await state.clear()
    await _show_bookings_list(message, session=session, mode=0, day_mode=2, page_num=1)


@bookings_admin_router.callback_query(BookingAdminCB.filter())
async def bookings_callbacks(
    call: types.CallbackQuery,
    callback_data: BookingAdminCB,
    session: AsyncSession,
    bot: Bot,
    state: FSMContext,
):
    msg = call.message
    if not isinstance(msg, types.Message):
        await call.answer()
        return

    action = callback_data.action
    mode = int(callback_data.mode or 0)
    day_mode = int(callback_data.day_mode)
    page_num = int(callback_data.p or 1)
    if action not in {"broadcast", "broadcast_send", "broadcast_cancel"}:
        await state.clear()

    if action == "home":
        await call.answer()
        await msg.answer("Админ-панель:", reply_markup=ADMIN_KB)
        return

    if action == "mode":
        new_mode = (mode + 1) % 5
        await call.answer()
        await _show_bookings_list(msg, session=session, mode=new_mode, day_mode=day_mode, page_num=1)
        return

    if action == "day_mode":
        new_day_mode = (day_mode + 1) % 3
        await call.answer()
        await _show_bookings_list(msg, session=session, mode=mode, day_mode=new_day_mode, page_num=1)
        return

    if action == "list":
        await call.answer()
        await _show_bookings_list(msg, session=session, mode=mode, day_mode=day_mode, page_num=page_num)
        return

    if action == "export_csv":
        bookings = await orm_get_bookings_for_export(
            session,
            mode=mode,
            day_mode=day_mode,
        )

        file = BufferedInputFile(
            _booking_export_bytes(bookings),
            filename=_booking_export_filename(mode=mode, day_mode=day_mode),
        )

        await msg.answer_document(
            document=file,
            caption=(
                f"Выгрузка записей: {len(bookings)} шт. "
                f"Все времена указаны по {booking_timezone_label()}."
            ),
        )
        await call.answer("CSV выгружен ✅")
        return

    if action == "broadcast":
        await state.clear()
        await state.update_data(
            mode=mode,
            day_mode=day_mode,
            p=page_num,
        )
        await state.set_state(BroadcastFSM.waiting_text)

        await call.answer()
        await msg.answer(
            "📣 Рассылка активным клиентам\n\n"
            "Введите текст одним сообщением.\n"
            "Кнопки снизу:\n"
            "• Назад — вернуться к списку записей\n"
            "• Отмена — выйти из режима рассылки",
            reply_markup=FSM_FORM_KB,
        )
        return

    if action == "broadcast_send":
        current_state = await state.get_state()
        if current_state != BroadcastFSM.waiting_confirm.state:
            await call.answer("Сессия рассылки устарела.", show_alert=True)
            return

        data = await state.get_data()
        text = str(data.get("broadcast_text") or "").strip()
        if not text:
            await state.clear()
            await call.answer("Текст рассылки не найден.", show_alert=True)
            await msg.answer("Админ-панель:", reply_markup=ADMIN_KB)
            await _show_bookings_list(
                msg,
                session=session,
                mode=mode,
                day_mode=day_mode,
                page_num=page_num,
                notice="Рассылка отменена.",
            )
            return

        tg_ids = await orm_get_active_booking_broadcast_tg_ids(session)

        await call.answer("Запускаю рассылку...")

        sent, failed = await _send_booking_broadcast(bot, tg_ids, text)

        await state.clear()

        await msg.answer("Админ-панель:", reply_markup=ADMIN_KB)
        await _show_bookings_list(
            msg,
            session=session,
            mode=mode,
            day_mode=day_mode,
            page_num=page_num,
            notice=(
                "📣 Рассылка завершена.\n\n"
                f"Получателей: {len(tg_ids)}\n"
                f"Успешно: {sent}\n"
                f"Ошибок: {failed}"
            ),
        )
        return

    if action == "broadcast_cancel":
        await state.clear()
        await call.answer("Рассылка отменена.")
        await msg.answer("Админ-панель:", reply_markup=ADMIN_KB)
        await _show_bookings_list(
            msg,
            session=session,
            mode=mode,
            day_mode=day_mode,
            page_num=page_num,
            notice="Рассылка отменена.",
        )
        return

    if action == "reminder_settings":
        await call.answer()
        await _show_reminder_settings(
            msg,
            session=session,
            mode=mode,
            day_mode=day_mode,
            page_num=page_num,
        )
        return

    if action == "reminder_set":
        if callback_data.value is None:
            await call.answer("Не выбрано значение.", show_alert=True)
            return

        ok = await orm_set_booking_reminder_lead_minutes(session, int(callback_data.value))
        if not ok:
            await call.answer("Недопустимое значение.", show_alert=True)
            return

        await call.answer("Настройка сохранена ✅")
        await _show_reminder_settings(
            msg,
            session=session,
            mode=mode,
            day_mode=day_mode,
            page_num=page_num,
            notice="Настройка напоминания обновлена.",
        )
        return

    if action == "open":
        await state.clear()
        if not callback_data.booking:
            await call.answer("Не найден идентификатор записи.", show_alert=True)
            return
        ok = await _show_booking_card(
            msg,
            session=session,
            booking_id=callback_data.booking,
            p=page_num,
            mode=mode,
            day_mode=day_mode,
        )
        if not ok:
            await call.answer("Запись не найдена.", show_alert=True)
            return
        await call.answer()
        return

    if action in {"confirm", "cancel", "done"}:
        if not callback_data.booking:
            await call.answer("Не найден идентификатор записи.", show_alert=True)
            return

        target_status = {
            "confirm": "confirmed",
            "cancel": "cancelled_by_admin",
            "done": "done",
        }[action]

        ok, reason, booking = await orm_admin_set_booking_status(
            session,
            booking_id=callback_data.booking,
            target_status=target_status,
        )
        if not ok:
            reason_text = {
                "not_found": "Запись не найдена.",
                "bad_transition": "Это действие недоступно для текущего статуса.",
                "too_early": "Нельзя завершить запись раньше времени встречи.",
                "missing_slot": "У записи нет времени слота.",
                "conflict": "Запись уже изменилась, обновите список.",
                "unknown_target": "Неизвестное действие.",
            }.get(reason, "Не удалось изменить статус.")
            await call.answer(reason_text, show_alert=True)
            return

        updated = booking if reason in {"updated", "noop"} else await orm_get_booking(session, callback_data.booking)
        if not updated:
            await call.answer("Запись не найдена.", show_alert=True)
            return

        if reason == "updated":
            await call.answer("Статус обновлён.")
            await _notify_user_about_status_change(bot, updated)
        else:
            await call.answer("Без изменений.")

        can_done = updated.status == "confirmed" and booking_has_started(updated)

        await _edit_or_send(
            msg,
            text=_booking_text(updated),
            kb=kb_admin_booking_card(
                updated.id,
                status=updated.status,
                payment_status=getattr(updated, "payment_status", "unpaid"),
                can_done=can_done,
                p=page_num,
                mode=mode,
                day_mode=day_mode,
            ),
        )
        return
    if action in {"mark_paid", "mark_unpaid"}:
        if not callback_data.booking:
            await call.answer("Не найдена запись", show_alert=True)
            return

        target_payment_status = "paid" if action == "mark_paid" else "unpaid"
        current = await orm_get_booking(session, callback_data.booking)
        if not current:
            await call.answer("Запись не найдена", show_alert=True)
            return

        if current.status in {"cancelled_by_admin", "cancelled_by_user"}:
            await call.answer("Для отменённой записи оплату менять нельзя", show_alert=True)
            return

        ok = await orm_set_booking_payment_status(
            session,
            booking_id=callback_data.booking,
            payment_status=target_payment_status,
        )
        if not ok:
            await call.answer("Не удалось изменить статус оплаты", show_alert=True)
            return

        updated = await orm_get_booking(session, callback_data.booking)
        if not updated:
            await call.answer("Запись не найдена", show_alert=True)
            return

        await call.answer("Статус оплаты обновлён ✅")

        if target_payment_status == "paid":
            await _notify_user_about_payment_marked(bot, updated)

        can_done = updated.status == "confirmed" and booking_has_started(updated)

        await _edit_or_send(
            msg,
            text=_booking_text(updated),
            kb=kb_admin_booking_card(
                updated.id,
                status=updated.status,
                payment_status=getattr(updated, "payment_status", "unpaid"),
                can_done=can_done,
                p=page_num,
                mode=mode,
                day_mode=day_mode,
            ),
        )
        return
    await call.answer("Неизвестное действие", show_alert=True)

@bookings_admin_router.message(
    StateFilter(BroadcastFSM.waiting_text),
    F.text.casefold() == "назад",
)
async def booking_broadcast_back(
    message: types.Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    data = await state.get_data()
    mode = int(data.get("mode", 0) or 0)
    day_mode = int(data.get("day_mode", 2) or 2)
    page_num = int(data.get("p", 1) or 1)

    await state.clear()
    await message.answer("Ок.", reply_markup=types.ReplyKeyboardRemove())
    await _show_bookings_list(
        message,
        session=session,
        mode=mode,
        day_mode=day_mode,
        page_num=page_num,
        notice="Рассылка отменена.",
    )

@bookings_admin_router.message(
    StateFilter(BroadcastFSM.waiting_text, BroadcastFSM.waiting_confirm),
    Command("отмена"),
)
@bookings_admin_router.message(
    StateFilter(BroadcastFSM.waiting_text, BroadcastFSM.waiting_confirm),
    F.text.casefold() == "отмена",
)
async def booking_broadcast_cancel_callback(
    message: types.Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    data = await state.get_data()
    mode = int(data.get("mode", 0) or 0)
    day_mode = int(data.get("day_mode", 2) or 2)
    page_num = int(data.get("p", 1) or 1)

    await state.clear()

    await message.answer("Ок, рассылка отменена.", reply_markup=ADMIN_KB)
    await _show_bookings_list(
        message,
        session=session,
        mode=mode,
        day_mode=day_mode,
        page_num=page_num,
        notice="Рассылка отменена.",
    )

@bookings_admin_router.message(BroadcastFSM.waiting_text, F.text)
async def booking_broadcast_text_step(
    message: types.Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    text = (message.text or "").strip()
    if not text:
        await message.answer("Текст не может быть пустым.", reply_markup=FSM_FORM_KB)
        return

    if len(text) > 3500:
        await message.answer("Текст слишком длинный. Сделай до 3500 символов.", reply_markup=FSM_FORM_KB)
        return

    tg_ids = await orm_get_active_booking_broadcast_tg_ids(session)
    data = await state.get_data()
    mode = int(data.get("mode", 0) or 0)
    day_mode = int(data.get("day_mode", 2) or 2)
    page_num = int(data.get("p", 1) or 1)

    if not tg_ids:
        await state.clear()
        await message.answer("Сейчас нет активных клиентов для рассылки.", reply_markup=ADMIN_KB)
        await _show_bookings_list(
            message,
            session=session,
            mode=mode,
            day_mode=day_mode,
            page_num=page_num,
            notice="Сейчас нет активных клиентов для рассылки.",
        )
        return

    await state.update_data(broadcast_text=text)
    await state.set_state(BroadcastFSM.waiting_confirm)

    await message.answer(
        "Проверьте сообщение ниже.",
        reply_markup=types.ReplyKeyboardRemove(),
    )

    await message.answer(
        _broadcast_preview_text(text, len(tg_ids)),
        reply_markup=kb_admin_broadcast_confirm(
            p=page_num,
            mode=mode,
            day_mode=day_mode,
        ),
    )

@bookings_admin_router.message(BroadcastFSM.waiting_text)
async def booking_broadcast_waiting_text_invalid(
    message: types.Message,
) -> None:
    await message.answer(
        "Отправьте текст одним сообщением.\n"
        "Или используйте кнопки «Назад» / «Отмена».",
        reply_markup=FSM_FORM_KB,
    )

@bookings_admin_router.message(BroadcastFSM.waiting_confirm, F.text)
async def booking_broadcast_waiting_confirm(
    message: types.Message,
) -> None:
    await message.answer("Нажмите «✅ Отправить» или «❌ Отмена» под предпросмотром.")

@bookings_admin_router.message(BroadcastFSM.waiting_confirm)
async def booking_broadcast_waiting_confirm_invalid(
    message: types.Message,
) -> None:
    await message.answer("Нажмите «✅ Отправить» или «❌ Отмена» под предпросмотром.")