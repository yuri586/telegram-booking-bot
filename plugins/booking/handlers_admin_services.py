from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from html import escape

from aiogram import Bot, F, Router, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession

from database.orm_query import (
    orm_add_service,
    orm_delete_service,
    orm_get_active_booking_tg_ids_by_service,
    orm_get_service,
    orm_get_service_dependency_stats,
    orm_get_services,
    orm_get_timeslots_page,
    orm_purge_service_with_dependencies,
    orm_toggle_service_active,
    orm_update_service,
)
from filters.chat_types import ChatTypeFilter, IsAdmin
from keyboards.admin_reply import ADMIN_KB  # твоя основная админ reply-клава
from keyboards.inline import (
    ServiceAdminCB,
    kb_admin_timeslots,
    kb_service_admin_card,
    kb_service_admin_purge_confirm,
    kb_services_admin_list,
)
from keyboards.reply import get_keyboard

logger = logging.getLogger(__name__)

services_admin_router = Router()
services_admin_router.message.filter(ChatTypeFilter(["private"]), IsAdmin())
services_admin_router.callback_query.filter(IsAdmin())

FSM_FORM_KB = get_keyboard(
    "Назад",
    "Отмена",
    placeholder="Можно вернуться или отменить",
    sizes=(2,),
)


class AddService(StatesGroup):
    title = State()
    description = State()
    price = State()


class EditService(StatesGroup):
    title = State()
    description = State()
    price = State()


def _format_price(p: Decimal | None) -> str:
    if p is None:
        return "—"
    return f"{Decimal(str(p)):.2f}"

def _h(value: str | None, default: str = "—") -> str:
    text = (value or "").strip()
    return escape(text or default)


async def _edit_or_send(
    msg: types.Message,
    *,
    text: str,
    kb: types.InlineKeyboardMarkup,
) -> None:
    try:
        if msg.photo:
            await msg.edit_caption(caption=text, reply_markup=kb)
        else:
            await msg.edit_text(text=text, reply_markup=kb)
    except TelegramBadRequest:
        await msg.answer(text, reply_markup=kb)


async def _show_services_list(
    message: types.Message,
    session: AsyncSession,
    *,
    show: int,
    notice: str | None = None,
) -> None:
    services = await orm_get_services(session, include_inactive=bool(show))
    text = "🧾 Услуги:"
    if notice:
        text = f"{notice}\n\n{text}"
    kb = kb_services_admin_list(services, show=show)
    await message.answer(text, reply_markup=kb)


async def _show_service_card(
    message: types.Message,
    session: AsyncSession,
    *,
    service_id: int,
    show: int,
    notice: str | None = None,
) -> None:
    s = await orm_get_service(session, service_id)
    if not s:
        await _show_services_list(message, session, show=show, notice="Услуга не найдена.")
        return

    slots_count, bookings_count, active_bookings_count = await orm_get_service_dependency_stats(
        session, s.id
    )
    text = _service_card_text(
        title=s.title,
        description=s.description,
        price=s.price,
        slots_count=slots_count,
        bookings_count=bookings_count,
        active_bookings_count=active_bookings_count,
    )
    if notice:
        text = f"{notice}\n\n{text}"

    await message.answer(
        text,
        reply_markup=kb_service_admin_card(s.id, is_active=s.is_active, show=show),
    )

def _service_card_text(
    *,
    title: str,
    description: str | None,
    price: Decimal | None,
    slots_count: int,
    bookings_count: int,
    active_bookings_count: int,
) -> str:
    safe_title = _h(title)
    safe_description = _h(description, default="")

    return (
        f"<b>{safe_title}</b>\n\n"
        f"{safe_description}\n\n"
        f"Цена: {_format_price(price)}\n\n"
        f"Зависимости:\n"
        f"Слоты: {slots_count}\n"
        f"Записи: {bookings_count} (активные: {active_bookings_count})"
    ).strip()


async def _notify_users_about_service_cleanup(
    bot: Bot,
    tg_ids: list[int],
    *,
    service_title: str,
) -> None:
    if not tg_ids:
        return

    safe_title = _h(service_title)

    text = (
        "ℹ️ Запись отменена администратором.\n\n"
        f"Причина: услуга «{safe_title}» удалена или переоформлена."
    )
    for tg_id in tg_ids:
        try:
            await bot.send_message(chat_id=tg_id, text=text)
        except Exception as e:
            logger.warning("Service cleanup notify failed for %s: %s", tg_id, e)


@services_admin_router.message(F.text == "Услуги")
async def services_entry(message: types.Message, session: AsyncSession):
    await _show_services_list(message, session, show=0)


@services_admin_router.callback_query(ServiceAdminCB.filter(F.action == "home"))
async def back_to_admin(call: types.CallbackQuery):
    await call.answer()
    if call.message:
        await call.message.answer("Админ-панель:", reply_markup=ADMIN_KB)


@services_admin_router.callback_query(ServiceAdminCB.filter())
async def services_callbacks(
    call: types.CallbackQuery,
    callback_data: ServiceAdminCB,
    session: AsyncSession,
    state: FSMContext,
    bot: Bot,
):
    msg = call.message
    if not isinstance(msg, types.Message):
        await call.answer()
        return

    show = int(callback_data.show or 0)

    if callback_data.action == "list":
        services = await orm_get_services(session, include_inactive=bool(show))
        await _edit_or_send(msg, text="🧾 Услуги:", kb=kb_services_admin_list(services, show=show))
        await call.answer()
        return

    if callback_data.action == "open" and callback_data.service:
        s = await orm_get_service(session, callback_data.service)
        if not s:
            await call.answer("Не найдено", show_alert=True)
            return

        slots_count, bookings_count, active_bookings_count = await orm_get_service_dependency_stats(
            session, s.id
        )
        text = _service_card_text(
            title=s.title,
            description=s.description,
            price=s.price,
            slots_count=slots_count,
            bookings_count=bookings_count,
            active_bookings_count=active_bookings_count,
        )
        await _edit_or_send(
            msg,
            text=text,
            kb=kb_service_admin_card(s.id, is_active=s.is_active, show=show),
        )
        await call.answer()
        return

    if callback_data.action == "toggle" and callback_data.service:
        await orm_toggle_service_active(session, callback_data.service)
        s = await orm_get_service(session, callback_data.service)
        await call.answer("Готово ✅")
        if s:
            slots_count, bookings_count, active_bookings_count = await orm_get_service_dependency_stats(
                session, s.id
            )
            text = _service_card_text(
                title=s.title,
                description=s.description,
                price=s.price,
                slots_count=slots_count,
                bookings_count=bookings_count,
                active_bookings_count=active_bookings_count,
            )
            await _edit_or_send(
                msg,
                text=text,
                kb=kb_service_admin_card(s.id, is_active=s.is_active, show=show),
            )
        return

    if callback_data.action == "slots" and callback_data.service:
        s = await orm_get_service(session, callback_data.service)
        if not s:
            await call.answer("Услуга не найдена", show_alert=True)
            return
        page = await orm_get_timeslots_page(
            session,
            service_id=s.id,
            page=1,
            per_page=10,
            mode=2,
        )
        await _edit_or_send(
            msg,
            text=f"🕒 Слоты: {_h(s.title)}\nСтр. {page.page}/{page.pages}",
            kb=kb_admin_timeslots(s.id, page, mode=2),
        )
        await call.answer()
        return

    if callback_data.action == "del" and callback_data.service:
        s = await orm_get_service(session, callback_data.service)
        if not s:
            await call.answer("Не найдено", show_alert=True)
            return
        slots_count, bookings_count, active_bookings_count = await orm_get_service_dependency_stats(
            session, s.id
        )
        if slots_count > 0 or bookings_count > 0:
            await call.answer(
                (
                    "Нельзя удалить без очистки.\n"
                    f"Слоты: {slots_count}, записи: {bookings_count}.\n"
                    "Используй кнопку «🧹 Удалить с очисткой»."
                ),
                show_alert=True,
            )
            await _edit_or_send(
                msg,
                text=_service_card_text(
                    title=s.title,
                    description=s.description,
                    price=s.price,
                    slots_count=slots_count,
                    bookings_count=bookings_count,
                    active_bookings_count=active_bookings_count,
                ),
                kb=kb_service_admin_card(s.id, is_active=s.is_active, show=show),
            )
            return

        await orm_delete_service(session, callback_data.service)
        await call.answer("Удалено ✅")

        services = await orm_get_services(session, include_inactive=bool(show))
        await _edit_or_send(msg, text="🧾 Услуги:", kb=kb_services_admin_list(services, show=show))
        return
    

    if callback_data.action == "purge_ask" and callback_data.service:
        s = await orm_get_service(session, callback_data.service)
        if not s:
            await call.answer("Не найдено", show_alert=True)
            return
        slots_count, bookings_count, active_bookings_count = await orm_get_service_dependency_stats(
            session, s.id
        )
        text = (
            _service_card_text(
                title=s.title,
                description=s.description,
                price=s.price,
                slots_count=slots_count,
                bookings_count=bookings_count,
                active_bookings_count=active_bookings_count,
            )
            + "\n\n⚠️ Будут удалены услуга, все её слоты и все записи по этой услуге."
        )
        await _edit_or_send(
            msg,
            text=text,
            kb=kb_service_admin_purge_confirm(s.id, show=show),
        )
        await call.answer()
        return

    if callback_data.action == "purge_do" and callback_data.service:
        s = await orm_get_service(session, callback_data.service)
        if not s:
            await call.answer("Услуга уже удалена", show_alert=True)
            return

        tg_ids = await orm_get_active_booking_tg_ids_by_service(session, s.id)
        ok, deleted_slots, deleted_bookings = await orm_purge_service_with_dependencies(session, s.id)
        if not ok:
            await call.answer("Не удалось удалить услугу", show_alert=True)
            return
        await session.commit()

        await _notify_users_about_service_cleanup(bot, tg_ids, service_title=s.title)
        await call.answer(
            f"Удалено ✅ Слотов: {deleted_slots}, записей: {deleted_bookings}",
            show_alert=True,
        )

        services = await orm_get_services(session, include_inactive=bool(show))
        await _edit_or_send(msg, text="🧾 Услуги:", kb=kb_services_admin_list(services, show=show))
        return

    if callback_data.action == "add":
        await state.clear()
        await state.update_data(show=show)
        await state.set_state(AddService.title)
        await call.answer()
        if call.message:
            await call.message.answer("Введите название услуги:", reply_markup=FSM_FORM_KB)
        return

    if callback_data.action == "edit" and callback_data.service:
        s = await orm_get_service(session, callback_data.service)
        if not s:
            await call.answer("Не найдено", show_alert=True)
            return
        await state.clear()
        await state.update_data(
            service_id=s.id,
            show=show,
            old_title=s.title,
            old_description=s.description or "",
            old_price=str(s.price) if s.price is not None else "",
        )
        await state.set_state(EditService.title)
        await call.answer()
        if call.message:
            await call.message.answer(
                "✏️ Редактирование услуги\n"
                "Введите новое название.\n"
                "Правила: '.' — оставить старое, /отмена — выйти.",
                reply_markup=FSM_FORM_KB
            )
        return

    await call.answer("Неизвестное действие", show_alert=True)


# ----------------------------
# FSM: ADD SERVICE
# ----------------------------


@services_admin_router.message(
    StateFilter(
        AddService.title,
        AddService.description,
        AddService.price,
        EditService.title,
        EditService.description,
        EditService.price,
    ),
    F.text.casefold() == "назад",
)
async def svc_back(message: types.Message, state: FSMContext, session: AsyncSession):
    current_state = await state.get_state()
    if current_state is None:
        return

    data = await state.get_data()
    service_id = data.get("service_id")
    show = int(data.get("show", 0) or 0)

    if current_state == AddService.title.state:
        await state.clear()
        await _show_services_list(
            message,
            session,
            show=show,
            notice="Добавление отменено.",
        )
        return

    if current_state == AddService.description.state:
        await state.set_state(AddService.title)
        await message.answer(
            "Введите название услуги:",
            reply_markup=FSM_FORM_KB,
        )
        return

    if current_state == AddService.price.state:
        await state.set_state(AddService.description)
        await message.answer(
            "Введите описание или '.' чтобы пропустить:",
            reply_markup=FSM_FORM_KB,
        )
        return

    if current_state == EditService.title.state:
        await state.clear()
        if service_id:
            await _show_service_card(
                message,
                session,
                service_id=int(service_id),
                show=show,
                notice="Редактирование отменено.",
            )
            return
        await _show_services_list(
            message,
            session,
            show=show,
            notice="Редактирование отменено.",
        )
        return

    if current_state == EditService.description.state:
        await state.set_state(EditService.title)
        await message.answer(
            "✏️ Редактирование услуги\n"
            "Введите новое название.\n"
            "Правила: '.' — оставить старое, /отмена — выйти.",
            reply_markup=FSM_FORM_KB,
        )
        return

    if current_state == EditService.price.state:
        await state.set_state(EditService.description)
        await message.answer(
            "Введите описание или '.' чтобы оставить старое (или пусто, чтобы очистить):",
            reply_markup=FSM_FORM_KB,
        )
        return


@services_admin_router.message(
    StateFilter(AddService.title, AddService.description, AddService.price, EditService.title, EditService.description, EditService.price),
    Command("отмена"),
)
@services_admin_router.message(
    StateFilter(AddService.title, AddService.description, AddService.price, EditService.title, EditService.description, EditService.price),
    F.text.casefold() == "отмена",
)
async def svc_cancel(message: types.Message, state: FSMContext, session: AsyncSession):
    current_state = await state.get_state()
    if current_state is None:
        return

    data = await state.get_data()
    await state.clear()

    await message.answer("Ок, отменено.", reply_markup=types.ReplyKeyboardRemove())

    service_id = data.get("service_id")
    show = int(data.get("show", 0) or 0)

    if service_id:
        await _show_service_card(
            message,
            session,
            service_id=int(service_id),
            show=show,
            notice="Редактирование отменено.",
        )
        return

    await _show_services_list(
        message,
        session,
        show=show,
        notice="Добавление отменено.",
    )


@services_admin_router.message(AddService.title, F.text)
async def add_svc_title(message: types.Message, state: FSMContext):
    title = (message.text or "").strip()
    if not title:
        await message.answer("Название не может быть пустым.", reply_markup=FSM_FORM_KB)
        return
    await state.update_data(title=title)
    await state.set_state(AddService.description)
    await message.answer("Введите описание или '.' чтобы пропустить:", reply_markup=FSM_FORM_KB)


@services_admin_router.message(AddService.description, F.text)
async def add_svc_desc(message: types.Message, state: FSMContext):
    desc = (message.text or "").strip()
    await state.update_data(description=None if desc == "." else desc)
    await state.set_state(AddService.price)
    await message.answer("Введите цену (число) или '.' чтобы без цены:", reply_markup=FSM_FORM_KB)


@services_admin_router.message(AddService.price, F.text)
async def add_svc_price(message: types.Message, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    raw = (message.text or "").strip()

    price: Decimal | None = None
    if raw != ".":
        try:
            price = Decimal(raw.replace(",", ".").strip())
        except InvalidOperation:
            await message.answer("Цена должна быть числом. Пример: 1500 или 1500.50, либо '.'.", reply_markup=FSM_FORM_KB)
            return

    await orm_add_service(
        session,
        title=str(data["title"]),
        description=data.get("description"),
        price=price,
    )

    show = int(data.get("show", 0) or 0)

    await state.clear()
    await message.answer("✅ Услуга добавлена.", reply_markup=types.ReplyKeyboardRemove())
    await _show_services_list(message, session, show=show)


# ----------------------------
# FSM: EDIT SERVICE
# ----------------------------

@services_admin_router.message(EditService.title, F.text)
async def edit_svc_title(message: types.Message, state: FSMContext):
    data = await state.get_data()
    text = (message.text or "").strip()
    if text == ".":
        text = str(data.get("old_title", "")).strip()
    if not text:
        await message.answer("Название не может быть пустым.", reply_markup=FSM_FORM_KB)
        return
    await state.update_data(title=text)
    await state.set_state(EditService.description)
    await message.answer(
        "Введите описание или '.' чтобы оставить старое (или пусто, чтобы очистить):",
        reply_markup=FSM_FORM_KB,
    )


@services_admin_router.message(EditService.description, F.text)
async def edit_svc_desc(message: types.Message, state: FSMContext):
    data = await state.get_data()
    text = (message.text or "")
    if text.strip() == ".":
        text = str(data.get("old_description", ""))
    await state.update_data(description=text)
    await state.set_state(EditService.price)
    await message.answer("Введите цену, '.' — оставить старую, '-' — убрать цену:", reply_markup=FSM_FORM_KB)


@services_admin_router.message(EditService.price, F.text)
async def edit_svc_price(message: types.Message, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    raw = (message.text or "").strip()

    if raw == ".":
        old = str(data.get("old_price", "")).strip()
        price = Decimal(old) if old else None
    elif raw == "-":
        price = None
    else:
        try:
            price = Decimal(raw.replace(",", ".").strip())
        except InvalidOperation:
            await message.answer("Цена должна быть числом. Пример: 1500 или 1500.50, либо '.' или '-'.", reply_markup=FSM_FORM_KB)
            return

    service_id = int(data["service_id"])
    await orm_update_service(
        session,
        service_id,
        title=str(data.get("title")),
        description=data.get("description"),
        price=price,
    )

    show = int(data.get("show", 0) or 0)

    await state.clear()
    await message.answer("✅ Услуга обновлена.", reply_markup=types.ReplyKeyboardRemove())
    await _show_service_card(
        message,
        session,
        service_id=service_id,
        show=show,
    )


# ----------------------------
# FSM: CANCEL
# ----------------------------


