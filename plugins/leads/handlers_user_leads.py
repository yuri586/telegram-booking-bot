from __future__ import annotations

import re
from html import escape

from aiogram import F, Router, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardRemove
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database.orm_query import orm_add_lead_request
from filters.chat_types import ChatTypeFilter
from keyboards.callbacks import LeadCB
from keyboards.inline import kb_lead_confirm, kb_lead_request_types, kb_lead_success
from keyboards.reply import get_keyboard

lead_user_router = Router()
lead_user_router.message.filter(ChatTypeFilter(["private"]))

FSM_FORM_KB = get_keyboard(
    "Назад",
    "Отмена",
    placeholder="Можно вернуться или отменить",
    sizes=(2,),
)

REQUEST_TYPE_OPTIONS: list[tuple[str, str]] = [
    ("Банкротство", "bankruptcy"),
    ("Семейный вопрос", "family"),
    ("Жильё / недвижимость", "housing"),
    ("Трудовой спор", "labor"),
    ("Договор / деньги", "money"),
    ("Другое", "other"),
]

REQUEST_TYPE_LABELS: dict[str, str] = {value: text for text, value in REQUEST_TYPE_OPTIONS}

USERNAME_RE = re.compile(r"^@[A-Za-z0-9_]{5,32}$")
PHONE_RE = re.compile(r"^[+]?\d{7,15}$")


class LeadFSM(StatesGroup):
    waiting_name = State()
    waiting_contact = State()
    waiting_message = State()
    waiting_confirm = State()


def request_type_label(value: str | None) -> str:
    return REQUEST_TYPE_LABELS.get((value or "").strip(), "Другое")


def normalize_lead_contact(raw: str) -> str | None:
    text = (raw or "").strip()
    if not text:
        return None

    if USERNAME_RE.fullmatch(text):
        return text

    cleaned = re.sub(r"[^\d+]", "", text)
    if cleaned.count("+") > 1 or ("+" in cleaned and not cleaned.startswith("+")):
        return None

    digits = cleaned[1:] if cleaned.startswith("+") else cleaned
    if not digits or not digits.isdigit():
        return None

    normalized = f"+{digits}" if cleaned.startswith("+") else digits
    if not PHONE_RE.fullmatch(normalized):
        return None

    return normalized


def build_lead_message(request_type: str, description: str) -> str:
    lead_type = request_type_label(request_type)
    text = (description or "").strip()
    return f"Тип запроса: {lead_type}\n\nОписание:\n{text}"


async def save_lead_request(
    session: AsyncSession,
    *,
    profile_slug: str,
    tg_id: int,
    request_type: str,
    name: str,
    contact: str,
    description: str,
):
    return await orm_add_lead_request(
        session,
        profile_slug=profile_slug,
        tg_id=tg_id,
        name=name.strip(),
        contact=contact.strip(),
        message=build_lead_message(request_type, description),
    )


def _h(value: str | None, default: str = "—") -> str:
    text = (value or "").strip()
    return escape(text or default)


def _confirm_text(data: dict[str, str]) -> str:
    return (
        "Проверьте заявку перед отправкой.\n\n"
        f"Тип запроса: {_h(request_type_label(data.get('request_type')))}\n"
        f"Имя: {_h(data.get('name'))}\n"
        f"Контакт: {_h(data.get('contact'))}\n\n"
        f"Описание:\n{_h(data.get('description'))}"
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


async def _show_request_type_screen(
    msg: types.Message,
    *,
    notice: str | None = None,
) -> None:
    text = "📝 Оставить заявку\n\nВыберите тип запроса:"
    if notice:
        text = f"{notice}\n\n{text}"

    await _edit_or_send(
        msg,
        text=text,
        kb=kb_lead_request_types(REQUEST_TYPE_OPTIONS),
    )


@lead_user_router.callback_query(LeadCB.filter(F.action == "start"))
async def lead_start(
    call: types.CallbackQuery,
    state: FSMContext,
) -> None:
    msg = call.message
    if not isinstance(msg, types.Message):
        await call.answer()
        return

    await state.clear()
    await _show_request_type_screen(msg)
    await call.answer()


@lead_user_router.callback_query(LeadCB.filter(F.action == "restart"))
async def lead_restart(
    call: types.CallbackQuery,
    state: FSMContext,
) -> None:
    msg = call.message
    if not isinstance(msg, types.Message):
        await call.answer()
        return

    await state.clear()
    await _show_request_type_screen(msg, notice="Начнём заново.")
    await call.answer()


@lead_user_router.callback_query(LeadCB.filter(F.action == "cancel"))
async def lead_cancel_callback(
    call: types.CallbackQuery,
    state: FSMContext,
) -> None:
    msg = call.message
    if not isinstance(msg, types.Message):
        await call.answer()
        return

    await state.clear()
    await _edit_or_send(
        msg,
        text="Заявка не отправлена.",
        kb=kb_lead_success(),
    )
    await call.answer("Отменено.")


@lead_user_router.callback_query(LeadCB.filter(F.action == "type"))
async def lead_select_type(
    call: types.CallbackQuery,
    callback_data: LeadCB,
    state: FSMContext,
) -> None:
    msg = call.message
    if not isinstance(msg, types.Message):
        await call.answer()
        return

    if not callback_data.request_type:
        await call.answer("Не выбран тип запроса.", show_alert=True)
        return

    await state.clear()
    await state.update_data(request_type=callback_data.request_type)
    await state.set_state(LeadFSM.waiting_name)

    try:
        await msg.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest:
        pass

    await msg.answer(
        f"Тип запроса: {request_type_label(callback_data.request_type)}\n\n"
        "Как к вам обращаться?",
        reply_markup=FSM_FORM_KB,
    )
    await call.answer()


@lead_user_router.callback_query(LeadCB.filter(F.action == "send"))
async def lead_send(
    call: types.CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    msg = call.message
    if not isinstance(msg, types.Message):
        await call.answer()
        return

    data = await state.get_data()

    request_type = str(data.get("request_type") or "").strip()
    name = str(data.get("name") or "").strip()
    contact = str(data.get("contact") or "").strip()
    description = str(data.get("description") or "").strip()

    if not request_type or not name or not contact or not description:
        await state.clear()
        await _edit_or_send(
            msg,
            text="Сессия заявки устарела. Начните заново.",
            kb=kb_lead_success(),
        )
        await call.answer("Сессия устарела.", show_alert=True)
        return

    lead = await save_lead_request(
        session,
        profile_slug=settings.DEMO_PROFILE,
        tg_id=call.from_user.id,
        request_type=request_type,
        name=name,
        contact=contact,
        description=description,
    )

    await state.clear()

    await _edit_or_send(
        msg,
        text=(
            f"✅ Заявка #{lead.id} отправлена.\n\n"
            "Юрист получит ваше обращение и свяжется с вами после просмотра заявки."
        ),
        kb=kb_lead_success(),
    )
    await call.answer("Отправлено ✅")


@lead_user_router.message(
    StateFilter(
        LeadFSM.waiting_name,
        LeadFSM.waiting_contact,
        LeadFSM.waiting_message,
        LeadFSM.waiting_confirm,
    ),
    F.text.casefold() == "отмена",
)
async def lead_cancel_message(
    message: types.Message,
    state: FSMContext,
) -> None:
    await state.clear()
    await message.answer("Ок, отменено.", reply_markup=ReplyKeyboardRemove())
    await message.answer("Заявка не отправлена.", reply_markup=kb_lead_success())


@lead_user_router.message(LeadFSM.waiting_name, F.text.casefold() == "назад")
async def lead_back_to_type(
    message: types.Message,
    state: FSMContext,
) -> None:
    await state.clear()
    await message.answer("Возвращаемся к выбору типа запроса.", reply_markup=ReplyKeyboardRemove())
    await message.answer(
        "📝 Оставить заявку\n\nВыберите тип запроса:",
        reply_markup=kb_lead_request_types(REQUEST_TYPE_OPTIONS),
    )


@lead_user_router.message(LeadFSM.waiting_contact, F.text.casefold() == "назад")
async def lead_back_to_name(
    message: types.Message,
    state: FSMContext,
) -> None:
    await state.set_state(LeadFSM.waiting_name)
    await message.answer("Как к вам обращаться?", reply_markup=FSM_FORM_KB)


@lead_user_router.message(LeadFSM.waiting_message, F.text.casefold() == "назад")
async def lead_back_to_contact(
    message: types.Message,
    state: FSMContext,
) -> None:
    await state.set_state(LeadFSM.waiting_contact)
    await message.answer(
        "Как с вами лучше связаться?\n"
        "Введите телефон или @username.",
        reply_markup=FSM_FORM_KB,
    )


@lead_user_router.message(LeadFSM.waiting_confirm, F.text.casefold() == "назад")
async def lead_back_to_message(
    message: types.Message,
    state: FSMContext,
) -> None:
    await state.set_state(LeadFSM.waiting_message)
    await message.answer(
        "Коротко опишите ситуацию.\n"
        "Без паспортных данных и лишних персональных деталей.",
        reply_markup=FSM_FORM_KB,
    )


@lead_user_router.message(LeadFSM.waiting_name, F.text)
async def lead_name_step(
    message: types.Message,
    state: FSMContext,
) -> None:
    name = (message.text or "").strip()
    if not name:
        await message.answer("Имя не может быть пустым.", reply_markup=FSM_FORM_KB)
        return

    await state.update_data(name=name)
    await state.set_state(LeadFSM.waiting_contact)
    await message.answer(
        "Как с вами лучше связаться?\n"
        "Введите телефон или @username.",
        reply_markup=FSM_FORM_KB,
    )


@lead_user_router.message(LeadFSM.waiting_contact, F.text)
async def lead_contact_step(
    message: types.Message,
    state: FSMContext,
) -> None:
    contact = normalize_lead_contact(message.text or "")
    if not contact:
        await message.answer(
            "Введите корректный телефон или @username.\n"
            "Примеры: +79991234567 или @username",
            reply_markup=FSM_FORM_KB,
        )
        return

    await state.update_data(contact=contact)
    await state.set_state(LeadFSM.waiting_message)
    await message.answer(
        "Коротко опишите ситуацию.\n"
        "Без паспортных данных и лишних персональных деталей.",
        reply_markup=FSM_FORM_KB,
    )


@lead_user_router.message(LeadFSM.waiting_message, F.text)
async def lead_message_step(
    message: types.Message,
    state: FSMContext,
) -> None:
    description = (message.text or "").strip()
    if not description:
        await message.answer("Описание не может быть пустым.", reply_markup=FSM_FORM_KB)
        return

    await state.update_data(description=description)
    await state.set_state(LeadFSM.waiting_confirm)

    data = await state.get_data()

    await message.answer("Проверьте заявку ниже.", reply_markup=ReplyKeyboardRemove())
    await message.answer(
        _confirm_text(data),
        reply_markup=kb_lead_confirm(),
    )


@lead_user_router.message(LeadFSM.waiting_confirm, F.text)
async def lead_waiting_confirm_text(
    message: types.Message,
) -> None:
    await message.answer("Нажмите «✅ Отправить», «🔁 Заполнить заново» или «❌ Отмена» под заявкой.")