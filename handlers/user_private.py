# handlers/user_private.py
from __future__ import annotations

import logging

from aiogram import Router, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from sqlalchemy.ext.asyncio import AsyncSession

from database.orm_query import orm_get_or_create_user
from filters.chat_types import ChatTypeFilter
from handlers.menu_engine import dispatch_menu
from handlers.menu_routes import render_banner
from keyboards.callbacks import MenuCB

logger = logging.getLogger(__name__)

user_private_router = Router()
user_private_router.message.filter(ChatTypeFilter(chat_types=["private"]))


def _missing_page_hint(page: str) -> str:
    return (
        f"Нет страницы <b>{page}</b> в БД.\n\n"
        "Сделай так:\n"
        "1) <code>alembic upgrade head</code>\n"
        "2) Запусти с демо-контентом:\n"
        "   <code>SEED_DEMO=1 DEMO_PROFILE=&lt;profile&gt; python app.py</code>\n"
    )


@user_private_router.message(CommandStart())
async def start_cmd(message: types.Message, session: AsyncSession) -> None:
    from_user = message.from_user
    if not from_user:
        await message.answer("Не удалось определить пользователя.")
        return

    await orm_get_or_create_user(
        session,
        tg_id=from_user.id,
        first_name=from_user.first_name,
        last_name=from_user.last_name,
    )

    ok = await render_banner(message, session, page="main", edit=False)
    if not ok:
        await message.answer(_missing_page_hint("main"))


@user_private_router.message(Command("help"))
async def help_cmd(message: types.Message, session: AsyncSession) -> None:
    ok = await render_banner(message, session, page="help", edit=False)
    if not ok:
        await message.answer(_missing_page_hint("help"))


@user_private_router.callback_query(MenuCB.filter())
async def on_menu_cb(
    call: types.CallbackQuery,
    callback_data: MenuCB,
    session: AsyncSession,
) -> None:
    msg = call.message
    if not isinstance(msg, types.Message):
        await call.answer()
        return

    try:
        handled = await dispatch_menu(call, msg, callback_data, session)
        if not handled:
            await call.answer("Неизвестное действие", show_alert=False)
        # если handled=True — роут уже сам сделал edit + call.answer()
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            logger.warning("Menu edit failed: %s", e)
        await call.answer()