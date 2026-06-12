# common/logging.py
from __future__ import annotations

import logging


def setup_logging(level: str = "INFO") -> None:
    root = logging.getLogger()

    # если уже настроено (например, тестами) — не ломаем
    if root.handlers:
        root.setLevel(getattr(logging, level.upper(), logging.INFO))
        return

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # меньше шума
    logging.getLogger("aiohttp.access").setLevel(logging.WARNING)
    logging.getLogger("aiogram.event").setLevel(logging.INFO)