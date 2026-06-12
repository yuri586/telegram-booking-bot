from __future__ import annotations

import argparse
import asyncio

from aiogram import Dispatcher, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from common.bot_cmds_list import admin_private_commands, user_private_commands
from common.capabilities import caps
from common.debug_bot import DebugBot
from common.logging import setup_logging
from config import settings, validate_startup_preflight
from database.engine import close_engine, session_maker
from database.orm_query import orm_get_banner, orm_has_seeded_profile_data
from handlers.admin_cms import admin_cms_router
from handlers.errors import router as errors_router
from handlers.menu_routes import register_menu_routes
from handlers.user_private import user_private_router
from middlewares.db import DataBaseSession
from middlewares.debug import DebugUpdateMiddleware
from plugins.booking.reminders import run_booking_reminder_loop
from plugins.registry import load_enabled_plugin_routers
from profiles.registry import get_profile


def create_bot() -> DebugBot:
    return DebugBot(
        token=settings.TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def create_dispatcher(c) -> Dispatcher:
    dp = Dispatcher()

    register_menu_routes()
    dp.include_router(errors_router)

    if c.debug_mw:
        dp.update.middleware(DebugUpdateMiddleware())

    dp.update.middleware(DataBaseSession(session_pool=session_maker))

    dp.include_router(user_private_router)
    dp.include_router(admin_cms_router)

    for router in load_enabled_plugin_routers(c):
        dp.include_router(router)

    return dp


async def run_startup() -> None:
    if settings.ENV == "prod" and settings.RESET_DB:
        raise RuntimeError("RESET_DB disabled in prod. Use manual ops + backup/restore.")

    profile = get_profile(settings.DEMO_PROFILE)

    if settings.SEED_DEMO:
        async with session_maker() as session:
            has_existing_data = await orm_has_seeded_profile_data(session)
            if has_existing_data:
                raise RuntimeError(
                    "SEED_DEMO=1 requires an empty DB. "
                    "One profile = one DB. "
                    "Use a fresh DB_URL for another profile."
                )

            await profile.seed(session)


async def run_shutdown(bot: DebugBot) -> None:
    await bot.session.close()
    await close_engine()


async def run_smoke() -> None:
    c = caps()

    # проверка профиля
    get_profile(settings.DEMO_PROFILE)

    # проверка сборки диспетчера и плагинов
    create_dispatcher(c)

    # быстрая проверка БД и схемы:
    # открываем session и делаем реальный ORM-запрос к banners
    async with session_maker() as session:
        await orm_get_banner(session, "main")

    print("SMOKE OK")


async def main(smoke: bool = False) -> None:
    setup_logging(settings.LOG_LEVEL)
    validate_startup_preflight()

    if smoke:
        await run_smoke()
        return

    c = caps()
    bot = create_bot()
    dp = create_dispatcher(c)
    reminder_task: asyncio.Task[None] | None = None

    async def _startup() -> None:
        nonlocal reminder_task

        await run_startup()

        if c.booking:
            reminder_task = asyncio.create_task(run_booking_reminder_loop(bot))

    async def _shutdown() -> None:
        nonlocal reminder_task

        if reminder_task is not None:
            reminder_task.cancel()
            try:
                await reminder_task
            except asyncio.CancelledError:
                pass

        await run_shutdown(bot)

    dp.startup.register(_startup)
    dp.shutdown.register(_shutdown)

    await bot.delete_webhook(drop_pending_updates=True)

    await bot.set_my_commands(
        commands=user_private_commands(c),
        scope=types.BotCommandScopeAllPrivateChats(),
    )

    if settings.ADMIN_IDS:
        admin_commands = admin_private_commands(c)
        for admin_id in settings.ADMIN_IDS:
            await bot.set_my_commands(
                commands=admin_commands,
                scope=types.BotCommandScopeChat(chat_id=admin_id),
            )

    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()

    asyncio.run(main(smoke=args.smoke))