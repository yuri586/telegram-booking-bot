"""
keyboards/reply.py

Утилиты для Reply-клавиатур в aiogram 3.
Основной рабочий путь — функция get_keyboard().
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import cast

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import ReplyKeyboardBuilder


def get_keyboard(
    *btns: str,
    placeholder: str | None = None,
    request_contact: int | None = None,
    request_location: int | None = None,
    sizes: Sequence[int] = (2,),
) -> ReplyKeyboardMarkup:
    """
    Универсальная сборка Reply-клавиатуры.

    request_contact / request_location — индекс кнопки в btns,
    для которой нужно включить request_contact=True
    или request_location=True.
    """
    keyboard = ReplyKeyboardBuilder()

    for index, text in enumerate(btns):
        if request_contact is not None and request_contact == index:
            keyboard.add(KeyboardButton(text=text, request_contact=True))
            continue

        if request_location is not None and request_location == index:
            keyboard.add(KeyboardButton(text=text, request_location=True))
            continue

        keyboard.add(KeyboardButton(text=text))

    return cast(
        ReplyKeyboardMarkup,
        keyboard.adjust(*sizes).as_markup(
            resize_keyboard=True,
            input_field_placeholder=placeholder,
        ),
    )