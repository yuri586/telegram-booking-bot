# handlers/errors.py
from __future__ import annotations

import logging

from aiogram import Router
from aiogram.types import ErrorEvent

router = Router()
log = logging.getLogger(__name__)


@router.errors()
async def global_error_handler(event: ErrorEvent):
    log.exception("Unhandled error while handling update", exc_info=event.exception)

    try:
        if event.update and event.update.message:
            await event.update.message.answer("⚠️ Ошибка. Попробуйте ещё раз чуть позже.")
    except Exception:
        pass

    return True