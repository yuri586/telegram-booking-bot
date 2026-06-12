# common/debug_bot.py
from typing import Any

from aiogram import Bot
from aiogram.methods import TelegramMethod

from config import settings


class DebugBot(Bot):
    async def __call__(
        self,
        method: TelegramMethod[Any],
        request_timeout: int | None = None,
    ) -> Any:
        if settings.DEBUG and settings.DEBUG_OUTGOING:
            name = method.__class__.__name__

            if name == "GetUpdates":
                return await super().__call__(method, request_timeout=request_timeout)

            # 1) dump без json-режима (он и ломается на Default)
            payload = method.model_dump(exclude_none=True)

            # 2) выкидываем Default(...) и другие сложные объекты
            cleaned = {}
            for k, v in payload.items():
                # Default(...) внутри aiogram выглядит как объект, не сериализуемый
                if v.__class__.__name__ == "Default":
                    continue
                cleaned[k] = v

            payload = cleaned

            # 3) режем длинные поля
            for k in ("text", "caption"):
                if k in payload and isinstance(payload[k], str) and len(payload[k]) > 200:
                    payload[k] = payload[k][:200] + "...<cut>"

            print("\n" + "-" * 50)
            print(f"OUTGOING: {name}")
            print(f"PAYLOAD: {payload}")
            print("-" * 50)

        return await super().__call__(method, request_timeout=request_timeout)
