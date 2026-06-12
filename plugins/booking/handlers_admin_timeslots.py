# plugins/booking/handlers_admin_timeslots.py
from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from html import escape

from aiogram import Bot, F, Router, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession

from common.booking_time import booking_now, booking_slot_dt, booking_timezone_label, booking_today
from database.orm_query import (
    orm_add_timeslot,
    orm_add_timeslots_bulk,
    orm_delete_timeslot,
    orm_get_active_booking_tg_ids_by_slot,
    orm_get_service,
    orm_get_services,
    orm_get_timeslot,
    orm_get_timeslots_for_day,
    orm_get_timeslots_page,
    orm_purge_slot_with_bookings,
    orm_release_slot_and_cancel_bookings,
    orm_slot_has_bookings,
    orm_toggle_timeslot_active,
    orm_update_timeslot_datetime,
)
from filters.chat_types import ChatTypeFilter, IsAdmin
from keyboards.admin_reply import ADMIN_KB
from keyboards.inline import (
    SlotAdminCB,
    kb_admin_services_for_slots,
    kb_admin_timeslot_card,
    kb_admin_timeslot_purge_confirm,
    kb_admin_timeslots,
)
from keyboards.reply import get_keyboard

logger = logging.getLogger(__name__)

timeslots_admin_router = Router()
timeslots_admin_router.message.filter(ChatTypeFilter(["private"]), IsAdmin())
timeslots_admin_router.callback_query.filter(IsAdmin())

FSM_FORM_KB = get_keyboard(
    "Назад",
    "Отмена",
    placeholder="Можно вернуться или отменить",
    sizes=(2,),
)

class AddSlotFSM(StatesGroup):
    day = State()
    start_time = State()


class EditSlotFSM(StatesGroup):
    day = State()
    start_time = State()

class BulkAddSlotFSM(StatesGroup):
    day = State()
    times = State()

class BulkRangeSlotFSM(StatesGroup):
    start_day = State()
    end_day = State()
    weekdays = State()
    times = State()

class CopyDaySlotFSM(StatesGroup):
    source_day = State()
    target_day = State()

def _h(value: str | None, default: str = "—") -> str:
    text = (value or "").strip()
    return escape(text or default)

def _parse_day_text(raw: str) -> date | None:
    try:
        return date.fromisoformat(raw.strip())
    except Exception:
        return None


def _parse_time_text(raw: str) -> time | None:
    try:
        hh_s, mm_s = raw.strip().split(":")
        return time(hour=int(hh_s), minute=int(mm_s))
    except Exception:
        return None


def _slot_in_past(day: date, start_time: time) -> bool:
    return booking_slot_dt(day, start_time) <= booking_now()

def _old_slot_datetime_from_state(data: dict) -> datetime | None:
    try:
        old_day = date.fromisoformat(str(data["old_day"]))
        old_time = _parse_time_text(str(data["old_time"]))
        if not old_time:
            return None
        return datetime.combine(old_day, old_time)
    except Exception:
        return None


def _normalize_bulk_tokens(raw: str) -> list[str]:
    normalized = (raw or "").replace(",", " ").replace("\n", " ")
    return [token.strip() for token in normalized.split() if token.strip()]


def _expand_range_token(token: str) -> tuple[list[time], str | None]:
    """
    Формат:
    10:00-12:00/30
    -> 10:00, 10:30, 11:00, 11:30
    """
    try:
        range_part, step_part = token.split("/", 1)
        start_s, end_s = range_part.split("-", 1)

        start_t = _parse_time_text(start_s)
        end_t = _parse_time_text(end_s)
        step = int(step_part)

        if not start_t or not end_t:
            return [], token
        if step <= 0:
            return [], token

        start_minutes = start_t.hour * 60 + start_t.minute
        end_minutes = end_t.hour * 60 + end_t.minute

        if end_minutes <= start_minutes:
            return [], token

        result: list[time] = []
        current = start_minutes

        while current < end_minutes:
            hh = current // 60
            mm = current % 60
            result.append(time(hour=hh, minute=mm))
            current += step

            if len(result) > 200:
                return [], token

        return result, None
    except Exception:
        return [], token


def _parse_bulk_times_input(raw: str) -> tuple[list[time], list[str]]:
    tokens = _normalize_bulk_tokens(raw)
    if not tokens:
        return [], []

    parsed: list[time] = []
    invalid_tokens: list[str] = []

    for token in tokens:
        if "-" in token and "/" in token:
            times_list, error_token = _expand_range_token(token)
            if error_token:
                invalid_tokens.append(error_token)
            else:
                parsed.extend(times_list)
            continue

        slot_time = _parse_time_text(token)
        if slot_time:
            parsed.append(slot_time)
        else:
            invalid_tokens.append(token)

    unique_sorted = sorted(dict.fromkeys(parsed))
    return unique_sorted, invalid_tokens

WEEKDAY_MAP = {
    "пн": 0,
    "вт": 1,
    "ср": 2,
    "чт": 3,
    "пт": 4,
    "сб": 5,
    "вс": 6,
    "вск": 6,
}

def _parse_weekdays(raw: str) -> list[int] | None:
    text = raw.lower().replace(",", " ")
    tokens = [t for t in text.split() if t]

    if not tokens:
        return None

    if "будни" in tokens:
        return [0,1,2,3,4]

    if "выходные" in tokens:
        return [5,6]

    if "все" in tokens:
        return list(range(7))

    result = []
    for t in tokens:
        if t not in WEEKDAY_MAP:
            return None
        result.append(WEEKDAY_MAP[t])

    return sorted(set(result))

def _generate_days(start: date, end: date, weekdays: list[int]) -> list[date]:
    result = []

    cur = start
    while cur <= end:
        if cur.weekday() in weekdays:
            result.append(cur)
        cur += timedelta(days=1)

    return result



def _fmt_times(times_list: list[time]) -> str:
    return ", ".join(t.strftime("%H:%M") for t in times_list)


def _bulk_day_prompt(service_title: str) -> str:
    return (
        f"⚡ Массовое добавление слотов для услуги: <b>{_h(service_title)}</b>\n\n"
        "Шаг 1/2: введи дату YYYY-MM-DD\n"
        "Пример: 2026-03-20\n"
        "/отмена — выйти"
    )


def _bulk_times_prompt() -> str:
    return (
        "Шаг 2/2: введи времена одним сообщением.\n\n"
        "Можно так:\n"
        "10:00 10:30 11:00\n\n"
        "Или так:\n"
        "10:00-12:00/30\n\n"
        "Или смешанно:\n"
        "10:00-12:00/30\n"
        "13:00\n"
        "14:30"
    )


def _bulk_result_text(
    *,
    created_times: list[time],
    duplicate_times: list[time],
    past_times: list[time],
    invalid_tokens: list[str],
) -> str:
    parts: list[str] = [
        "⚡ Массовое добавление завершено.",
        "",
        f"Создано: {len(created_times)}",
        f"Пропущено как дубликаты: {len(duplicate_times)}",
        f"Пропущено как прошедшие: {len(past_times)}",
        f"Ошибки формата: {len(invalid_tokens)}",
    ]

    if created_times:
        parts.extend(["", f"Создано: {_fmt_times(created_times)}"])
    if duplicate_times:
        parts.extend(["", f"Дубликаты: {_fmt_times(duplicate_times)}"])
    if past_times:
        parts.extend(["", f"Прошедшие: {_fmt_times(past_times)}"])
    if invalid_tokens:
        parts.extend(["", f"Не разобрано: {', '.join(invalid_tokens)}"])

    return "\n".join(parts)

def _parse_slot_cmd(text: str) -> tuple[int, date, time] | None:
    parts = (text or "").split()
    if len(parts) != 4:
        return None
    _, service_id_s, day_s, time_s = parts
    try:
        service_id = int(service_id_s)
    except ValueError:
        return None

    day = _parse_day_text(day_s)
    slot_time = _parse_time_text(time_s)
    if not day or not slot_time:
        return None
    return service_id, day, slot_time


def _slot_status(is_active: bool, is_booked: bool) -> str:
    if is_booked:
        return "🚫 занят"
    if is_active:
        return "✅ свободен"
    return "⏸️ выключен"


def _slot_card_text(*, service_title: str, slot_day: date, slot_time: time, is_active: bool, is_booked: bool) -> str:
    return (
        f"<b>Слот</b>\n"
        f"Услуга: {_h(service_title)}\n"
        f"Дата: {slot_day.isoformat()}\n"
        f"Время: {slot_time.strftime('%H:%M')} ({booking_timezone_label()})\n"
        f"Статус: {_slot_status(is_active, is_booked)}"
    )


async def _edit_or_send(msg: types.Message, *, text: str, kb: types.InlineKeyboardMarkup | None) -> None:
    try:
        if msg.photo:
            await msg.edit_caption(caption=text, reply_markup=kb)
        else:
            await msg.edit_text(text=text, reply_markup=kb)
    except TelegramBadRequest:
        await msg.answer(text, reply_markup=kb)


async def _show_slots_list(
    msg: types.Message,
    *,
    session: AsyncSession,
    service_id: int,
    page_num: int,
    mode: int,
    notice: str | None = None,
) -> None:
    page = await orm_get_timeslots_page(
        session,
        service_id=service_id,
        page=page_num,
        per_page=10,
        mode=mode,
    )
    service = await orm_get_service(session, service_id)
    service_title = service.title if service else f"#{service_id}"
    text = (
        f"🕒 Расписание: {_h(service_title)}\n"
        f"Часовой пояс: {booking_timezone_label()}\n"
        f"Страница {page.page}/{page.pages}"
    )
    if notice:
        text = f"{notice}\n\n{text}"
    await _edit_or_send(msg, text=text, kb=kb_admin_timeslots(service_id, page, mode=mode))


async def _show_slot_card(
    msg: types.Message,
    *,
    session: AsyncSession,
    service_id: int,
    slot_id: int,
    page_num: int,
    mode: int,
    notice: str | None = None,
) -> bool:
    slot = await orm_get_timeslot(session, slot_id)
    if not slot:
        return False
    has_bookings = await orm_slot_has_bookings(session, slot.id)

    service = await orm_get_service(session, service_id)
    service_title = service.title if service else f"#{service_id}"

    text = _slot_card_text(
        service_title=service_title,
        slot_day=slot.day,
        slot_time=slot.start_time,
        is_active=slot.is_active,
        is_booked=slot.is_booked,
    )
    if notice:
        text = f"{notice}\n\n{text}"

    kb = kb_admin_timeslot_card(
        service_id,
        slot.id,
        p=page_num,
        mode=mode,
        is_active=slot.is_active,
        is_booked=slot.is_booked,
        has_bookings=has_bookings,
    )
    await _edit_or_send(msg, text=text, kb=kb)
    return True


async def _notify_users_about_slot_cleanup(
    bot: Bot,
    tg_ids: list[int],
    *,
    service_title: str,
    slot_day: date,
    slot_time: time,
) -> None:
    if not tg_ids:
        return

    safe_title = _h(service_title)

    text = (
        "ℹ️ Ваша запись отменена администратором.\n\n"
        f"Услуга: {safe_title}\n"
        f"Дата: {slot_day.strftime('%d.%m.%Y')}\n"
        f"Время: {slot_time.strftime('%H:%M')}\n"
        "Причина: слот удалён или переоформлен."
    )
    for tg_id in tg_ids:
        try:
            await bot.send_message(chat_id=tg_id, text=text)
        except Exception as e:
            logger.warning("Slot cleanup notify failed for %s: %s", tg_id, e)

async def _slot_active_booking_tg_ids(session: AsyncSession, slot_id: int) -> list[int]:
    return await orm_get_active_booking_tg_ids_by_slot(session, slot_id)


@timeslots_admin_router.message(
    StateFilter(
        AddSlotFSM.day,
        AddSlotFSM.start_time,
        EditSlotFSM.day,
        EditSlotFSM.start_time,
        BulkAddSlotFSM.day,
        BulkAddSlotFSM.times,
        BulkRangeSlotFSM.start_day,
        BulkRangeSlotFSM.end_day,
        BulkRangeSlotFSM.weekdays,
        BulkRangeSlotFSM.times,
        CopyDaySlotFSM.source_day,
        CopyDaySlotFSM.target_day,
    ),
    F.text.casefold() == "назад",
)
async def slot_back(message: types.Message, state: FSMContext, session: AsyncSession):
    current_state = await state.get_state()
    if current_state is None:
        return

    data = await state.get_data()
    service_id = data.get("service_id")
    slot_id = data.get("slot_id")
    page_num = int(data.get("p", 1) or 1)
    mode = int(data.get("mode", 0) or 0)

    if current_state == AddSlotFSM.day.state:
        await state.clear()
        if service_id:
            await _show_slots_list(
                message,
                session=session,
                service_id=int(service_id),
                page_num=page_num,
                mode=mode,
                notice="Добавление отменено.",
            )
            return
        await message.answer("Админ-панель:", reply_markup=ADMIN_KB)
        return

    if current_state == AddSlotFSM.start_time.state:
        await state.set_state(AddSlotFSM.day)

        service = await orm_get_service(session, int(service_id)) if service_id else None
        service_title = service.title if service else f"#{service_id}"

        await message.answer(
            f"➕ Добавление слота для услуги: <b>{_h(service_title)}</b>\n\n"
            f"Часовой пояс слотов: {booking_timezone_label()}\n\n"
            "Шаг 1/2: введи дату в формате YYYY-MM-DD\n"
            "Пример: 2026-03-01\n"
            "Команда /отмена — выйти из режима добавления.",
            reply_markup=FSM_FORM_KB,
        )
        return

    if current_state == BulkAddSlotFSM.day.state:
        await state.clear()
        if service_id:
            await _show_slots_list(
                message,
                session=session,
                service_id=int(service_id),
                page_num=page_num,
                mode=mode,
                notice="Массовое добавление отменено.",
            )
            return
        await message.answer("Админ-панель:", reply_markup=ADMIN_KB)
        return

    if current_state == BulkAddSlotFSM.times.state:
        await state.set_state(BulkAddSlotFSM.day)

        service = await orm_get_service(session, int(service_id)) if service_id else None
        service_title = service.title if service else f"#{service_id}"

        await message.answer(
            _bulk_day_prompt(service_title),
            reply_markup=FSM_FORM_KB,
        )
        return

    if current_state == BulkRangeSlotFSM.start_day.state:
        await state.clear()
        if service_id:
            await _show_slots_list(
                message,
                session=session,
                service_id=int(service_id),
                page_num=page_num,
                mode=mode,
                notice="Создание по периоду отменено.",
            )
            return
        await message.answer("Админ-панель:", reply_markup=ADMIN_KB)
        return

    if current_state == BulkRangeSlotFSM.end_day.state:
        await state.set_state(BulkRangeSlotFSM.start_day)

        service = await orm_get_service(session, int(service_id)) if service_id else None
        service_title = service.title if service else f"#{service_id}"

        await message.answer(
            f"🗓️ Создание расписания для услуги <b>{_h(service_title)}</b>\n\n"
            "Шаг 1/4\n"
            "Введи дату начала (YYYY-MM-DD)",
            reply_markup=FSM_FORM_KB,
        )
        return

    if current_state == CopyDaySlotFSM.source_day.state:
        await state.clear()

        if service_id:
            await _show_slots_list(
                message,
                session=session,
                service_id=int(service_id),
                page_num=page_num,
                mode=mode,
                notice="Копирование дня отменено.",
            )
            return

    if current_state == CopyDaySlotFSM.target_day.state:
        await state.set_state(CopyDaySlotFSM.source_day)

        await message.answer(
            "Шаг 1/2\n"
            "Введи дату-источник (YYYY-MM-DD)",
            reply_markup=FSM_FORM_KB,
        )
        return

    if current_state == BulkRangeSlotFSM.weekdays.state:
        await state.set_state(BulkRangeSlotFSM.end_day)

        await message.answer(
            "Шаг 2/4\n"
            "Введи дату конца (YYYY-MM-DD)",
            reply_markup=FSM_FORM_KB,
        )
        return

    if current_state == BulkRangeSlotFSM.times.state:
        await state.set_state(BulkRangeSlotFSM.weekdays)

        await message.answer(
            "Шаг 3/4\n"
            "Введи дни недели\n\n"
            "Пример:\n"
            "пн ср пт\n"
            "или\n"
            "будни",
            reply_markup=FSM_FORM_KB,
        )
        return

    if current_state == EditSlotFSM.day.state:
        await state.clear()

        if service_id and slot_id:
            ok = await _show_slot_card(
                message,
                session=session,
                service_id=int(service_id),
                slot_id=int(slot_id),
                page_num=page_num,
                mode=mode,
                notice="Редактирование отменено.",
            )
            if ok:
                return

        if service_id:
            await _show_slots_list(
                message,
                session=session,
                service_id=int(service_id),
                page_num=page_num,
                mode=mode,
                notice="Редактирование отменено.",
            )
            return

        await message.answer("Админ-панель:", reply_markup=ADMIN_KB)
        return

    if current_state == EditSlotFSM.start_time.state:
        await state.set_state(EditSlotFSM.day)

        service = await orm_get_service(session, int(service_id)) if service_id else None
        service_title = service.title if service else f"#{service_id}"

        old_day = str(data.get("old_day", ""))
        old_time = str(data.get("old_time", ""))
        old_dt = _old_slot_datetime_from_state(data)
        old_is_past = old_dt is not None and old_dt < booking_now()

        hint = (
            "/отмена — выйти."
            if old_is_past
            else "'.' — оставить старую дату, /отмена — выйти."
        )

        await message.answer(
            f"✏️ Редактирование слота ({_h(service_title)})\n"
            f"Текущие: {old_day} {old_time}\n\n"
            "Шаг 1/2: введи новую дату YYYY-MM-DD.\n"
            f"{hint}",
            reply_markup=FSM_FORM_KB,
        )
        return

@timeslots_admin_router.message(
    StateFilter(
        AddSlotFSM.day,
        AddSlotFSM.start_time,
        EditSlotFSM.day,
        EditSlotFSM.start_time,
        BulkAddSlotFSM.day,
        BulkAddSlotFSM.times,
        BulkRangeSlotFSM.start_day,
        BulkRangeSlotFSM.end_day,
        BulkRangeSlotFSM.weekdays,
        BulkRangeSlotFSM.times,
    ),
    Command("отмена"),
)

@timeslots_admin_router.message(
    StateFilter(
        AddSlotFSM.day,
        AddSlotFSM.start_time,
        EditSlotFSM.day,
        EditSlotFSM.start_time,
        BulkAddSlotFSM.day,
        BulkAddSlotFSM.times,
        BulkRangeSlotFSM.start_day,
        BulkRangeSlotFSM.end_day,
        BulkRangeSlotFSM.weekdays,
        BulkRangeSlotFSM.times,
        CopyDaySlotFSM.source_day,
        CopyDaySlotFSM.target_day,
    ),
    F.text.casefold() == "отмена",
)
async def slot_cancel(message: types.Message, state: FSMContext, session: AsyncSession):
    current_state = await state.get_state()
    if current_state is None:
        return

    data = await state.get_data()
    await state.clear()

    await message.answer("Ок, отменено.", reply_markup=types.ReplyKeyboardRemove())

    service_id = data.get("service_id")
    slot_id = data.get("slot_id")
    page_num = int(data.get("p", 1) or 1)
    mode = int(data.get("mode", 0) or 0)

    if service_id and slot_id:
        ok = await _show_slot_card(
            message,
            session=session,
            service_id=int(service_id),
            slot_id=int(slot_id),
            page_num=page_num,
            mode=mode,
            notice="Редактирование отменено.",
        )
        if ok:
            return

    if service_id:
        notice = "Добавление отменено."

        if current_state in {BulkAddSlotFSM.day.state, BulkAddSlotFSM.times.state}:
            notice = "Массовое добавление отменено."

        if current_state in {
            BulkRangeSlotFSM.start_day.state,
            BulkRangeSlotFSM.end_day.state,
            BulkRangeSlotFSM.weekdays.state,
            BulkRangeSlotFSM.times.state,
        }:
            notice = "Создание по периоду отменено."

        await _show_slots_list(
            message,
            session=session,
            service_id=int(service_id),
            page_num=page_num,
            mode=mode,
            notice=notice,
        )
        return

    await message.answer("Админ-панель:", reply_markup=ADMIN_KB)

@timeslots_admin_router.message(F.text == "Расписание")
async def slots_entry(message: types.Message, session: AsyncSession):
    services = await orm_get_services(session, include_inactive=True)
    if not services:
        await message.answer("Сначала добавьте услуги (Админ → Услуги).", reply_markup=ADMIN_KB)
        return

    await message.answer("🕒 Расписание → выберите услугу:", reply_markup=kb_admin_services_for_slots(services))


@timeslots_admin_router.callback_query(SlotAdminCB.filter())
async def slots_callbacks(
    call: types.CallbackQuery,
    callback_data: SlotAdminCB,
    session: AsyncSession,
    state: FSMContext,
    bot: Bot,
):
    msg = call.message
    if not isinstance(msg, types.Message):
        await call.answer()
        return

    action = callback_data.action
    mode = int(callback_data.mode or 0)

    if action == "home":
        await call.answer()
        await msg.answer("Админ-панель:", reply_markup=ADMIN_KB)
        return

    if action == "services":
        services = await orm_get_services(session, include_inactive=True)
        await call.answer()
        await _edit_or_send(msg, text="🕒 Расписание → выберите услугу:", kb=kb_admin_services_for_slots(services))
        return

    if action == "mode":
        if not callback_data.service:
            await call.answer("Не выбрана услуга.", show_alert=True)
            return
        new_mode = (mode + 1) % 3
        await call.answer()
        await _show_slots_list(
            msg,
            session=session,
            service_id=callback_data.service,
            page_num=callback_data.p,
            mode=new_mode,
        )
        return

    if action == "list":
        if not callback_data.service:
            await call.answer("Не выбрана услуга.", show_alert=True)
            return
        await call.answer()
        await _show_slots_list(
            msg,
            session=session,
            service_id=callback_data.service,
            page_num=callback_data.p,
            mode=mode,
        )
        return

    if action == "add":
        if not callback_data.service:
            await call.answer("Не выбрана услуга.", show_alert=True)
            return

        service = await orm_get_service(session, callback_data.service)
        if not service:
            await call.answer("Услуга не найдена.", show_alert=True)
            return

        await state.clear()
        await state.update_data(
            service_id=service.id,
            mode=mode,
            p=callback_data.p or 1,
        )
        await state.set_state(AddSlotFSM.day)

        await call.answer()
        await msg.answer(
            f"➕ Добавление слота для услуги: <b>{_h(service.title)}</b>\n\n"
            "Шаг 1/2: введи дату в формате YYYY-MM-DD\n"
            "Пример: 2026-03-01\n"
            "Команда /отмена — выйти из режима добавления.",
            reply_markup=FSM_FORM_KB,
        )
        return
    
    if action in {"add_today", "add_tomorrow"}:

        if not callback_data.service:
            await call.answer("Не выбрана услуга.", show_alert=True)
            return

        service = await orm_get_service(session, callback_data.service)
        if not service:
            await call.answer("Услуга не найдена.", show_alert=True)
            return

        target_day = booking_now().date()

        if action == "add_tomorrow":
            target_day = target_day + timedelta(days=1)

        await state.clear()

        await state.update_data(
            service_id=service.id,
            mode=mode,
            p=callback_data.p or 1,
            day=target_day.isoformat(),
        )

        await state.set_state(AddSlotFSM.start_time)

        await call.answer()

        await msg.answer(
            f"➕ Добавление слота для услуги: <b>{service.title}</b>\n\n"
            f"Дата: {target_day.isoformat()}\n"
            f"Часовой пояс: {booking_timezone_label()}\n\n"
            "Шаг 1/1: введи одно время в формате HH:MM.\n"
            "Пример: 10:30\n\n"
            "Если нужно добавить несколько времён или диапазон, используй «⚡ Массово добавить».",
            reply_markup=FSM_FORM_KB,
        )
        return
    
    if action == "bulk_add":
        if not callback_data.service:
            await call.answer("Не выбрана услуга.", show_alert=True)
            return

        service = await orm_get_service(session, callback_data.service)
        if not service:
            await call.answer("Услуга не найдена.", show_alert=True)
            return

        await state.clear()
        await state.update_data(
            service_id=service.id,
            mode=mode,
            p=callback_data.p or 1,
        )
        await state.set_state(BulkAddSlotFSM.day)

        await call.answer()
        await msg.answer(
            _bulk_day_prompt(service.title),
            reply_markup=FSM_FORM_KB,
        )
        return
        
    if action == "bulk_range":
        if not callback_data.service:
            await call.answer("Не выбрана услуга.", show_alert=True)
            return

        service = await orm_get_service(session, callback_data.service)
        if not service:
            await call.answer("Услуга не найдена.", show_alert=True)
            return

        await state.clear()

        await state.update_data(
            service_id=service.id,
            mode=mode,
            p=callback_data.p or 1,
        )

        await state.set_state(BulkRangeSlotFSM.start_day)

        await call.answer()

        await msg.answer(
            f"🗓️ Создание расписания для услуги <b>{_h(service.title)}</b>\n\n"
            "Шаг 1/4\n"
            "Введи дату начала (YYYY-MM-DD)",
            reply_markup=FSM_FORM_KB,
        )

        return
    
    if action == "copy_day":
        if not callback_data.service:
            await call.answer("Не выбрана услуга.", show_alert=True)
            return

        service = await orm_get_service(session, callback_data.service)
        if not service:
            await call.answer("Услуга не найдена.", show_alert=True)
            return

        await state.clear()

        await state.update_data(
            service_id=service.id,
            mode=mode,
            p=callback_data.p or 1,
        )

        await state.set_state(CopyDaySlotFSM.source_day)

        await call.answer()

        await msg.answer(
            f"📋 Копирование слотов для услуги <b>{_h(service.title)}</b>\n\n"
            "Шаг 1/2\n"
            "Введи дату-источник (YYYY-MM-DD)",
            reply_markup=FSM_FORM_KB,
        )

        return

    if action == "open":
        if not callback_data.service or not callback_data.slot:
            await call.answer("Не хватает данных.", show_alert=True)
            return
        ok = await _show_slot_card(
            msg,
            session=session,
            service_id=callback_data.service,
            slot_id=callback_data.slot,
            page_num=callback_data.p,
            mode=mode,
        )
        if not ok:
            await call.answer("Слот не найден.", show_alert=True)
            return
        await call.answer()
        return

    if action == "edit":
        if not callback_data.slot:
            await call.answer("Слот не выбран.", show_alert=True)
            return

        if await orm_slot_has_bookings(session, callback_data.slot):
            await call.answer(
                "Нельзя изменять дату или время слота, если по нему уже есть записи.",
                show_alert=True,
            )
            return
        if not callback_data.service or not callback_data.slot:
            
            await call.answer("Не хватает данных.", show_alert=True)
            return

        slot = await orm_get_timeslot(session, callback_data.slot)
        if not slot:
            await call.answer("Слот не найден.", show_alert=True)
            return

        service = await orm_get_service(session, callback_data.service)
        service_title = service.title if service else f"#{callback_data.service}"

        await state.clear()
        await state.update_data(
            service_id=callback_data.service,
            slot_id=slot.id,
            p=callback_data.p,
            mode=mode,
            old_day=slot.day.isoformat(),
            old_time=slot.start_time.strftime("%H:%M"),
        )
        await state.set_state(EditSlotFSM.day)

        await call.answer()
        old_is_past = _slot_in_past(slot.day, slot.start_time)

        hint = (
            "/отмена — выйти."
            if old_is_past
            else "'.' — оставить старую дату, /отмена — выйти."
        )

        await msg.answer(
            f"✏️ Редактирование слота ({service_title})\n"
            f"Текущие: {slot.day.isoformat()} {slot.start_time.strftime('%H:%M')}\n\n"
            "Шаг 1/2: введи новую дату YYYY-MM-DD.\n"
            f"{hint}",
            reply_markup=FSM_FORM_KB,
        )
        return

    if action == "toggle_active":
        if not callback_data.service or not callback_data.slot:
            await call.answer("Не хватает данных.", show_alert=True)
            return

        await orm_toggle_timeslot_active(session, callback_data.slot)
        await call.answer("Готово ✅")

        await _show_slot_card(
            msg,
            session=session,
            service_id=callback_data.service,
            slot_id=callback_data.slot,
            page_num=callback_data.p,
            mode=mode,
        )
        return

    if action == "free":
        if not callback_data.slot:
            await call.answer("Слот не выбран.", show_alert=True)
            return

        slot = await orm_get_timeslot(session, callback_data.slot)
        if not slot:
            await call.answer("Слот не найден.", show_alert=True)
            return

        service = await orm_get_service(session, slot.service_id)
        service_title = service.title if service else f"Услуга #{slot.service_id}"

        tg_ids = await _slot_active_booking_tg_ids(session, callback_data.slot)

        cancelled = await orm_release_slot_and_cancel_bookings(session, callback_data.slot)

        if cancelled > 0 and tg_ids:
            await _notify_users_about_slot_cleanup(
                bot=bot,
                tg_ids=tg_ids,
                service_title=service_title,
                slot_day=slot.day,
                slot_time=slot.start_time,
            )

    
        await call.answer(f"Слот освобождён. Отменено записей: {cancelled}")

        slot = await orm_get_timeslot(session, callback_data.slot)
        if not slot:
            return
        await _show_slot_card(
            msg,
            session=session,
            service_id=callback_data.service or slot.service_id,
            slot_id=slot.id,
            page_num=callback_data.p,
            mode=mode,
        )
        return

    if action == "del":
        if not callback_data.service or not callback_data.slot:
            await call.answer("Не хватает данных.", show_alert=True)
            return

        has_bookings = await orm_slot_has_bookings(session, callback_data.slot)
        if has_bookings:
            await call.answer(
                "По слоту есть записи. Используй кнопку «🧹 Удалить с очисткой».",
                show_alert=True,
            )
            await _show_slot_card(
                msg,
                session=session,
                service_id=callback_data.service,
                slot_id=callback_data.slot,
                page_num=callback_data.p,
                mode=mode,
            )
            return

        await orm_delete_timeslot(session, callback_data.slot)
        await call.answer("Удалено ✅")
        await _show_slots_list(
            msg,
            session=session,
            service_id=callback_data.service,
            page_num=callback_data.p,
            mode=mode,
        )
        return

    if action == "purge_ask":
        if not callback_data.slot:
            await call.answer("Не выбран слот.", show_alert=True)
            return

        slot = await orm_get_timeslot(session, callback_data.slot)
        if not slot:
            await call.answer("Слот не найден.", show_alert=True)
            return

        service_id = callback_data.service or slot.service_id
        service = await orm_get_service(session, service_id)
        service_title = service.title if service else f"#{service_id}"
        text = (
            _slot_card_text(
                service_title=service_title,
                slot_day=slot.day,
                slot_time=slot.start_time,
                is_active=slot.is_active,
                is_booked=slot.is_booked,
            )
            + "\n\n⚠️ Будут удалены слот и все записи по этому слоту."
        )
        await _edit_or_send(
            msg,
            text=text,
            kb=kb_admin_timeslot_purge_confirm(
                service_id,
                slot.id,
                p=callback_data.p,
                mode=mode,
            ),
        )
        await call.answer()
        return

    if action == "purge_do":
        if not callback_data.slot:
            await call.answer("Не выбран слот.", show_alert=True)
            return

        slot = await orm_get_timeslot(session, callback_data.slot)
        if not slot:
            await call.answer("Слот уже удалён.", show_alert=True)
            return

        service_id = callback_data.service or slot.service_id
        service = await orm_get_service(session, service_id)
        service_title = service.title if service else f"#{service_id}"

        tg_ids = await orm_get_active_booking_tg_ids_by_slot(session, slot.id)
        ok, deleted_bookings = await orm_purge_slot_with_bookings(session, slot.id)
        if not ok:
            await call.answer("Не удалось удалить слот.", show_alert=True)
            return

        await _notify_users_about_slot_cleanup(
            bot,
            tg_ids,
            service_title=service_title,
            slot_day=slot.day,
            slot_time=slot.start_time,
        )

        await call.answer(f"Слот удалён. Удалено записей: {deleted_bookings}", show_alert=True)
        await _show_slots_list(
            msg,
            session=session,
            service_id=service_id,
            page_num=callback_data.p,
            mode=mode,
        )
        return

    await call.answer("Неизвестное действие", show_alert=True)

@timeslots_admin_router.message(BulkRangeSlotFSM.start_day, F.text)
async def bulk_range_start(message: types.Message, state: FSMContext):

    start = _parse_day_text(message.text or "")
    if not start:
        await message.answer(
            "Неверная дата.\n\n"
            "Шаг 1/4\n"
            "Введи дату начала (YYYY-MM-DD)",
            reply_markup=FSM_FORM_KB,
        )
        return

    if start < booking_now().date():
        await message.answer(
            "Дата начала не может быть в прошлом.\n\n"
            "Шаг 1/4\n"
            "Введи дату начала (YYYY-MM-DD)",
            reply_markup=FSM_FORM_KB,
        )
        return

    await state.update_data(start_day=start.isoformat())
    await state.set_state(BulkRangeSlotFSM.end_day)

    await message.answer(
        "Шаг 2/4\n"
        "Введи дату конца (YYYY-MM-DD)",
        reply_markup=FSM_FORM_KB,
    )

@timeslots_admin_router.message(BulkRangeSlotFSM.end_day, F.text)
async def bulk_range_end(message: types.Message, state: FSMContext):

    end = _parse_day_text(message.text or "")
    if not end:
        await message.answer(
            "Неверная дата.\n\n"
            "Шаг 2/4\n"
            "Введи дату конца (YYYY-MM-DD)",
            reply_markup=FSM_FORM_KB,
        )
        return

    data = await state.get_data()
    start = date.fromisoformat(data["start_day"])

    if end < start:
        await message.answer(
            "Дата конца раньше даты начала.\n\n"
            "Шаг 2/4\n"
            "Введи дату конца (YYYY-MM-DD)",
            reply_markup=FSM_FORM_KB,
        )
        return

    if (end - start).days > 90:
        await message.answer(
            "Максимальный диапазон 90 дней.\n\n"
            "Шаг 2/4\n"
            "Введи дату конца (YYYY-MM-DD)",
            reply_markup=FSM_FORM_KB,
        )
        return

    await state.update_data(end_day=end.isoformat())
    await state.set_state(BulkRangeSlotFSM.weekdays)

    await message.answer(
        "Шаг 3/4\n"
        "Введи дни недели\n\n"
        "Пример:\n"
        "пн ср пт\n"
        "или\n"
        "будни",
        reply_markup=FSM_FORM_KB,
    )

@timeslots_admin_router.message(BulkRangeSlotFSM.weekdays, F.text)
async def bulk_range_weekdays(message: types.Message, state: FSMContext):

    weekdays = _parse_weekdays(message.text or "")

    if not weekdays:
        await message.answer(
            "Не удалось разобрать дни недели.\n\n"
            "Шаг 3/4\n"
            "Введи дни недели\n\n"
            "Пример:\n"
            "пн ср пт\n"
            "или\n"
            "будни",
            reply_markup=FSM_FORM_KB,
        )
        return

    await state.update_data(weekdays=weekdays)
    await state.set_state(BulkRangeSlotFSM.times)

    await message.answer(
        "Шаг 4/4\n"
        "Введи времена\n\n"
        "Пример:\n"
        "10:00-18:00/30",
        reply_markup=FSM_FORM_KB,
    )


@timeslots_admin_router.message(CopyDaySlotFSM.source_day, F.text)
async def copy_day_source_step(message: types.Message, state: FSMContext):

    source = _parse_day_text(message.text or "")
    if not source:
        await message.answer(
            "Неверная дата.\n\n"
            "Шаг 1/2\n"
            "Введи дату-источник (YYYY-MM-DD)",
            reply_markup=FSM_FORM_KB,
        )
        return

    await state.update_data(source_day=source.isoformat())
    await state.set_state(CopyDaySlotFSM.target_day)

    await message.answer(
        "Шаг 2/2\n"
        "Введи дату-назначение (YYYY-MM-DD)",
        reply_markup=FSM_FORM_KB,
    )

@timeslots_admin_router.message(CopyDaySlotFSM.target_day, F.text)
async def copy_day_target_step(
    message: types.Message,
    state: FSMContext,
    session: AsyncSession,
):

    target = _parse_day_text(message.text or "")
    if not target:
        await message.answer(
            "Неверная дата.\n\n"
            "Шаг 2/2\n"
            "Введи дату-назначение (YYYY-MM-DD)",
            reply_markup=FSM_FORM_KB,
        )
        return

    if target < booking_now().date():
        await message.answer(
            "Дата назначения не может быть в прошлом.",
            reply_markup=FSM_FORM_KB,
        )
        return

    data = await state.get_data()

    service_id = int(data["service_id"])
    source_day = date.fromisoformat(data["source_day"])
    if target == source_day:
        await message.answer(
            "Дата назначения должна отличаться от даты-источника.\n\n"
            "Шаг 2/2\n"
            "Введи дату-назначение (YYYY-MM-DD)",
            reply_markup=FSM_FORM_KB,
        )
        return
    page_num = int(data.get("p", 1) or 1)
    mode = int(data.get("mode", 0) or 0)

    slots = await orm_get_timeslots_for_day(
        session,
        service_id=service_id,
        day=source_day,
    )

    if not slots:
        await message.answer(
            "На дате-источнике нет слотов.",
            reply_markup=FSM_FORM_KB,
        )
        return

    times = [slot.start_time for slot in slots]

    created, duplicates, past = await orm_add_timeslots_bulk(
        session,
        service_id=service_id,
        day=target,
        times=times,
    )

    await state.clear()

    summary = (
        "📋 Копирование дня завершено\n\n"
        f"Источник: {source_day.isoformat()}\n"
        f"Назначение: {target.isoformat()}\n\n"
        f"Создано: {len(created)}\n"
        f"Дубликаты: {len(duplicates)}\n"
        f"Прошедшие: {len(past)}"
    )

    await _show_slots_list(
        message,
        session=session,
        service_id=service_id,
        page_num=page_num,
        mode=mode,
        notice=summary,
    )


@timeslots_admin_router.message(BulkRangeSlotFSM.times, F.text)
async def bulk_range_times(
    message: types.Message,
    state: FSMContext,
    session: AsyncSession,
):

    raw = (message.text or "").strip()

    times_list, invalid_tokens = _parse_bulk_times_input(raw)

    if not times_list:
        await message.answer(
            "Не удалось разобрать времена.\n\n"
            "Шаг 4/4\n"
            "Введи времена\n\n"
            "Пример:\n"
            "10:00 10:30 11:00\n"
            "или\n"
            "10:00-18:00/30",
            reply_markup=FSM_FORM_KB,
        )
        return

    data = await state.get_data()

    service_id = int(data["service_id"])
    start = date.fromisoformat(data["start_day"])
    end = date.fromisoformat(data["end_day"])
    weekdays = list(data["weekdays"])

    page_num = int(data.get("p", 1) or 1)
    mode = int(data.get("mode", 0) or 0)

    days = _generate_days(start, end, weekdays)

    if not days:
        await message.answer(
            "В выбранном диапазоне нет дней с такими днями недели.\n\n"
            "Шаг 3/4\n"
            "Введи дни недели заново.",
            reply_markup=FSM_FORM_KB,
        )
        await state.set_state(BulkRangeSlotFSM.weekdays)
        return

    total_created = []
    total_duplicates = []
    total_past = []

    for day in days:

        created, duplicates, past = await orm_add_timeslots_bulk(
            session,
            service_id=service_id,
            day=day,
            times=times_list,
        )

        total_created.extend(created)
        total_duplicates.extend(duplicates)
        total_past.extend(past)

    await state.clear()

    total_days = len(days)
    total_candidates = total_days * len(times_list)

    summary = (
        "🗓️ Массовое создание по периоду завершено\n\n"
        f"Дней обработано: {total_days}\n"
        f"Кандидатов: {total_candidates}\n"
        f"Создано: {len(total_created)}\n"
        f"Дубликаты: {len(total_duplicates)}\n"
        f"Прошедшие: {len(total_past)}\n"
        f"Ошибки формата: {len(invalid_tokens)}"
    )

    await _show_slots_list(
        message,
        session=session,
        service_id=service_id,
        page_num=page_num,
        mode=mode,
        notice=summary,
    )



@timeslots_admin_router.message(AddSlotFSM.day, F.text)
async def add_slot_day_step(message: types.Message, state: FSMContext):
    raw = (message.text or "").strip()
    day = _parse_day_text(raw)
    if not day:
        await message.answer("Неверная дата. Формат: YYYY-MM-DD. Пример: 2026-03-01", reply_markup=FSM_FORM_KB)
        return
    if day < booking_now().date():
        await message.answer("Нельзя создать слот в прошлом. Введи актуальную дату.", reply_markup=FSM_FORM_KB)
        return

    await state.update_data(day=day.isoformat())
    await state.set_state(AddSlotFSM.start_time)
    await message.answer(
        "Шаг 2/2: введи время в формате HH:MM. Пример: 10:30",
        reply_markup=FSM_FORM_KB,
    )


@timeslots_admin_router.message(AddSlotFSM.start_time, F.text)
async def add_slot_time_step(message: types.Message, state: FSMContext, session: AsyncSession):
    slot_time = _parse_time_text(message.text or "")
    if not slot_time:
        await message.answer("Неверное время. Формат: HH:MM. Пример: 10:30", reply_markup=FSM_FORM_KB)
        return

    data = await state.get_data()
    service_id = int(data["service_id"])
    day = date.fromisoformat(str(data["day"]))

    if _slot_in_past(day, slot_time):
        await message.answer("Слот в прошлом. Выбери другое время.", reply_markup=FSM_FORM_KB)
        return

    try:
        await orm_add_timeslot(session, service_id=service_id, day=day, start_time=slot_time)
    except Exception as e:
        logger.warning("Add slot failed: %s", e)
        await message.answer("Не удалось добавить слот (возможно, уже есть такой).", reply_markup=FSM_FORM_KB)
        return

    page_num = int(data.get("p", 1) or 1)
    mode = int(data.get("mode", 0) or 0)

    await state.clear()
    await message.answer(
        "✅ Слот добавлен.",
        reply_markup=types.ReplyKeyboardRemove(),
    )

    await _show_slots_list(
        message,
        session=session,
        service_id=service_id,
        page_num=page_num,
        mode=mode,
    )



@timeslots_admin_router.message(BulkAddSlotFSM.day, F.text)
async def bulk_add_slot_day_step(message: types.Message, state: FSMContext):
    raw = (message.text or "").strip()
    day = _parse_day_text(raw)
    if not day:
        await message.answer(
            "Неверная дата. Формат: YYYY-MM-DD. Пример: 2026-03-20",
            reply_markup=FSM_FORM_KB,
        )
        return

    if day < booking_today():
        await message.answer(
            "Нельзя создать слоты в прошлом. Введи актуальную дату.",
            reply_markup=FSM_FORM_KB,
        )
        return

    await state.update_data(day=day.isoformat())
    await state.set_state(BulkAddSlotFSM.times)
    await message.answer(
        _bulk_times_prompt(),
        reply_markup=FSM_FORM_KB,
    )

@timeslots_admin_router.message(BulkAddSlotFSM.times, F.text)
async def bulk_add_slot_times_step(
    message: types.Message,
    state: FSMContext,
    session: AsyncSession,
):
    raw = (message.text or "").strip()
    times_list, invalid_tokens = _parse_bulk_times_input(raw)

    if not times_list:
        invalid_part = ""
        if invalid_tokens:
            invalid_part = f"\n\nНе разобрано: {', '.join(invalid_tokens)}"

        await message.answer(
            "Не удалось разобрать ни одного корректного времени."
            "\nИспользуй формат вроде:\n"
            "10:00 10:30 11:00\n"
            "или\n"
            "10:00-12:00/30"
            f"{invalid_part}",
            reply_markup=FSM_FORM_KB,
        )
        return

    data = await state.get_data()
    service_id = int(data["service_id"])
    day = date.fromisoformat(str(data["day"]))
    page_num = int(data.get("p", 1) or 1)
    mode = int(data.get("mode", 0) or 0)

    try:
        created_times, duplicate_times, past_times = await orm_add_timeslots_bulk(
            session,
            service_id=service_id,
            day=day,
            times=times_list,
        )
    except Exception as e:
        logger.warning("Bulk add slots failed: %s", e)
        await message.answer(
            "Не удалось массово добавить слоты.",
            reply_markup=FSM_FORM_KB,
        )
        return

    await state.clear()

    summary = _bulk_result_text(
        created_times=created_times,
        duplicate_times=duplicate_times,
        past_times=past_times,
        invalid_tokens=invalid_tokens,
    )

    await _show_slots_list(
        message,
        session=session,
        service_id=service_id,
        page_num=page_num,
        mode=mode,
        notice=summary,
    )


@timeslots_admin_router.message(EditSlotFSM.day, F.text)
async def edit_slot_day_step(message: types.Message, state: FSMContext):
    data = await state.get_data()
    raw = (message.text or "").strip()

    old_dt = _old_slot_datetime_from_state(data)

    if raw == ".":
        if old_dt and old_dt < booking_now():
            await message.answer(
                "Старую дату оставить нельзя: текущий слот уже в прошлом.\n"
                "Введи новую дату в формате YYYY-MM-DD.", reply_markup=FSM_FORM_KB
            )
            return
        day = date.fromisoformat(str(data["old_day"]))
    else:
        parsed_day = _parse_day_text(raw)
        if parsed_day is None:
            await message.answer(
                "Введите корректную дату в формате YYYY-MM-DD.",
                reply_markup=FSM_FORM_KB,
            )
            return

        day = parsed_day

        if day < booking_now().date():
            await message.answer("Нельзя поставить дату в прошлом.", reply_markup=FSM_FORM_KB)
            return

    await state.update_data(day=day.isoformat())
    await state.set_state(EditSlotFSM.start_time)
    await message.answer(
        "Шаг 2/2: введи время HH:MM, или '.' чтобы оставить старое.",
        reply_markup=FSM_FORM_KB,
    )


@timeslots_admin_router.message(EditSlotFSM.start_time, F.text)
async def edit_slot_time_step(message: types.Message, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    raw = (message.text or "").strip()
    day = date.fromisoformat(str(data["day"]))

    if raw == ".":
        slot_time = _parse_time_text(str(data["old_time"]))
        if not slot_time:
            await message.answer("Не удалось взять старое время. Введи HH:MM.", reply_markup=FSM_FORM_KB)
            return

        if _slot_in_past(day, slot_time):
            await message.answer(
                "Старое время оставить нельзя: итоговый слот уже в прошлом.\n"
                "Введи новое время в формате HH:MM.", reply_markup=FSM_FORM_KB
            )
            return
    else:
        slot_time = _parse_time_text(raw)
        if not slot_time:
            await message.answer("Неверное время. Формат: HH:MM или '.'", reply_markup=FSM_FORM_KB)
            return

        if _slot_in_past(day, slot_time):
            await message.answer("Слот в прошлом. Выбери другое время.", reply_markup=FSM_FORM_KB)
            return

    slot_id = int(data["slot_id"])
    service_id = int(data["service_id"])
    page_num = int(data.get("p", 1) or 1)
    mode = int(data.get("mode", 0) or 0)

    try:
        if await orm_slot_has_bookings(session, slot_id):
            await state.clear()
            await _show_slot_card(
                message,
                session=session,
                service_id=service_id,
                slot_id=slot_id,
                page_num=page_num,
                mode=mode,
                notice="Нельзя сохранить изменения: по этому слоту уже есть записи.",
            )
            return
        updated = await orm_update_timeslot_datetime(
            session,
            slot_id=slot_id,
            day=day,
            start_time=slot_time,
        )
    except Exception as e:
        logger.warning("Update slot failed: %s", e)
        await message.answer("Не удалось обновить слот (возможно, уже есть такой).", reply_markup=FSM_FORM_KB)
        return

    if not updated:
        await message.answer("Слот не найден.", reply_markup=FSM_FORM_KB)
        return

    
    await state.clear()
    await message.answer("✅ Слот обновлён.", reply_markup=types.ReplyKeyboardRemove())

    await _show_slot_card(
        message,
        session=session,
        service_id=service_id,
        slot_id=slot_id,
        page_num=page_num,
        mode=mode,
        notice=None,
    )





@timeslots_admin_router.message(Command("slot"))
async def add_slot_cmd(message: types.Message, session: AsyncSession):
    parsed = _parse_slot_cmd(message.text or "")
    if not parsed:
        await message.answer(
            "Формат:\n<pre>/slot SERVICE_ID YYYY-MM-DD HH:MM</pre>\n"
            "Пример:\n<pre>/slot 1 2026-03-01 10:30</pre>"
        )
        return

    service_id, day, slot_time = parsed

    service = await orm_get_service(session, service_id)
    if not service:
        await message.answer(f"Нет такой услуги: {service_id}.")
        return

    if _slot_in_past(day, slot_time):
        await message.answer("Нельзя добавить слот в прошлом.")
        return

    try:
        slot = await orm_add_timeslot(session, service_id=service_id, day=day, start_time=slot_time)
    except Exception as e:
        logger.warning("Add slot failed: %s", e)
        await message.answer("Не удалось добавить слот (возможно, уже есть такой).")
        return

    await message.answer(
        f"✅ Слот добавлен: service={service_id} {slot.day.isoformat()} {slot.start_time.strftime('%H:%M')}"
    )
