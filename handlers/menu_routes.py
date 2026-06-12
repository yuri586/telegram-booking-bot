from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aiogram import types

from sqlalchemy.ext.asyncio import AsyncSession

from common.tg_msg import cap, replace_with_photo, safe_text
from common.ui import ui_labels, ui_msg
from database.orm_query import orm_get_banner, orm_get_item, orm_get_items_page, orm_get_section, orm_get_sections
from handlers.menu_engine import route
from keyboards.callbacks import MenuCB
from keyboards.inline import get_inline_buttons, kb_items_list, kb_level0, kb_sections

_REGISTERED = False

def _menu_msg(key: str, default: str) -> str:
    return ui_msg(key, default)

async def render_banner(
    msg: types.Message,
    session: AsyncSession,
    *,
    page: str,
    edit: bool,
) -> bool:
    """
    Универсальный рендер баннера.
    edit=False -> отправляет новое сообщение (для /start, /help)
    edit=True  -> редактирует текущий экран (для inline меню)
    Возвращает False если баннера нет в БД.
    """
    labels = ui_labels()
    banner = await orm_get_banner(session, page)
    if not banner:
        return False

    kb = kb_level0(labels)

    if banner.photo:
        caption = cap(safe_text(banner.description or ""))
        if edit:
            if msg.photo:
                from aiogram.types import InputMediaPhoto
                media = InputMediaPhoto(media=banner.photo, caption=caption)
                await msg.edit_media(media=media, reply_markup=kb)
            else:
                await replace_with_photo(
                    msg,
                    photo=banner.photo,
                    caption=caption,
                    reply_markup=kb,
                )
        else:
            await msg.answer_photo(
                photo=banner.photo,
                caption=caption,
                reply_markup=kb,
            )
        return True

    # no photo
    text = safe_text(banner.description or "")

    if edit:
        if msg.photo:
            await msg.edit_caption(caption=cap(text), reply_markup=kb)
        else:
            await msg.edit_text(text=text, reply_markup=kb)
    else:
        await msg.answer(text=text or "…", reply_markup=kb)

    return True


def register_menu_routes() -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    _REGISTERED = True


    route(level=0, page="main")(_menu_banner)
    route(level=0, page="about")(_menu_banner)
    route(level=0, page="help")(_menu_banner)
    route(level=0, page="contacts")(_menu_banner)
    route(level=1, page="sections")(_menu_sections)
    route(level=2, page="section")(menu_section_items)
    route(level=3, page="item")(menu_item_card)

async def _render_menu_screen(
    msg: types.Message,
    *,
    text: str,
    kb,
    photo: str | None = None,
) -> None:
    if photo:
        caption = cap(safe_text(text))
        if msg.photo:
            from aiogram.types import InputMediaPhoto
            media = InputMediaPhoto(media=photo, caption=caption)
            await msg.edit_media(media=media, reply_markup=kb)
        else:
            await replace_with_photo(
                msg,
                photo=photo,
                caption=caption,
                reply_markup=kb,
            )
        return

    text = safe_text(text)

    if msg.photo:
        await msg.edit_caption(caption=cap(text), reply_markup=kb)
    else:
        await msg.edit_text(text=text or "…", reply_markup=kb)

async def _menu_banner(call: types.CallbackQuery, msg: types.Message, data: MenuCB, session: AsyncSession) -> None:
    ok = await render_banner(msg, session, page=data.page, edit=True)
    if not ok:
        await call.answer(_menu_msg("page_not_found", "Страница не найдена"), show_alert=True)
        return
    await call.answer()


async def _menu_sections(
    call: types.CallbackQuery,
    msg: types.Message,
    data: MenuCB,
    session: AsyncSession,
) -> None:
    labels = ui_labels()
    sections = await orm_get_sections(session)
    text = ui_msg("sections_title", "📚 Разделы:")

    await _render_menu_screen(
        msg,
        text=text,
        kb=kb_sections(sections, labels),
        photo=None,
    )

    await call.answer()


async def menu_section_items(
    call: types.CallbackQuery,
    msg: types.Message,
    data: MenuCB,
    session: AsyncSession,
) -> None:
    labels = ui_labels()

    section_id = data.section
    if not section_id:
        await call.answer(_menu_msg("section_missing", "Не выбран раздел."), show_alert=True)
        return

    page_num = data.p or 1

    section = await orm_get_section(session, section_id)
    section_title = section.title if section else f"Раздел #{section_id}"
    section_photo = section.photo if section else None

    page = await orm_get_items_page(session, section_id=section_id, page=page_num, per_page=6)

    # 1) пусто
    if not page.items:
        text = _menu_msg(
            "section_empty",
            "В разделе «{section_title}» пока нет материалов.",
        ).format(section_title=section_title)
        kb = get_inline_buttons(
            btns={
                labels["to_sections"]: MenuCB(level=1, page="sections").pack(),
                labels["home_main"]: MenuCB(level=0, page="main").pack(),
            },
            sizes=(2,),
        )

        await _render_menu_screen(
            msg,
            text=text,
            kb=kb,
            photo=section_photo,
        )

        await call.answer()
        return

    # 2) список + пагинация
    text = f"🧩 {section_title}\nСтраница {page.page}/{page.pages}"
    kb = kb_items_list(section_id, page, labels)

    await _render_menu_screen(
        msg,
        text=text,
        kb=kb,
        photo=section_photo,
    )

    await call.answer()



async def menu_item_card(
    call: types.CallbackQuery,
    msg: types.Message,
    data: MenuCB,
    session: AsyncSession,
) -> None:
    
    labels = ui_labels()

    section_id = data.section
    item_id = data.item
    page_num = data.p or 1

    if not section_id or not item_id:
        await call.answer(
            _menu_msg("item_or_section_missing", "Нет данных item/section"),
            show_alert=True,
        )
        return

    item = await orm_get_item(session, item_id)
    if not item:
        await call.answer(_menu_msg("item_not_found", "Элемент не найден"), show_alert=True)
        return

    # клавиатура карточки
    kb = get_inline_buttons(
        btns={
            labels["back_to_list"]: MenuCB(level=2, page="section", section=section_id, p=page_num).pack(),
            labels["to_sections"]: MenuCB(level=1, page="sections").pack(),
            labels["home_main"]: MenuCB(level=0, page="main").pack(),
        },
        sizes=(1, 2),
    )

    title = item.title or "Без названия"
    body = item.body or ""
    text = safe_text(f"<b>{title}</b>\n\n{body}".strip())

    # если у элемента есть фото — показываем фото, иначе просто текст/подпись
    if item.photo:
        caption = cap(text)

        if msg.photo:
            from aiogram.types import InputMediaPhoto
            media = InputMediaPhoto(media=item.photo, caption=caption)
            await msg.edit_media(media=media, reply_markup=kb)
        else:
            await replace_with_photo(
                msg,
                photo=item.photo,
                caption=caption,
                reply_markup=kb,
            )
    else:
        if msg.photo:
            await msg.edit_caption(caption=cap(text), reply_markup=kb)
        else:
            await msg.edit_text(text=text, reply_markup=kb)

    await call.answer()