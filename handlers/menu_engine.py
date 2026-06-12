# handlers/menu_engine.py
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from keyboards.callbacks import MenuCB

if TYPE_CHECKING:
    from aiogram import types
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

Handler = Callable[["types.CallbackQuery", "types.Message", MenuCB, "AsyncSession"], Awaitable[None]]


class RouteConflictError(RuntimeError):
    pass


@dataclass(frozen=True)
class Key:
    level: int
    page: str
    action: str | None = None


ROUTES: dict[Key, Handler] = {}


def route(level: int, page: str, action: str | None = None):
    def deco(fn: Handler) -> Handler:
        key = Key(level, page, action)
        existing = ROUTES.get(key)
        if existing is not None and existing is not fn:
            raise RouteConflictError(f"Duplicate menu route {key}: {existing} vs {fn}")
        ROUTES[key] = fn
        logger.debug("Menu route registered: %s -> %s", key, getattr(fn, "__name__", fn))
        return fn

    return deco


async def dispatch_menu(call: types.CallbackQuery, msg: types.Message, data: MenuCB, session: AsyncSession) -> bool:
    key = Key(data.level, data.page, data.action)
    fn = ROUTES.get(key)
    if not fn:
        logger.debug("Menu route not found: %s. Known: %s", key, [(k.level, k.page, k.action) for k in ROUTES.keys()])
        return False
    await fn(call, msg, data, session)
    return True