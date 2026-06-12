from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Generic, TypeVar

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar("T")


@dataclass(frozen=True)
class Page(Generic[T]):
    items: list[T]
    page: int
    per_page: int
    total: int
    pages: int

    @property
    def has_next(self) -> bool:
        return self.page < self.pages

    @property
    def has_prev(self) -> bool:
        return self.page > 1

    @property
    def next_page(self) -> int | None:
        return self.page + 1 if self.has_next else None

    @property
    def prev_page(self) -> int | None:
        return self.page - 1 if self.has_prev else None


async def paginate(
    session: AsyncSession,
    stmt: Select,
    *,
    page: int = 1,
    per_page: int = 6,
) -> Page:
    page = max(1, int(page))
    per_page = max(1, int(per_page))

    # считаем total через подзапрос
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = int((await session.execute(count_stmt)).scalar_one())

    pages = max(1, math.ceil(total / per_page)) if total else 1
    if page > pages:
        page = pages

    offset = (page - 1) * per_page

    result = await session.execute(stmt.limit(per_page).offset(offset))
    items = list(result.scalars().all())

    return Page(items=items, page=page, per_page=per_page, total=total, pages=pages)