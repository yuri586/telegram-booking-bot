# database/seed_core.py
from __future__ import annotations

from datetime import date, time, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.booking_time import booking_today
from database.models import Banner, ContentItem, Section, Service, TimeSlot


async def _upsert_banner(
    session: AsyncSession,
    *,
    name: str,
    description: str,
    photo: str | None,
) -> Banner:
    res = await session.execute(select(Banner).where(Banner.name == name))
    obj = res.scalar_one_or_none()
    if obj is None:
        obj = Banner(name=name, description=description, photo=photo)
        session.add(obj)
        await session.flush()
        return obj

    obj.description = description
    obj.photo = photo
    return obj


async def _upsert_section(
    session: AsyncSession,
    *,
    title: str,
    description: str | None,
    photo: str | None,
) -> Section:
    res = await session.execute(select(Section).where(Section.title == title))
    obj = res.scalars().first()
    if obj is None:
        obj = Section(title=title, description=description, photo=photo)
        session.add(obj)
        await session.flush()
        return obj

    obj.description = description
    obj.photo = photo
    return obj


async def _upsert_item(
    session: AsyncSession,
    *,
    section_id: int,
    title: str,
    body: str | None,
    photo: str | None,
    sort_order: int,
) -> ContentItem:
    res = await session.execute(
        select(ContentItem).where(
            ContentItem.section_id == section_id,
            ContentItem.title == title,
        )
    )
    obj = res.scalars().first()
    if obj is None:
        obj = ContentItem(
            section_id=section_id,
            title=title,
            body=body,
            photo=photo,
            sort_order=sort_order,
            is_active=True,
        )
        session.add(obj)
        await session.flush()
        return obj

    obj.body = body
    obj.photo = photo
    obj.sort_order = sort_order
    obj.is_active = True
    return obj


async def _upsert_service(
    session: AsyncSession,
    *,
    title: str,
    description: str | None,
    price: Decimal | None,
) -> Service:
    res = await session.execute(select(Service).where(Service.title == title))
    obj = res.scalars().first()
    if obj is None:
        obj = Service(title=title, description=description, price=price, is_active=True)
        session.add(obj)
        await session.flush()
        return obj

    obj.description = description
    obj.price = price
    obj.is_active = True
    return obj


async def _upsert_timeslot(
    session: AsyncSession,
    *,
    service_id: int,
    day: date,
    start_time: time,
) -> TimeSlot:
    res = await session.execute(
        select(TimeSlot).where(
            TimeSlot.service_id == service_id,
            TimeSlot.day == day,
            TimeSlot.start_time == start_time,
        )
    )
    obj = res.scalars().first()
    if obj is None:
        obj = TimeSlot(
            service_id=service_id,
            day=day,
            start_time=start_time,
            is_active=True,
            is_booked=False,
        )
        session.add(obj)
        await session.flush()
        return obj

    obj.is_active = True
    return obj


def _parse_hhmm(value: str) -> time:
    hour_s, minute_s = value.split(":")
    return time(hour=int(hour_s), minute=int(minute_s))


async def seed_from_content(
    session: AsyncSession,
    *,
    banners: dict[str, dict[str, str | None]],
    sections: list[dict[str, str | None]],
    items: dict[str, list[dict[str, str | int | None]]],
    services: list[dict[str, str | None]] | None = None,
    slot_times: tuple[str, ...] = (),
    slot_days_ahead: int = 0,
) -> None:
    # 1) banners
    for name, payload in banners.items():
        await _upsert_banner(
            session,
            name=name,
            description=str(payload.get("description") or ""),
            photo=(str(payload["photo"]) if payload.get("photo") else None),
        )

    # 2) sections
    sections_by_title: dict[str, Section] = {}
    for raw_section in sections:
        title = str(raw_section["title"])
        section = await _upsert_section(
            session,
            title=title,
            description=(str(raw_section["description"]) if raw_section.get("description") else None),
            photo=(str(raw_section["photo"]) if raw_section.get("photo") else None),
        )
        sections_by_title[title] = section

    # 3) items (section -> list[items])
    for section_title, raw_items in items.items():
        section_obj = sections_by_title.get(section_title)
        if section_obj is None:
            continue

        section = section_obj

        for raw_item in raw_items:
            await _upsert_item(
                session,
                section_id=section.id,
                title=str(raw_item["title"]),
                body=(str(raw_item["body"]) if raw_item.get("body") else None),
                photo=(str(raw_item["photo"]) if raw_item.get("photo") else None),
                sort_order=int(raw_item.get("sort_order", 0) or 0),
            )

    # 4) optional services
    seeded_services: list[Service] = []
    for raw_service in services or []:
        price_raw = raw_service.get("price")
        price = Decimal(str(price_raw)) if price_raw else None
        service = await _upsert_service(
            session,
            title=str(raw_service["title"]),
            description=(str(raw_service["description"]) if raw_service.get("description") else None),
            price=price,
        )
        seeded_services.append(service)

    # 5) optional timeslots (booking-only profiles)
    if seeded_services and slot_times and slot_days_ahead > 0:
        slot_time_values = [_parse_hhmm(value) for value in slot_times]
        today = booking_today()

        for service in seeded_services:
            for offset in range(int(slot_days_ahead)):
                day = today + timedelta(days=offset)

                for start_time in slot_time_values:
                    await _upsert_timeslot(
                        session,
                        service_id=service.id,
                        day=day,
                        start_time=start_time,
                    )

    await session.commit()