from __future__ import annotations

import logging

from aiogram import F, Router, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InputMediaPhoto
from sqlalchemy.ext.asyncio import AsyncSession

from database.orm_query import (
    orm_add_item,
    orm_delete_item,
    orm_get_banner,
    orm_get_item,
    orm_get_items_page,
    orm_get_section,
    orm_get_sections,
    orm_set_banner_description,
    orm_set_banner_photo,
    orm_set_section_description,
    orm_set_section_photo,
    orm_set_section_title,
    orm_toggle_item_active,
    orm_update_item,
)
from filters.chat_types import ChatTypeFilter, IsAdmin
from keyboards.admin_reply import ADMIN_KB
from keyboards.callbacks import AdminCB, BannerAdminCB
from keyboards.inline import (
    kb_admin_banner_card,
    kb_admin_banners,
    kb_admin_item_card,
    kb_admin_items,
    kb_admin_section_card,
    kb_admin_sections,
)
from keyboards.reply import get_keyboard

logger = logging.getLogger(__name__)

admin_cms_router = Router()
admin_cms_router.message.filter(ChatTypeFilter(["private"]), IsAdmin())
admin_cms_router.callback_query.filter(IsAdmin())

FSM_FORM_KB = get_keyboard(
    "Назад",
    "Отмена",
    placeholder="Можно вернуться или отменить",
    sizes=(2,),
)


def _cap(text: str, limit: int = 1024) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"

async def _section_items_title(
    session: AsyncSession,
    *,
    section_id: int,
    page_num: int,
    pages_total: int,
) -> str:
    section = await orm_get_section(session, section_id)
    section_title = section.title if section else "Без названия"
    return f"🧩 Элементы раздела: {section_title}\nСтраница {page_num}/{pages_total}"

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

async def _show_admin_item(
    msg: types.Message,
    *,
    session: AsyncSession,
    section_id: int,
    item_id: int,
    p: int = 1,
    mode: int = 0,
    notice: str | None = None,
) -> None:
    item = await orm_get_item(session, item_id)
    if not item:
        await msg.answer("Элемент не найден.", reply_markup=ADMIN_KB)
        return

    title = item.title or "Без названия"
    body = item.body or ""
    prefix = f"{notice}\n\n" if notice else ""
    text = f"{prefix}<b>{title}</b>\n\n{body}".strip()

    kb = kb_admin_item_card(
        section_id,
        item.id,
        p,
        is_active=item.is_active,
        mode=mode,
    )

    try:
        if item.photo:
            await msg.answer_photo(
                photo=item.photo,
                caption=_cap(text),
                reply_markup=kb,
            )
        else:
            await msg.answer(
                _cap(text),
                reply_markup=kb,
            )
    except TelegramBadRequest:
        await msg.answer(
            _cap(text),
            reply_markup=kb,
        )


async def _show_admin_items_list(
    msg: types.Message,
    *,
    session: AsyncSession,
    section_id: int,
    p: int = 1,
    mode: int = 0,
    notice: str | None = None,
) -> None:
    page = await orm_get_items_page(
        session,
        section_id=section_id,
        page=p,
        per_page=6,
        mode=mode,
    )
    text = await _section_items_title(
        session,
        section_id=section_id,
        page_num=page.page,
        pages_total=page.pages,
    )
    if notice:
        text = f"{notice}\n\n{text}"

    await msg.answer(
        text,
        reply_markup=kb_admin_items(section_id, page, mode=mode),
    )

async def _show_admin_banner(
    msg: types.Message,
    *,
    page: str,
    session: AsyncSession,
    notice: str | None = None,
) -> None:
    banner = await orm_get_banner(session, page)
    if not banner:
        await msg.answer("Страница не найдена.", reply_markup=ADMIN_KB)
        return

    title_map = {
        "main": "🏠 Главная",
        "about": "ℹ️ О проекте",
        "help": "❓ Помощь",
        "contacts": "📞 Контакты",
    }
    title = title_map.get(page, page)

    body = banner.description or "—"
    prefix = f"{notice}\n\n" if notice else ""
    text = f"{prefix}<b>{title}</b>\n\n{body}"
    kb = kb_admin_banner_card(page)

    try:
        if banner.photo:
            await msg.answer_photo(
                photo=banner.photo,
                caption=_cap(text),
                reply_markup=kb,
            )
        else:
            await msg.answer(
                _cap(text),
                reply_markup=kb,
            )
    except TelegramBadRequest:
        await msg.answer(
            _cap(text),
            reply_markup=kb,
        )

async def _show_admin_section(
    msg: types.Message,
    *,
    session: AsyncSession,
    section_id: int,
    notice: str | None = None,
) -> None:
    section = await orm_get_section(session, section_id)
    if not section:
        await msg.answer("Раздел не найден.", reply_markup=ADMIN_KB)
        return

    body = section.description or "—"
    prefix = f"{notice}\n\n" if notice else ""
    text = f"{prefix}<b>{section.title}</b>\n\n{body}"
    kb = kb_admin_section_card(section.id)

    try:
        if section.photo:
            await msg.answer_photo(
                photo=section.photo,
                caption=_cap(text),
                reply_markup=kb,
            )
        else:
            await msg.answer(
                _cap(text),
                reply_markup=kb,
            )
    except TelegramBadRequest:
        await msg.answer(
            _cap(text),
            reply_markup=kb,
        )

class AddItem(StatesGroup):
    title = State()
    body = State()
    photo = State()
    sort_order = State()


class EditItem(StatesGroup):
    title = State()
    body = State()
    photo = State()
    sort_order = State()

class EditBanner(StatesGroup):
    description = State()
    photo = State()

class EditSection(StatesGroup):
    title = State()
    description = State()
    photo = State()


@admin_cms_router.message(Command("admin"))
async def admin_home(message: types.Message):
    await message.answer("Админ-панель:", reply_markup=ADMIN_KB)



@admin_cms_router.message(F.text == "Разделы")
async def cms_entry(message: types.Message, session: AsyncSession):
    sections = await orm_get_sections(session)
    if not sections:
        await message.answer(
            "Разделов пока нет. Сначала заполните демо-данные или добавьте раздел в базу данных.",
            reply_markup=ADMIN_KB,
        )
        return

    await message.answer("Открываю разделы…", reply_markup=types.ReplyKeyboardRemove())
    await message.answer("Выберите раздел:", reply_markup=kb_admin_sections(sections))

@admin_cms_router.message(Command("banners"))
async def admin_banners_cmd(message: types.Message):
    await message.answer("Выберите страницу:", reply_markup=kb_admin_banners())

@admin_cms_router.message(F.text == "Страницы")
async def admin_banners_button(message: types.Message):
    await message.answer("Выберите страницу:", reply_markup=kb_admin_banners())


@admin_cms_router.callback_query(AdminCB.filter())
async def cms_callbacks(
    call: types.CallbackQuery,
    callback_data: AdminCB,
    session: AsyncSession,
    state: FSMContext,
):
    msg = call.message
    if not isinstance(msg, types.Message):
        await call.answer()
        return

    action = callback_data.action
    mode = int(getattr(callback_data, "mode", 0) or 0)  # 0/1/2

    # -----------------------------
    # HOME
    # -----------------------------
    if action == "home":
        await call.answer()
        await msg.answer("Админ-панель:", reply_markup=ADMIN_KB)
        return

    # -----------------------------
    # SECTIONS LIST
    # -----------------------------
    if action == "sections":
        sections = await orm_get_sections(session)
        await call.answer()
        await msg.answer("Выберите раздел:", reply_markup=kb_admin_sections(sections))
        return
    
    if action == "section_open":
        if not callback_data.section:
            await call.answer("Раздел не выбран.", show_alert=True)
            return

        await call.answer()
        await _show_admin_section(
            msg,
            session=session,
            section_id=callback_data.section,
        )
        return

    if action == "section_edit_title":
        if not callback_data.section:
            await call.answer("Раздел не выбран.", show_alert=True)
            return

        await state.clear()
        await state.update_data(section_id=callback_data.section)
        await state.set_state(EditSection.title)

        await call.answer()
        await msg.answer(
            "Введите новый заголовок раздела.\n"
            "'.' — оставить текущее значение",
            reply_markup=FSM_FORM_KB,
        )
        return

    if action == "section_edit_description":
        if not callback_data.section:
            await call.answer("Раздел не выбран.", show_alert=True)
            return

        await state.clear()
        await state.update_data(section_id=callback_data.section)
        await state.set_state(EditSection.description)

        await call.answer()
        await msg.answer(
            "Введите новое описание раздела.\n"
            "'.' — оставить текущее значение\n"
            "'-' — очистить описание",
            reply_markup=FSM_FORM_KB,
        )
        return

    if action == "section_edit_photo":
        if not callback_data.section:
            await call.answer("Раздел не выбран.", show_alert=True)
            return

        await state.clear()
        await state.update_data(section_id=callback_data.section)
        await state.set_state(EditSection.photo)

        await call.answer()
        await msg.answer(
            "Отправьте новое фото раздела.\n"
            "'.' — оставить текущее\n"
            "'-' — удалить фото",
            reply_markup=FSM_FORM_KB,
        )
        return

    # -----------------------------
    # TOGGLE SHOW HIDDEN (0<->1) then open items list
    # -----------------------------
    if action == "toggle_mode":
        if not callback_data.section:
            await call.answer("Раздел не выбран.", show_alert=True)
            return

        new_mode = (mode + 1) % 3  # 0->1->2->0

        page = await orm_get_items_page(
            session,
            section_id=callback_data.section,
            page=callback_data.p,
            per_page=6,
            mode=new_mode,
        )
        text = await _section_items_title(
            session,
            section_id=callback_data.section,
            page_num=page.page,
            pages_total=page.pages,
        )
        kb = kb_admin_items(callback_data.section, page, mode=new_mode)

        try:
            if msg.photo:
                await msg.edit_caption(caption=text, reply_markup=kb)
            else:
                await msg.edit_text(text=text, reply_markup=kb)
        except TelegramBadRequest:
            await msg.answer(text, reply_markup=kb)

        await call.answer()
        return

    # -----------------------------
    # ITEMS LIST
    # -----------------------------
    if action == "items":
        if not callback_data.section:
            await call.answer("Раздел не выбран.", show_alert=True)
            return

        page = await orm_get_items_page(
            session,
            section_id=callback_data.section,
            page=callback_data.p,
            per_page=6,
            mode=mode,
        )

        text = await _section_items_title(
            session,
            section_id=callback_data.section,
            page_num=page.page,
            pages_total=page.pages,
        )
        kb = kb_admin_items(callback_data.section, page, mode=mode)

        await _edit_or_send(msg, text=text, kb=kb)

        await call.answer()
        return

    # -----------------------------
    # OPEN ITEM CARD
    # -----------------------------
    if action == "open":
        if not callback_data.section or not callback_data.item:
            await call.answer("Не выбран элемент или раздел.", show_alert=True)
            return

        item = await orm_get_item(session, callback_data.item)
        if not item:
            await call.answer("Элемент не найден.", show_alert=True)
            return

        title = item.title or "Без названия"
        body = item.body or ""
        text = f"<b>{title}</b>\n\n{body}".strip()
        kb = kb_admin_item_card(
            callback_data.section,
            item.id,
            callback_data.p,
            is_active=item.is_active,
            mode=mode,
        )

        try:
            if item.photo:
                cap = _cap(text)
                if msg.photo:
                    await msg.edit_media(InputMediaPhoto(media=item.photo, caption=cap), reply_markup=kb)
                else:
                    await msg.answer_photo(photo=item.photo, caption=cap, reply_markup=kb)
            else:
                if msg.photo:
                    await msg.edit_caption(caption=_cap(text), reply_markup=kb)
                else:
                    await msg.edit_text(text=_cap(text), reply_markup=kb)
        except TelegramBadRequest as e:
            logger.warning("Admin open item failed: %s", e)

        await call.answer()
        return

    # -----------------------------
    # DELETE ITEM -> back to list
    # -----------------------------
    if action == "del":
        if not callback_data.item or not callback_data.section:
            await call.answer("Не выбран элемент или раздел.", show_alert=True)
            return

        await orm_delete_item(session, callback_data.item)
        await call.answer("Элемент удалён ✅")

        page = await orm_get_items_page(
            session,
            section_id=callback_data.section,
            page=callback_data.p,
            per_page=6,
            mode=mode,
        )
        text = await _section_items_title(
            session,
            section_id=callback_data.section,
            page_num=page.page,
            pages_total=page.pages,
        )
        kb = kb_admin_items(callback_data.section, page, mode=mode)

        try:
            if msg.photo:
                await msg.edit_caption(caption=text, reply_markup=kb)
            else:
                await msg.edit_text(text=text, reply_markup=kb)
        except TelegramBadRequest:
            await msg.answer(text, reply_markup=kb)

        return

    # -----------------------------
    # TOGGLE ACTIVE (hide/show) -> reopen card (doesn't disappear)
    # -----------------------------
    if action == "toggle":
        if not callback_data.item or not callback_data.section:
            await call.answer("Не выбран элемент или раздел.", show_alert=True)
            return

        await orm_toggle_item_active(session, callback_data.item)
        await call.answer("Статус элемента обновлён ✅")

        item = await orm_get_item(session, callback_data.item)
        if not item:
            return
        if mode == 0 and not item.is_active:
            mode = 2

        title = item.title or "Без названия"
        body = item.body or ""
        text = f"<b>{title}</b>\n\n{body}".strip()
        kb = kb_admin_item_card(
            callback_data.section,
            item.id,
            callback_data.p,
            is_active=item.is_active,
            mode=mode,
        )

        try:
            if item.photo:
                cap = _cap(text)
                if msg.photo:
                    await msg.edit_media(InputMediaPhoto(media=item.photo, caption=cap), reply_markup=kb)
                else:
                    await msg.answer_photo(photo=item.photo, caption=cap, reply_markup=kb)
            else:
                if msg.photo:
                    await msg.edit_caption(caption=_cap(text), reply_markup=kb)
                else:
                    await msg.edit_text(text=_cap(text), reply_markup=kb)
        except TelegramBadRequest as e:
            logger.warning("Admin toggle failed: %s", e)

        return

    # -----------------------------
    # ADD ITEM (FSM)
    # -----------------------------
    if action == "add":
        if not callback_data.section:
            await call.answer("Раздел не выбран", show_alert=True)
            return

        await state.clear()
        await state.update_data(
            section_id=callback_data.section,
            p=callback_data.p,
            mode=mode,
        )
        await state.set_state(AddItem.title)

        await call.answer()
        await msg.answer("Введите заголовок элемента:", reply_markup=FSM_FORM_KB)
        return

    # -----------------------------
    # EDIT ITEM (FSM)
    # -----------------------------
    if action == "edit":
        if not callback_data.item or not callback_data.section:
            await call.answer("Не выбран элемент или раздел.", show_alert=True)
            return

        item = await orm_get_item(session, callback_data.item)
        if not item:
            await call.answer("Элемент не найден.", show_alert=True)
            return

        await state.clear()
        await state.update_data(
            section_id=callback_data.section,
            item_id=item.id,
            p=callback_data.p,
            mode=mode,
            old_title=item.title,
            old_body=item.body or "",
            old_photo=item.photo or "",
            old_sort_order=item.sort_order,
        )

        await state.set_state(EditItem.title)
        await call.answer()

        await msg.answer(
            "✏️ Редактирование элемента\n\n"
            "Введите новый заголовок.\n"
            "'.' — оставить текущее значение\n"
            "/отмена — выйти",
            reply_markup=FSM_FORM_KB,
        )
        return

    await call.answer("Неизвестное действие", show_alert=True)
    return


@admin_cms_router.callback_query(BannerAdminCB.filter())
async def banner_callbacks(
    call: types.CallbackQuery,
    callback_data: BannerAdminCB,
    session: AsyncSession,
    state: FSMContext,
):
    msg = call.message
    if not isinstance(msg, types.Message):
        await call.answer()
        return

    action = callback_data.action
    page = callback_data.page

    if action == "home":
        await call.answer()
        await msg.answer("Админ-панель:", reply_markup=ADMIN_KB)
        return

    if action == "list":
        await call.answer()
        await _edit_or_send(msg, text="Выберите страницу:", kb=kb_admin_banners())
        return

    if action == "open":
        if not page:
            await call.answer("Страница не выбрана.", show_alert=True)
            return

        banner = await orm_get_banner(session, page)
        if not banner:
            await call.answer("Страница не найдена", show_alert=True)
            return

        title_map = {
            "main": "🏠 Главная",
            "about": "ℹ️ О проекте",
            "help": "❓ Помощь",
            "contacts": "📞 Контакты",
        }
        title = title_map.get(page, page)
        text = f"<b>{title}</b>\n\n{banner.description or '—'}"
        kb = kb_admin_banner_card(page)

        try:
            if banner.photo:
                cap = _cap(text)
                if msg.photo:
                    await msg.edit_media(
                        InputMediaPhoto(media=banner.photo, caption=cap),
                        reply_markup=kb,
                    )
                else:
                    await msg.answer_photo(
                        photo=banner.photo,
                        caption=cap,
                        reply_markup=kb,
                    )
            else:
                if msg.photo:
                    await msg.edit_caption(caption=_cap(text), reply_markup=kb)
                else:
                    await msg.edit_text(text=_cap(text), reply_markup=kb)
        except TelegramBadRequest:
            await msg.answer(_cap(text), reply_markup=kb)

        await call.answer()
        return

    if action == "edit_desc":
        if not page:
            await call.answer("Страница не выбрана.", show_alert=True)
            return

        await state.clear()
        await state.update_data(page=page)
        await state.set_state(EditBanner.description)

        await call.answer()
        await msg.answer(
            "Введите новое описание.\n"
            "'.' — оставить текущее значение\n"
            "'-' — очистить текст",
            reply_markup=FSM_FORM_KB,
        )
        return

    if action == "edit_photo":
        if not page:
            await call.answer("Страница не выбрана.", show_alert=True)
            return

        await state.clear()
        await state.update_data(page=page)
        await state.set_state(EditBanner.photo)

        await call.answer()
        await msg.answer(
            "Отправьте новое фото.\n"
            "'.' — оставить текущее\n"
            "'-' — удалить фото",
            reply_markup=FSM_FORM_KB,
        )
        return

    await call.answer("Неизвестное действие", show_alert=True)

# -----------------------------
# FSM: ADD ITEM
# -----------------------------

@admin_cms_router.message(
    StateFilter(
        AddItem.title,
        AddItem.body,
        AddItem.photo,
        AddItem.sort_order,
        EditItem.title,
        EditItem.body,
        EditItem.photo,
        EditItem.sort_order,
        EditBanner.description,
        EditBanner.photo,
        EditSection.title,
        EditSection.description,
        EditSection.photo,
    ),
    F.text.casefold() == "назад",
)
async def cms_back(message: types.Message, state: FSMContext, session: AsyncSession):
    current_state = await state.get_state()
    if current_state is None:
        return

    data = await state.get_data()

    page = data.get("page")
    item_id = data.get("item_id")
    section_id = data.get("section_id")
    p = int(data.get("p", 1) or 1)
    mode = int(data.get("mode", 0) or 0)

    if current_state in {
        EditSection.title.state,
        EditSection.description.state,
        EditSection.photo.state,
    }:
        await state.clear()
        if section_id:
            await _show_admin_section(
                message,
                session=session,
                section_id=int(section_id),
                notice="Редактирование раздела отменено.",
            )
            return
        await message.answer("Админ-панель:", reply_markup=ADMIN_KB)
        return
    
    if current_state == AddItem.title.state:
        await state.clear()
        if section_id:
            await _show_admin_items_list(
                message,
                session=session,
                section_id=int(section_id),
                p=p,
                mode=mode,
                notice="Добавление отменено.",
            )
            return
        await message.answer("Админ-панель:", reply_markup=ADMIN_KB)
        return

    if current_state == AddItem.body.state:
        await state.set_state(AddItem.title)
        await message.answer(
            "Введите заголовок элемента:",
            reply_markup=FSM_FORM_KB,
        )
        return

    if current_state == AddItem.photo.state:
        await state.set_state(AddItem.body)
        await message.answer(
            "Введите текст элемента или '.' чтобы пропустить:",
            reply_markup=FSM_FORM_KB,
        )
        return

    if current_state == AddItem.sort_order.state:
        await state.set_state(AddItem.photo)
        await message.answer(
            "Отправьте фото или '.' чтобы без фото:",
            reply_markup=FSM_FORM_KB,
        )
        return

    if current_state == EditItem.title.state:
        await state.clear()
        if item_id and section_id:
            await _show_admin_item(
                message,
                session=session,
                section_id=int(section_id),
                item_id=int(item_id),
                p=p,
                mode=mode,
                notice="Редактирование отменено.",
            )
            return
        await message.answer("Админ-панель:", reply_markup=ADMIN_KB)
        return

    if current_state == EditItem.body.state:
        await state.set_state(EditItem.title)
        await message.answer(
            "✏️ Редактирование элемента\n\n"
            "Введите новый заголовок.\n"
            "'.' — оставить текущее значение\n"
            "/отмена — выйти",
            reply_markup=FSM_FORM_KB,
        )
        return

    if current_state == EditItem.photo.state:
        await state.set_state(EditItem.body)
        await message.answer(
            "Введите новый текст.\n"
            "'.' — оставить текущее значение\n"
            "'-' — очистить текст",
            reply_markup=FSM_FORM_KB,
        )
        return

    if current_state == EditItem.sort_order.state:
        await state.set_state(EditItem.photo)
        await message.answer(
            "Отправьте новое фото.\n"
            "'.' — оставить текущее\n"
            "'-' — удалить фото",
            reply_markup=FSM_FORM_KB,
        )
        return

    if current_state in {EditBanner.description.state, EditBanner.photo.state}:
        await state.clear()
        if page:
            await _show_admin_banner(
                message,
                page=str(page),
                session=session,
                notice="Редактирование отменено.",
            )
            return
        await message.answer("Админ-панель:", reply_markup=ADMIN_KB)


@admin_cms_router.message(
    StateFilter(
        AddItem.title,
        AddItem.body,
        AddItem.photo,
        AddItem.sort_order,
        EditItem.title,
        EditItem.body,
        EditItem.photo,
        EditItem.sort_order,
        EditBanner.description,
        EditBanner.photo,
        EditSection.title,
        EditSection.description,
        EditSection.photo,
    ),
    Command("отмена"),
)
@admin_cms_router.message(
    StateFilter(
        AddItem.title,
        AddItem.body,
        AddItem.photo,
        AddItem.sort_order,
        EditItem.title,
        EditItem.body,
        EditItem.photo,
        EditItem.sort_order,
        EditBanner.description,
        EditBanner.photo,
        EditSection.title,
        EditSection.description,
        EditSection.photo,
    ),
    F.text.casefold() == "отмена",
)
async def cms_cancel(message: types.Message, state: FSMContext, session: AsyncSession):
    current_state = await state.get_state()
    if current_state is None:
        return

    data = await state.get_data()
    await state.clear()

    await message.answer("Действие отменено.", reply_markup=types.ReplyKeyboardRemove())

    page = data.get("page")
    item_id = data.get("item_id")
    section_id = data.get("section_id")
    p = int(data.get("p", 1) or 1)
    mode = int(data.get("mode", 0) or 0)

    if page:
        await _show_admin_banner(
            message,
            page=str(page),
            session=session,
            notice="Редактирование отменено.",
        )
        return
    if current_state in {
        EditSection.title.state,
        EditSection.description.state,
        EditSection.photo.state,
    }:
        if section_id:
            await _show_admin_section(
                message,
                session=session,
                section_id=int(section_id),
                notice="Редактирование раздела отменено.",
            )
            return

    if item_id and section_id:
        await _show_admin_item(
            message,
            session=session,
            section_id=int(section_id),
            item_id=int(item_id),
            p=p,
            mode=mode,
            notice="Редактирование отменено.",
        )
        return

    if section_id:
        await _show_admin_items_list(
            message,
            session=session,
            section_id=int(section_id),
            p=p,
            mode=mode,
            notice="Добавление отменено.",
        )
        return

    await message.answer("Админ-панель:", reply_markup=ADMIN_KB)


@admin_cms_router.message(AddItem.title, F.text)
async def add_item_title(message: types.Message, state: FSMContext):
    title = (message.text or "").strip()
    if not title:
        await message.answer("Заголовок не может быть пустым. Введите ещё раз.", reply_markup=FSM_FORM_KB)
        return
    await state.update_data(title=title)
    await state.set_state(AddItem.body)
    await message.answer("Введите текст элемента или '.' чтобы пропустить:", reply_markup=FSM_FORM_KB)


@admin_cms_router.message(AddItem.body, F.text)
async def add_item_body(message: types.Message, state: FSMContext):
    body: str | None = (message.text or "").strip()
    if body == ".":
        body = None
    await state.update_data(body=body)
    await state.set_state(AddItem.photo)
    await message.answer("Отправьте фото или '.' чтобы без фото:", reply_markup=FSM_FORM_KB)


@admin_cms_router.message(AddItem.photo, F.photo)
async def add_item_photo(message: types.Message, state: FSMContext):
    photo = message.photo[-1].file_id if message.photo else None
    await state.update_data(photo=photo)
    await state.set_state(AddItem.sort_order)
    await message.answer(
        "Введите порядок сортировки (число, например 0, 10, 20):",
        reply_markup=FSM_FORM_KB,
    )


@admin_cms_router.message(AddItem.photo, F.text == ".")
async def add_item_photo_skip(message: types.Message, state: FSMContext):
    await state.update_data(photo=None)
    await state.set_state(AddItem.sort_order)
    await message.answer(
        "Введите порядок сортировки (число, например 0, 10, 20):",
        reply_markup=FSM_FORM_KB,
    )


@admin_cms_router.message(AddItem.sort_order, F.text)
async def add_item_finish(message: types.Message, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    section_id = int(data["section_id"])

    raw = (message.text or "").strip()
    try:
        sort_order = int(raw)
    except ValueError:
        await message.answer(
            "Введите число. Например: 0, 10, 20.",
            reply_markup=FSM_FORM_KB,
        )
        return

    item = await orm_add_item(
        session,
        section_id=section_id,
        title=str(data["title"]),
        body=data.get("body"),
        photo=data.get("photo"),
        sort_order=sort_order,
    )

    p = int(data.get("p", 1) or 1)
    mode = int(data.get("mode", 0) or 0)

    await state.clear()

    await message.answer(
        "✅ Элемент добавлен.",
        reply_markup=types.ReplyKeyboardRemove(),
    )

    await _show_admin_item(
        message,
        session=session,
        section_id=section_id,
        item_id=item.id,
        p=p,
        mode=mode,
    )


# -----------------------------
# FSM: EDIT ITEM
# -----------------------------
@admin_cms_router.message(EditItem.title, F.text)
async def edit_item_title(message: types.Message, state: FSMContext):
    data = await state.get_data()
    text = (message.text or "").strip()

    if text == ".":
        text = str(data.get("old_title", "")).strip()

    if not text:
        await message.answer(
            "Заголовок не может быть пустым. Введите ещё раз или нажмите '.'.",
            reply_markup=FSM_FORM_KB,
        )
        return

    await state.update_data(title=text)
    await state.set_state(EditItem.body)
    await message.answer(
        "Введите новый текст.\n"
        "'.' — оставить текущее значение\n"
        "'-' — очистить текст",
        reply_markup=FSM_FORM_KB,
    )


@admin_cms_router.message(EditItem.body, F.text)
async def edit_item_body(message: types.Message, state: FSMContext):
    data = await state.get_data()
    text = (message.text or "").strip()

    if text == ".":
        text = str(data.get("old_body", ""))
    elif text == "-":
        text = ""
    elif text == "":
        text = ""  # очистка разрешена

    await state.update_data(body=text)
    await state.set_state(EditItem.photo)
    await message.answer(
        "Отправьте новое фото.\n"
        "'.' — оставить текущее\n"
        "'-' — удалить фото",
        reply_markup=FSM_FORM_KB,
    )


@admin_cms_router.message(EditItem.photo, F.photo)
async def edit_item_photo_new(message: types.Message, state: FSMContext):
    photo = message.photo[-1].file_id if message.photo else None
    await state.update_data(
        photo=photo,
        clear_photo=False,
    )
    await state.set_state(EditItem.sort_order)
    await message.answer(
        "Введите порядок сортировки.\n"
        "'.' — оставить текущее значение",
        reply_markup=FSM_FORM_KB,
    )


@admin_cms_router.message(EditItem.photo, F.text)
async def edit_item_photo_text(message: types.Message, state: FSMContext):
    data = await state.get_data()
    text = (message.text or "").strip()

    if text == ".":
        await state.update_data(
            photo=str(data.get("old_photo", "")) or None,
            clear_photo=False,
        )
    elif text == "-":
        await state.update_data(
            photo=None,
            clear_photo=True,
        )
    else:
        await message.answer("Отправьте фото, '.' или '-'.", reply_markup=FSM_FORM_KB)
        return

    await state.set_state(EditItem.sort_order)
    await message.answer(
        "Введите порядок сортировки.\n"
        "'.' — оставить текущее значение",
        reply_markup=FSM_FORM_KB,
    )


@admin_cms_router.message(EditItem.sort_order, F.text)
async def edit_item_finish(
    message: types.Message,
    state: FSMContext,
    session: AsyncSession,
):
    data = await state.get_data()
    item_id = int(data["item_id"])
    section_id = int(data["section_id"])
    p = int(data.get("p", 1))
    mode = int(data.get("mode", 0))

    raw = (message.text or "").strip()
    if raw == ".":
        sort_order = int(data.get("old_sort_order", 0))
    else:
        try:
            sort_order = int(raw)
        except ValueError:
            await message.answer(
                "Введите число. Например: 0, 10, 20.\n"
                "'.' — оставить текущее значение",
                reply_markup=FSM_FORM_KB,
            )
            return

    title = str(data.get("title"))
    body = data.get("body")
    photo = data.get("photo")

    clear_photo = bool(data.get("clear_photo", False))

    await orm_update_item(
        session,
        item_id,
        title=title,
        body=body,
        photo=photo,
        clear_photo=clear_photo,
        sort_order=sort_order,
    )

    await state.clear()

    await _show_admin_item(
        message,
        session=session,
        section_id=section_id,
        item_id=item_id,
        p=p,
        mode=mode,
        notice="✅ Элемент обновлён.",
    )


# -----------------------------
# FSM: EDIT BANNER
# -----------------------------

@admin_cms_router.message(EditBanner.description, F.text)
async def edit_banner_description(
    message: types.Message,
    state: FSMContext,
    session: AsyncSession,
):
    data = await state.get_data()
    page = str(data["page"])
    text = (message.text or "").strip()

    if text == ".":
        await state.clear()
        await _show_admin_banner(
            message,
            page=page,
            session=session,
            notice="Ок, без изменений.",
        )
        return

    if text == "-":
        text = ""

    await orm_set_banner_description(session, page, text)
    await state.clear()

    await _show_admin_banner(
        message,
        page=page,
        session=session,
        notice="✅ Описание обновлено.",
    )

@admin_cms_router.message(EditBanner.photo, F.photo)
async def edit_banner_photo_new(
    message: types.Message,
    state: FSMContext,
    session: AsyncSession,
):
    data = await state.get_data()
    page = str(data["page"])
    photo = message.photo[-1].file_id if message.photo else None

    await orm_set_banner_photo(session, page, photo)
    await state.clear()

    await _show_admin_banner(
        message,
        page=page,
        session=session,
        notice="✅ Фото обновлено.",
    )

@admin_cms_router.message(EditBanner.photo, F.text)
async def edit_banner_photo_text(
    message: types.Message,
    state: FSMContext,
    session: AsyncSession,
):
    data = await state.get_data()
    page = str(data["page"])
    text = (message.text or "").strip()

    if text == ".":
        await state.clear()
        await _show_admin_banner(
            message,
            page=page,
            session=session,
            notice="Ок, без изменений.",
        )
        return

    if text == "-":
        await orm_set_banner_photo(session, page, None)
        await state.clear()
        await _show_admin_banner(
            message,
            page=page,
            session=session,
            notice="✅ Фото удалено.",
        )
        return

    await message.answer("Отправьте фото, '.' или '-'.", reply_markup=FSM_FORM_KB)


@admin_cms_router.message(EditSection.title, F.text)
async def edit_section_title(
    message: types.Message,
    state: FSMContext,
    session: AsyncSession,
):
    data = await state.get_data()
    section_id = int(data["section_id"])
    text = (message.text or "").strip()

    if text == ".":
        await state.clear()
        await _show_admin_section(
            message,
            session=session,
            section_id=section_id,
            notice="Ок, без изменений.",
        )
        return

    if not text:
        await message.answer(
            "Заголовок раздела не может быть пустым.\n"
            "Введите новый заголовок или нажмите '.'.",
            reply_markup=FSM_FORM_KB,
        )
        return

    ok = await orm_set_section_title(session, section_id, text)
    await state.clear()

    if not ok:
        await message.answer("Не удалось обновить заголовок раздела.", reply_markup=ADMIN_KB)
        return

    await _show_admin_section(
        message,
        session=session,
        section_id=section_id,
        notice="✅ Заголовок раздела обновлён.",
    )


@admin_cms_router.message(EditSection.description, F.text)
async def edit_section_description(
    message: types.Message,
    state: FSMContext,
    session: AsyncSession,
):
    data = await state.get_data()
    section_id = int(data["section_id"])
    text = (message.text or "").strip()

    if text == ".":
        await state.clear()
        await _show_admin_section(
            message,
            session=session,
            section_id=section_id,
            notice="Ок, без изменений.",
        )
        return

    if text == "-":
        text_value: str | None = None
    else:
        text_value = text

    ok = await orm_set_section_description(session, section_id, text_value)
    await state.clear()

    if not ok:
        await message.answer("Не удалось обновить описание раздела.", reply_markup=ADMIN_KB)
        return

    await _show_admin_section(
        message,
        session=session,
        section_id=section_id,
        notice="✅ Описание обновлено.",
    )


@admin_cms_router.message(EditSection.photo, F.photo)
async def edit_section_photo_new(
    message: types.Message,
    state: FSMContext,
    session: AsyncSession,
):
    data = await state.get_data()
    section_id = int(data["section_id"])
    photo = message.photo[-1].file_id if message.photo else None

    ok = await orm_set_section_photo(session, section_id, photo)
    await state.clear()

    if not ok:
        await message.answer("Не удалось обновить фото раздела.", reply_markup=ADMIN_KB)
        return

    await _show_admin_section(
        message,
        session=session,
        section_id=section_id,
        notice="✅ Фото раздела обновлено.",
    )


@admin_cms_router.message(EditSection.photo, F.text)
async def edit_section_photo_text(
    message: types.Message,
    state: FSMContext,
    session: AsyncSession,
):
    data = await state.get_data()
    section_id = int(data["section_id"])
    text = (message.text or "").strip()

    if text == ".":
        await state.clear()
        await _show_admin_section(
            message,
            session=session,
            section_id=section_id,
            notice="Ок, без изменений.",
        )
        return

    if text == "-":
        ok = await orm_set_section_photo(session, section_id, None)
        await state.clear()

        if not ok:
            await message.answer("Не удалось удалить фото раздела.", reply_markup=ADMIN_KB)
            return

        await _show_admin_section(
            message,
            session=session,
            section_id=section_id,
            notice="✅ Фото раздела удалено.",
        )
        return

    await message.answer("Отправьте фото, '.' или '-'.", reply_markup=FSM_FORM_KB)

# -----------------------------
# FSM: CANCEL
# -----------------------------



