from __future__ import annotations

from aiogram import types

CAPTION_LIMIT = 1024

def cap(text: str, limit: int = CAPTION_LIMIT) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"

def safe_text(text: str) -> str:
    # Telegram не любит совсем пустые caption/text
    text = (text or "").strip()
    return text if text else " "

async def replace_with_photo(
    msg: types.Message,
    *,
    photo: str,
    caption: str,
    reply_markup,
) -> None:
    # удаляем старый “экран”
    try:
        await msg.delete()
    except Exception:
        pass

    # создаём новый “экран”
    await msg.answer_photo(photo=photo, caption=caption, reply_markup=reply_markup)