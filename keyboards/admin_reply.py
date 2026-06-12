from __future__ import annotations

from aiogram.types import ReplyKeyboardMarkup

from common.capabilities import Caps
from common.capabilities import caps as get_caps
from keyboards.reply import get_keyboard
from plugins.registry import load_enabled_plugin_admin_buttons

CORE_ADMIN_BUTTONS: list[str] = ["Разделы", "Страницы"]


def _sizes_for(n: int) -> tuple[int, ...]:
    """
    Раскладка по 2 кнопки в ряд, последний ряд 1 (если нечетное).
    5 -> (2,2,1), 4 -> (2,2), 2 -> (2,), 1 -> (1,)
    """
    if n <= 0:
        return (1,)
    sizes: list[int] = []
    while n > 2:
        sizes.append(2)
        n -= 2
    sizes.append(n)
    return tuple(sizes)


def _dedupe_buttons(buttons: list[str]) -> list[str]:
    return list(dict.fromkeys(buttons))


def admin_kb(c: Caps | None = None) -> ReplyKeyboardMarkup:
    c = c or get_caps()

    btns = list(CORE_ADMIN_BUTTONS)
    btns.extend(load_enabled_plugin_admin_buttons(c))
    btns = _dedupe_buttons(btns)

    return get_keyboard(
        *btns,
        placeholder="Админ: выбери действие",
        sizes=_sizes_for(len(btns)),
    )


ADMIN_KB = admin_kb()