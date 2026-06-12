# database/orm_query.py
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, cast

from sqlalchemy import and_, delete, exists, func, or_, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, selectinload

from common.booking_time import booking_now, booking_slot_dt
from database.models import (
    AppSetting,
    Banner,
    Booking,
    ContentItem,
    LeadRequest,
    Product,
    Section,
    Service,
    TimeSlot,
    User,
)
from utils.paginator import Page, paginate

# ----------------------------
# PRODUCTS (plugin / demo)
# ----------------------------
BOOKING_REMINDER_LEAD_MINUTES_KEY = "booking_reminder_lead_minutes"
BOOKING_REMINDER_ALLOWED_MINUTES: tuple[int, ...] = (60, 180, 1440, 2880)
BOOKING_REMINDER_DEFAULT_MINUTES = 60


async def orm_add_product(
    session: AsyncSession,
    title: str,
    description: str | None,
    price: str | int | float | Decimal,
    photo: str | None,
) -> Product:
    price_dec = Decimal(str(price)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    obj = Product(
        title=title.strip(),
        description=description,
        price=price_dec,
        photo=photo,
    )
    session.add(obj)

    try:
        await session.commit()
    except Exception:
        await session.rollback()
        raise

    await session.refresh(obj)
    return obj


async def orm_get_products(session: AsyncSession) -> list[Product]:
    result = await session.execute(select(Product).order_by(Product.id.desc()))
    return cast(list[Product], result.scalars().all())


async def orm_get_product(session: AsyncSession, product_id: int) -> Product | None:
    result = await session.execute(select(Product).where(Product.id == product_id))
    return result.scalar_one_or_none()


async def orm_update_product(session: AsyncSession, product_id: int, data: dict) -> None:
    title = data.get("title")
    description = data.get("description")
    photo = data.get("photo")

    price = data.get("price")
    if price is None:
        raise ValueError("price is required")

    price_dec = Decimal(str(price)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    await session.execute(
        update(Product)
        .where(Product.id == product_id)
        .values(
            title=title.strip() if isinstance(title, str) else title,
            description=description,
            price=price_dec,
            photo=photo,
        )
    )
    await session.commit()


async def orm_delete_product(session: AsyncSession, product_id: int) -> None:
    await session.execute(delete(Product).where(Product.id == product_id))
    await session.commit()





# ----------------------------
# BANNERS (L0 info pages)
# ----------------------------




async def orm_get_banner(session: AsyncSession, name: str) -> Banner | None:
    result = await session.execute(select(Banner).where(Banner.name == name))
    return result.scalar_one_or_none()


async def orm_set_banner_photo(session: AsyncSession, name: str, photo: str | None) -> None:
    await session.execute(update(Banner).where(Banner.name == name).values(photo=photo))
    await session.commit()


async def orm_set_banner_description(session: AsyncSession, name: str, description: str) -> None:
    await session.execute(
        update(Banner).where(Banner.name == name).values(description=description)
    )
    await session.commit()




# ----------------------------
# USERS (core)
# ----------------------------

async def orm_get_or_create_user(
    session: AsyncSession,
    *,
    tg_id: int,
    first_name: str | None = None,
    last_name: str | None = None,
) -> User:
    result = await session.execute(select(User).where(User.tg_id == tg_id))
    user = result.scalar_one_or_none()

    if user:
        changed = False
        if first_name is not None and user.first_name != first_name:
            user.first_name = first_name
            changed = True
        if last_name is not None and user.last_name != last_name:
            user.last_name = last_name
            changed = True

        if changed:
            await session.commit()
            await session.refresh(user)

        return user

    user = User(tg_id=tg_id, first_name=first_name, last_name=last_name)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def orm_set_user_phone(session: AsyncSession, *, tg_id: int, phone: str) -> None:
    phone = phone.strip()
    if not phone:
        return
    await session.execute(update(User).where(User.tg_id == tg_id).values(phone=phone))
    await session.commit()


# ----------------------------
# LEADS (core)
# ----------------------------

async def orm_add_lead_request(
    session: AsyncSession,
    *,
    profile_slug: str,
    tg_id: int,
    name: str | None = None,
    contact: str | None = None,
    message: str | None = None,
) -> LeadRequest:
    obj = LeadRequest(
        profile_slug=profile_slug.strip().lower(),
        tg_id=tg_id,
        name=(name.strip() if isinstance(name, str) and name.strip() else None),
        contact=(contact.strip() if isinstance(contact, str) and contact.strip() else None),
        message=(message.strip() if isinstance(message, str) and message.strip() else None),
        status="new",
    )
    session.add(obj)

    try:
        await session.commit()
    except Exception:
        await session.rollback()
        raise

    await session.refresh(obj)
    return obj


async def orm_get_lead_request(session: AsyncSession, lead_id: int) -> LeadRequest | None:
    res = await session.execute(select(LeadRequest).where(LeadRequest.id == lead_id))
    return res.scalar_one_or_none()


async def orm_get_leads_page(
    session: AsyncSession,
    *,
    page: int = 1,
    per_page: int = 10,
    profile_slug: str | None = None,
    mode: int = 0,  # 0=new, 1=processed, 2=all
) -> Page[LeadRequest]:
    stmt = select(LeadRequest)

    if profile_slug:
        stmt = stmt.where(LeadRequest.profile_slug == profile_slug.strip().lower())

    if mode == 0:
        stmt = stmt.where(LeadRequest.status == "new")
    elif mode == 1:
        stmt = stmt.where(LeadRequest.status != "new")
    else:
        pass  # all

    stmt = stmt.order_by(LeadRequest.created.desc(), LeadRequest.id.desc())
    return await paginate(session, stmt, page=page, per_page=per_page)


async def orm_set_lead_status(
    session: AsyncSession,
    *,
    lead_id: int,
    status: str,
) -> bool:
    status = (status or "").strip()
    if not status:
        return False

    try:
        result = cast(
            CursorResult[Any],
            await session.execute(
                update(LeadRequest)
                .where(LeadRequest.id == lead_id)
                .values(status=status),
            ),
        )
        if (result.rowcount or 0) != 1:
            await session.rollback()
            return False

        await session.commit()
        return True
    except Exception:
        await session.rollback()
        raise

# ----------------------------
# SECTIONS (L1)
# ----------------------------

async def orm_get_sections(session: AsyncSession) -> list[Section]:
    result = await session.execute(select(Section).order_by(Section.id.asc()))
    return list(result.scalars().all())


async def orm_get_section(session: AsyncSession, section_id: int) -> Section | None:
    result = await session.execute(select(Section).where(Section.id == section_id))
    return result.scalar_one_or_none()

async def orm_set_section_title(
    session: AsyncSession,
    section_id: int,
    title: str,
) -> bool:
    title = title.strip()
    if not title:
        return False

    result = cast(
        CursorResult[Any],
        await session.execute(
            update(Section)
            .where(Section.id == section_id)
            .values(title=title),
        ),
    )
    if (result.rowcount or 0) != 1:
        await session.rollback()
        return False

    await session.commit()
    return True


async def orm_set_section_description(
    session: AsyncSession,
    section_id: int,
    description: str | None,
) -> bool:
    result = cast(
        CursorResult[Any],
        await session.execute(
            update(Section)
            .where(Section.id == section_id)
            .values(description=description),
        ),
    )
    if (result.rowcount or 0) != 1:
        await session.rollback()
        return False

    await session.commit()
    return True


async def orm_set_section_photo(
    session: AsyncSession,
    section_id: int,
    photo: str | None,
) -> bool:
    result = cast(
        CursorResult[Any],
        await session.execute(
            update(Section)
            .where(Section.id == section_id)
            .values(photo=photo),
        ),
    )
    if (result.rowcount or 0) != 1:
        await session.rollback()
        return False

    await session.commit()
    return True



# ----------------------------
# CONTENT ITEMS (L2/L3)
# ----------------------------

async def orm_get_items_page(
    session: AsyncSession,
    *,
    section_id: int,
    page: int = 1,
    per_page: int = 6,
    mode: int = 0,  # 0=active, 1=hidden, 2=all
) -> Page[ContentItem]:
    stmt = select(ContentItem).where(ContentItem.section_id == section_id)

    if mode == 0:
        stmt = stmt.where(ContentItem.is_active == True)   # noqa: E712
    elif mode == 1:
        stmt = stmt.where(ContentItem.is_active == False)  # noqa: E712
    else:
        # mode == 2 -> all, без фильтра
        pass

    stmt = stmt.order_by(ContentItem.sort_order.asc(), ContentItem.id.asc())
    return await paginate(session, stmt, page=page, per_page=per_page)


async def orm_get_item(session: AsyncSession, item_id: int) -> ContentItem | None:
    result = await session.execute(select(ContentItem).where(ContentItem.id == item_id))
    return result.scalar_one_or_none()


async def orm_add_item(
    session: AsyncSession,
    *,
    section_id: int,
    title: str,
    body: str | None = None,
    photo: str | None = None,
    sort_order: int = 0,
) -> ContentItem:
    obj = ContentItem(
        section_id=section_id,
        title=title.strip(),
        body=body,
        photo=photo,
        sort_order=sort_order,
        is_active=True,
    )
    session.add(obj)
    await session.commit()
    await session.refresh(obj)
    return obj


async def orm_update_item(
    session: AsyncSession,
    item_id: int,
    *,
    title: str | None = None,
    body: str | None = None,
    photo: str | None = None,
    clear_photo: bool = False,
    sort_order: int | None = None,
    is_active: bool | None = None,
) -> None:
    values: dict = {}
    if title is not None:
        values["title"] = title.strip()
    if body is not None:
        values["body"] = body
    if clear_photo:
        values["photo"] = None
    elif photo is not None:
        values["photo"] = photo
    if sort_order is not None:
        values["sort_order"] = sort_order
    if is_active is not None:
        values["is_active"] = is_active

    if not values:
        return

    await session.execute(update(ContentItem).where(ContentItem.id == item_id).values(**values))
    await session.commit()


async def orm_delete_item(session: AsyncSession, item_id: int) -> None:
    await session.execute(delete(ContentItem).where(ContentItem.id == item_id))
    await session.commit()



async def orm_toggle_item_active(session: AsyncSession, item_id: int) -> None:
    item = await orm_get_item(session, item_id)
    if not item:
        return
    item.is_active = not item.is_active
    await session.commit()

async def orm_has_seeded_profile_data(session: AsyncSession) -> bool:
    checks = (
        exists(select(Banner.id)),
        exists(select(Section.id)),
        exists(select(ContentItem.id)),
        exists(select(Service.id)),
        exists(select(TimeSlot.id)),
        exists(select(Booking.id)),
        exists(select(LeadRequest.id)),
    )

    for stmt in checks:
        found = await session.scalar(select(stmt))
        if found:
            return True

    return False
# -----------------------------
# BOOKING
# -----------------------------

ACTIVE_BOOKING_STATUSES: tuple[str, ...] = ("new", "confirmed")
BOOKING_STATUS_FILTERS: dict[int, tuple[str, ...] | None] = {
    0: ("new",),
    1: ("confirmed",),
    2: ("done",),
    3: ("cancelled_by_admin", "cancelled_by_user"),
    4: None,  # all
}

def booking_has_started(booking: Booking, *, now: datetime | None = None) -> bool:
    if not booking.slot:
        return False

    current = now or booking_now()
    slot_dt = booking_slot_dt(booking.slot.day, booking.slot.start_time)
    return slot_dt <= current

async def orm_get_user_bookings(
    session: AsyncSession,
    *,
    tg_id: int,
    active_only: bool = True,
) -> list[Booking]:
    stmt = (
        select(Booking)
        .options(selectinload(Booking.service), selectinload(Booking.slot))
        .where(Booking.tg_id == tg_id)
        .order_by(Booking.created.desc(), Booking.id.desc())
    )
    if active_only:
        stmt = stmt.where(Booking.status.in_(ACTIVE_BOOKING_STATUSES))

    res = await session.execute(stmt)
    return cast(list[Booking], res.scalars().all())


async def orm_get_user_booking(
    session: AsyncSession,
    *,
    booking_id: int,
    tg_id: int,
) -> Booking | None:
    stmt = (
        select(Booking)
        .options(selectinload(Booking.service), selectinload(Booking.slot))
        .where(Booking.id == booking_id, Booking.tg_id == tg_id)
    )
    res = await session.execute(stmt)
    return res.scalar_one_or_none()

async def orm_get_active_booking_broadcast_tg_ids(
    session: AsyncSession,
) -> list[int]:
    stmt = (
        select(Booking.tg_id)
        .where(Booking.status.in_(ACTIVE_BOOKING_STATUSES))
        .distinct()
        .order_by(Booking.tg_id.asc())
    )
    res = await session.execute(stmt)
    return [int(x) for x in res.scalars().all()]

async def orm_cancel_user_booking(
    session: AsyncSession,
    *,
    booking_id: int,
    tg_id: int,
) -> tuple[bool, str]:
    booking = await orm_get_user_booking(session, booking_id=booking_id, tg_id=tg_id)
    if not booking:
        return False, "not_found"

    if booking.status not in ACTIVE_BOOKING_STATUSES:
        return False, "inactive"

    if booking_has_started(booking):
        return False, "too_late"

    try:
        status_update = cast(
            CursorResult[Any],
            await session.execute(
                update(Booking)
                .where(
                    Booking.id == booking_id,
                    Booking.tg_id == tg_id,
                    Booking.status.in_(ACTIVE_BOOKING_STATUSES),
                )
                .values(status="cancelled_by_user")
            ),
        )
        if (status_update.rowcount or 0) != 1:
            await session.rollback()
            return False, "conflict"

        if booking.slot_id is not None:
            await _release_slot_if_no_active_bookings(session, booking.slot_id)

        await session.commit()
        return True, "cancelled"
    except Exception:
        await session.rollback()
        raise


async def _release_slot_if_no_active_bookings(session: AsyncSession, slot_id: int) -> None:
    active_exists = (
        select(1)
        .where(
            Booking.slot_id == slot_id,
            Booking.status.in_(ACTIVE_BOOKING_STATUSES),
        )
        .exists()
    )

    await session.execute(
        update(TimeSlot)
        .where(
            TimeSlot.id == slot_id,
            TimeSlot.is_booked == True,  # noqa: E712
            ~active_exists,
        )
        .values(is_booked=False)
    )
    # commit НЕ ДЕЛАЕМ

def _bookings_stmt(*, mode: int, day_mode: int):
    statuses = BOOKING_STATUS_FILTERS.get(mode, ("new",))

    stmt = (
        select(Booking)
        .options(selectinload(Booking.service), selectinload(Booking.slot))
        .outerjoin(TimeSlot, Booking.slot_id == TimeSlot.id)
        .order_by(
            Booking.slot_id.is_(None).asc(),
            TimeSlot.day.asc(),
            TimeSlot.start_time.asc(),
            Booking.id.asc(),
        )
    )
    if statuses is not None:
        stmt = stmt.where(Booking.status.in_(statuses))

    current = booking_now()
    today = current.date()
    now_time = current.time()

    if day_mode == 0:
        stmt = stmt.where(
            or_(
                TimeSlot.day > today,
                and_(
                    TimeSlot.day == today,
                    TimeSlot.start_time > now_time,
                ),
            )
        )
    elif day_mode == 1:
        stmt = stmt.where(
            or_(
                TimeSlot.day < today,
                and_(
                    TimeSlot.day == today,
                    TimeSlot.start_time <= now_time,
                ),
            )
        )

    return stmt

async def orm_get_bookings_page(
    session: AsyncSession,
    *,
    page: int = 1,
    per_page: int = 10,
    mode: int = 0,
    day_mode: int = 2,
) -> Page[Booking]:
    stmt = _bookings_stmt(mode=mode, day_mode=day_mode)
    return await paginate(session, stmt, page=page, per_page=per_page)

async def orm_get_bookings_for_export(
    session: AsyncSession,
    *,
    mode: int = 4,
    day_mode: int = 2,
) -> list[Booking]:
    stmt = _bookings_stmt(mode=mode, day_mode=day_mode)
    res = await session.execute(stmt)
    return cast(list[Booking], res.scalars().all())


async def orm_get_booking(session: AsyncSession, booking_id: int) -> Booking | None:
    stmt = (
        select(Booking)
        .options(selectinload(Booking.service), selectinload(Booking.slot))
        .where(Booking.id == booking_id)
    )
    res = await session.execute(stmt)
    return res.scalar_one_or_none()

async def orm_set_booking_payment_status(
    session: AsyncSession,
    *,
    booking_id: int,
    payment_status: str,
) -> bool:
    payment_status = (payment_status or "").strip()
    if payment_status not in {"unpaid", "paid"}:
        return False

    allowed_statuses = ("new", "confirmed", "done")

    try:
        result = cast(
            CursorResult[Any],
            await session.execute(
                update(Booking)
                .where(
                    Booking.id == booking_id,
                    Booking.status.in_(allowed_statuses),
                )
                .values(payment_status=payment_status)
            ),
        )
        if (result.rowcount or 0) != 1:
            await session.rollback()
            return False

        await session.commit()
        return True
    except Exception:
        await session.rollback()
        raise

async def orm_admin_set_booking_status(
    session: AsyncSession,
    *,
    booking_id: int,
    target_status: str,
) -> tuple[bool, str, Booking | None]:
    booking = await orm_get_booking(session, booking_id)
    if not booking:
        return False, "not_found", None

    current = booking.status
    if current == target_status:
        return True, "noop", booking

    if target_status == "confirmed":
        if current != "new":
            return False, "bad_transition", booking
    elif target_status == "done":
        if current != "confirmed":
            return False, "bad_transition", booking
        if booking.slot is None:
            return False, "missing_slot", booking

        if not booking_has_started(booking):
            return False, "too_early", booking
        
    elif target_status == "cancelled_by_admin":
        if current not in ACTIVE_BOOKING_STATUSES:
            return False, "bad_transition", booking
    else:
        return False, "unknown_target", booking

    try:
        result = cast(
            CursorResult[Any],
            await session.execute(
                update(Booking)
                .where(Booking.id == booking_id, Booking.status == current)
                .values(status=target_status)
            ),
        )
        if (result.rowcount or 0) != 1:
            await session.rollback()
            return False, "conflict", booking

        if target_status == "cancelled_by_admin" and booking.slot_id is not None:
            await _release_slot_if_no_active_bookings(session, booking.slot_id)

        await session.commit()
    except Exception:
        await session.rollback()
        raise

    updated = await orm_get_booking(session, booking_id)
    return True, "updated", updated


async def orm_get_setting(session: AsyncSession, key: str) -> AppSetting | None:
    res = await session.execute(select(AppSetting).where(AppSetting.key == key))
    return res.scalar_one_or_none()


async def orm_get_booking_reminder_lead_minutes(session: AsyncSession) -> int:
    setting = await orm_get_setting(session, BOOKING_REMINDER_LEAD_MINUTES_KEY)
    if not setting:
        return BOOKING_REMINDER_DEFAULT_MINUTES

    try:
        value = int(setting.value)
    except (TypeError, ValueError):
        return BOOKING_REMINDER_DEFAULT_MINUTES

    if value not in BOOKING_REMINDER_ALLOWED_MINUTES:
        return BOOKING_REMINDER_DEFAULT_MINUTES

    return value


async def orm_set_booking_reminder_lead_minutes(
    session: AsyncSession,
    minutes: int,
) -> bool:
    if minutes not in BOOKING_REMINDER_ALLOWED_MINUTES:
        return False

    setting = await orm_get_setting(session, BOOKING_REMINDER_LEAD_MINUTES_KEY)

    if setting is None:
        session.add(
            AppSetting(
                key=BOOKING_REMINDER_LEAD_MINUTES_KEY,
                value=str(minutes),
            )
        )
        await session.commit()
        return True

    setting.value = str(minutes)
    await session.commit()
    return True

async def orm_get_due_booking_reminders(
    session: AsyncSession,
    *,
    now: datetime | None = None,
    lead_minutes: int = 60,
) -> list[Booking]:
    current = now or booking_now()
    deadline = current + timedelta(minutes=lead_minutes)

    stmt = (
        select(Booking)
        .options(selectinload(Booking.service), selectinload(Booking.slot))
        .join(TimeSlot, Booking.slot_id == TimeSlot.id)
        .where(
            Booking.status == "confirmed",
            Booking.slot_id.is_not(None),
            Booking.reminder_sent_at.is_(None),
            TimeSlot.day >= current.date(),
            TimeSlot.day <= deadline.date(),
        )
        .order_by(
            TimeSlot.day.asc(),
            TimeSlot.start_time.asc(),
            Booking.id.asc(),
        )
    )

    res = await session.execute(stmt)
    bookings = cast(list[Booking], res.scalars().all())

    due: list[Booking] = []
    for booking in bookings:
        if not booking.slot:
            continue

        slot_dt = booking_slot_dt(booking.slot.day, booking.slot.start_time)
        if current < slot_dt <= deadline:
            due.append(booking)

    return due

async def orm_mark_booking_reminder_sent(
    session: AsyncSession,
    *,
    booking_id: int,
    sent_at: datetime | None = None,
) -> bool:
    sent_value = sent_at or booking_now()

    try:
        result = cast(
            CursorResult[Any],
            await session.execute(
                update(Booking)
                .where(
                    Booking.id == booking_id,
                    Booking.reminder_sent_at.is_(None),
                )
                .values(reminder_sent_at=sent_value)
            ),
        )
        if (result.rowcount or 0) != 1:
            await session.rollback()
            return False

        await session.commit()
        return True
    except Exception:
        await session.rollback()
        raise



# ----------------------------
# SERVICES (booking core)
# ----------------------------

async def orm_add_service(
    session: AsyncSession,
    *,
    title: str,
    description: str | None = None,
    price: str | int | float | Decimal | None = None,
) -> Service:
    price_dec: Decimal | None = None
    if price is not None:
        price_dec = Decimal(str(price)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    obj = Service(
        title=title.strip(),
        description=description,
        price=price_dec,
        is_active=True,
    )
    session.add(obj)
    await session.commit()
    await session.refresh(obj)
    return obj


async def orm_get_services(
    session: AsyncSession,
    *,
    include_inactive: bool = False,
) -> list[Service]:
    stmt = select(Service).order_by(Service.id.desc())
    if not include_inactive:
        stmt = stmt.where(Service.is_active == True)  # noqa: E712

    res = await session.execute(stmt)
    return cast(list[Service], res.scalars().all())


async def orm_get_service(session: AsyncSession, service_id: int) -> Service | None:
    res = await session.execute(select(Service).where(Service.id == service_id))
    return res.scalar_one_or_none()


async def orm_update_service(
    session: AsyncSession,
    service_id: int,
    *,
    title: str | None = None,
    description: str | None = None,
    price: str | int | float | Decimal | None = None,
    is_active: bool | None = None,
) -> None:
    values: dict = {}

    if title is not None:
        values["title"] = title.strip()
    if description is not None:
        values["description"] = description
    if price is not None:
        values["price"] = Decimal(str(price)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if is_active is not None:
        values["is_active"] = is_active

    if not values:
        return

    await session.execute(update(Service).where(Service.id == service_id).values(**values))
    await session.commit()


async def orm_delete_service(session: AsyncSession, service_id: int) -> None:
    await session.execute(delete(Service).where(Service.id == service_id))
    await session.commit()


async def orm_toggle_service_active(session: AsyncSession, service_id: int) -> None:
    obj = await orm_get_service(session, service_id)
    if not obj:
        return
    await orm_update_service(session, service_id, is_active=not obj.is_active)


async def orm_get_service_dependency_stats(
    session: AsyncSession,
    service_id: int,
) -> tuple[int, int, int]:
    slots_count_stmt = select(func.count()).where(TimeSlot.service_id == service_id)
    slots_count = int((await session.execute(slots_count_stmt)).scalar_one())

    bookings_count_stmt = select(func.count()).where(Booking.service_id == service_id)
    bookings_count = int((await session.execute(bookings_count_stmt)).scalar_one())

    active_bookings_count_stmt = select(func.count()).where(
        Booking.service_id == service_id,
        Booking.status.in_(ACTIVE_BOOKING_STATUSES),
    )
    active_bookings_count = int((await session.execute(active_bookings_count_stmt)).scalar_one())

    return slots_count, bookings_count, active_bookings_count


async def orm_get_active_booking_tg_ids_by_service(
    session: AsyncSession,
    service_id: int,
) -> list[int]:
    stmt = (
        select(Booking.tg_id)
        .where(
            Booking.service_id == service_id,
            Booking.status.in_(ACTIVE_BOOKING_STATUSES),
        )
        .distinct()
    )
    res = await session.execute(stmt)
    return [int(x) for x in res.scalars().all()]


async def orm_purge_service_with_dependencies(
    session: AsyncSession,
    service_id: int,
) -> tuple[bool, int, int]:
    try:
        bookings_result = cast(
            CursorResult[Any],
            await session.execute(delete(Booking).where(Booking.service_id == service_id)),
        )
        slots_result = cast(
            CursorResult[Any],
            await session.execute(delete(TimeSlot).where(TimeSlot.service_id == service_id)),
        )
        service_result = cast(
            CursorResult[Any],
            await session.execute(delete(Service).where(Service.id == service_id)),
        )
        if (service_result.rowcount or 0) != 1:
            await session.rollback()
            return False, 0, 0

        await session.commit()
        deleted_slots = int(slots_result.rowcount or 0)
        deleted_bookings = int(bookings_result.rowcount or 0)
        return True, deleted_slots, deleted_bookings
    except Exception:
        await session.rollback()
        raise


# ----------------------------
# TIMESLOTS (booking)
# ----------------------------


async def orm_get_timeslots_page(
    session: AsyncSession,
    *,
    service_id: int,
    page: int = 1,
    per_page: int = 10,
    mode: int = 0,  # 0 actual free, 1 booked, 2 all
) -> Page[TimeSlot]:
    stmt = select(TimeSlot).where(TimeSlot.service_id == service_id)

    now = booking_now()
    today = now.date()
    now_time = now.time()

    if mode == 0:
        stmt = stmt.where(
            TimeSlot.is_active == True,   # noqa: E712
            TimeSlot.is_booked == False,  # noqa: E712
            or_(
                TimeSlot.day > today,
                and_(
                    TimeSlot.day == today,
                    TimeSlot.start_time > now_time,
                ),
            ),
        )
    elif mode == 1:
        stmt = stmt.where(
            TimeSlot.is_active == True,  # noqa: E712
            TimeSlot.is_booked == True,  # noqa: E712
        )
    else:
        # mode == 2: all
        pass

    stmt = stmt.order_by(TimeSlot.day.asc(), TimeSlot.start_time.asc())
    return await paginate(session, stmt, page=page, per_page=per_page)

async def orm_add_timeslot(
    session: AsyncSession,
    *,
    service_id: int,
    day: date,
    start_time: time,
) -> TimeSlot:
    obj = TimeSlot(service_id=service_id, day=day, start_time=start_time, is_active=True, is_booked=False)
    session.add(obj)
    try:
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    await session.refresh(obj)
    return obj

async def orm_add_timeslots_bulk(
    session: AsyncSession,
    *,
    service_id: int,
    day: date,
    times: list[time],
) -> tuple[list[time], list[time], list[time]]:
    """
    Массово создаёт слоты на один день.

    Возвращает:
    - created_times: что реально создали
    - duplicate_times: что уже существовало
    - past_times: что было отброшено как прошлое время (только для today)
    """
    if not times:
        return [], [], []

    unique_times = list(dict.fromkeys(times))
    created_times: list[time] = []
    duplicate_times: list[time] = []
    past_times: list[time] = []

    now = booking_now()
    today = now.date()

    filtered_times: list[time] = []
    for slot_time in unique_times:
        if day == today and booking_slot_dt(day, slot_time) <= now:
            past_times.append(slot_time)
            continue
        filtered_times.append(slot_time)

    if not filtered_times:
        return [], [], sorted(past_times)

    existing_stmt = select(TimeSlot.start_time).where(
        TimeSlot.service_id == service_id,
        TimeSlot.day == day,
    )
    existing_res = await session.execute(existing_stmt)
    existing_times = set(existing_res.scalars().all())

    new_times: list[time] = []
    for slot_time in filtered_times:
        if slot_time in existing_times:
            duplicate_times.append(slot_time)
        else:
            new_times.append(slot_time)

    if not new_times:
        return [], sorted(duplicate_times), sorted(past_times)

    session.add_all(
        [
            TimeSlot(
                service_id=service_id,
                day=day,
                start_time=slot_time,
                is_active=True,
                is_booked=False,
            )
            for slot_time in new_times
        ]
    )

    try:
        await session.commit()
    except Exception:
        await session.rollback()
        raise

    created_times = list(new_times)
    return sorted(created_times), sorted(duplicate_times), sorted(past_times)

async def orm_get_timeslots_days(
    session: AsyncSession,
    *,
    service_id: int,
    include_inactive: bool = False,
    include_booked: bool = False,
) -> list[date]:
    now = booking_now()
    today = now.date()
    now_time = now.time()

    stmt = select(TimeSlot.day).where(TimeSlot.service_id == service_id)

    if not include_inactive:
        stmt = stmt.where(TimeSlot.is_active == True)  # noqa: E712
    if not include_booked:
        stmt = stmt.where(TimeSlot.is_booked == False)  # noqa: E712

    stmt = stmt.where(
        or_(
            TimeSlot.day > today,
            and_(
                TimeSlot.day == today,
                TimeSlot.start_time > now_time,
            ),
        )
    )

    stmt = stmt.group_by(TimeSlot.day).order_by(TimeSlot.day.asc())
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def orm_get_timeslots_by_day(
    session: AsyncSession,
    *,
    service_id: int,
    day: date,
    include_inactive: bool = False,
    include_booked: bool = False,
) -> list[TimeSlot]:
    stmt = select(TimeSlot).where(
        TimeSlot.service_id == service_id,
        TimeSlot.day == day,
    )

    if not include_inactive:
        stmt = stmt.where(TimeSlot.is_active == True)  # noqa: E712
    if not include_booked:
        stmt = stmt.where(TimeSlot.is_booked == False)  # noqa: E712

    now = booking_now()
    today = now.date()

    if day < today:
        return []

    if day == today:
        stmt = stmt.where(TimeSlot.start_time > now.time())

    stmt = stmt.order_by(TimeSlot.start_time.asc())
    res = await session.execute(stmt)
    return list(res.scalars().all())

async def orm_get_timeslots_for_day(
    session: AsyncSession,
    *,
    service_id: int,
    day: date,
) -> list[TimeSlot]:
    stmt = (
        select(TimeSlot)
        .where(
            TimeSlot.service_id == service_id,
            TimeSlot.day == day,
        )
        .order_by(TimeSlot.start_time.asc())
    )
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def orm_get_timeslot(session: AsyncSession, slot_id: int) -> TimeSlot | None:
    res = await session.execute(select(TimeSlot).where(TimeSlot.id == slot_id))
    return res.scalar_one_or_none()


async def orm_toggle_timeslot_active(session: AsyncSession, slot_id: int) -> None:
    slot = await orm_get_timeslot(session, slot_id)
    if not slot:
        return
    await session.execute(
        update(TimeSlot).where(TimeSlot.id == slot_id).values(is_active=not slot.is_active)
    )
    await session.commit()


async def orm_delete_timeslot(session: AsyncSession, slot_id: int) -> None:
    await session.execute(delete(TimeSlot).where(TimeSlot.id == slot_id))
    await session.commit()


async def orm_update_timeslot_datetime(
    session: AsyncSession,
    *,
    slot_id: int,
    day: date,
    start_time: time,
) -> bool:
    try:
        booking_exists = (
            select(1)
            .where(Booking.slot_id == slot_id)
            .exists()
        )
        result = cast(
            CursorResult[Any],
            await session.execute(
                update(TimeSlot)
                .where(
                    TimeSlot.id == slot_id,
                    TimeSlot.is_booked == False,  # noqa: E712
                    ~booking_exists,
                )
                .values(day=day, start_time=start_time)
            ),
        )
        if (result.rowcount or 0) != 1:
            await session.rollback()
            return False
        await session.commit()
        return True
    except Exception:
        await session.rollback()
        raise


async def orm_slot_has_bookings(session: AsyncSession, slot_id: int) -> bool:
    stmt = select(func.count()).where(Booking.slot_id == slot_id)
    count = int((await session.execute(stmt)).scalar_one())
    return count > 0


async def orm_get_active_booking_tg_ids_by_slot(
    session: AsyncSession,
    slot_id: int,
) -> list[int]:
    stmt = (
        select(Booking.tg_id)
        .where(
            Booking.slot_id == slot_id,
            Booking.status.in_(ACTIVE_BOOKING_STATUSES),
        )
        .distinct()
    )
    res = await session.execute(stmt)
    return [int(x) for x in res.scalars().all()]


async def orm_release_slot_and_cancel_bookings(session: AsyncSession, slot_id: int) -> int:
    """
    Освобождает слот и переводит активные записи по нему в cancelled_by_admin.
    Возвращает количество отменённых записей.
    """
    try:
        booking_result = cast(
            CursorResult[Any],
            await session.execute(
                update(Booking)
                .where(
                    Booking.slot_id == slot_id,
                    Booking.status.in_(ACTIVE_BOOKING_STATUSES),
                )
                .values(status="cancelled_by_admin")
            ),
        )
        cancelled = int(booking_result.rowcount or 0)

        await session.execute(
            update(TimeSlot).where(TimeSlot.id == slot_id).values(is_booked=False)
        )
        await session.commit()
        return cancelled
    except Exception:
        await session.rollback()
        raise


async def orm_purge_slot_with_bookings(session: AsyncSession, slot_id: int) -> tuple[bool, int]:
    try:
        bookings_result = cast(
            CursorResult[Any],
            await session.execute(delete(Booking).where(Booking.slot_id == slot_id)),
        )
        slot_result = cast(
            CursorResult[Any],
            await session.execute(delete(TimeSlot).where(TimeSlot.id == slot_id)),
        )
        if (slot_result.rowcount or 0) != 1:
            await session.rollback()
            return False, 0

        await session.commit()
        return True, int(bookings_result.rowcount or 0)
    except Exception:
        await session.rollback()
        raise


# ----------------------------
# BOOKING (reserve slot)
# ----------------------------

async def orm_create_booking_for_slot(
    session: AsyncSession,
    *,
    tg_id: int,
    slot_id: int,
    customer_name: str | None = None,
    customer_phone: str | None = None,
) -> Booking | None:
    """
    Атомарно резервирует слот и создаёт Booking.
    Возвращает None если слот уже занят, неактивен, уже в прошлом
    или если на это же время уже есть активная запись по другой услуге.
    """
    slot = await orm_get_timeslot(session, slot_id)
    if not slot:
        return None

    now = booking_now()
    slot_dt = booking_slot_dt(slot.day, slot.start_time)

    if slot_dt <= now:
        return None

    today = now.date()
    now_time = now.time()

    other_slot = aliased(TimeSlot)

    active_conflict_exists = (
        select(1)
        .select_from(Booking)
        .join(other_slot, Booking.slot_id == other_slot.id)
        .where(
            Booking.status.in_(ACTIVE_BOOKING_STATUSES),
            other_slot.day == slot.day,
            other_slot.start_time == slot.start_time,
            other_slot.id != slot.id,
        )
        .exists()
    )

    try:
        reserve_result = cast(
            CursorResult[Any],
            await session.execute(
                update(TimeSlot)
                .where(
                    TimeSlot.id == slot_id,
                    TimeSlot.is_active == True,   # noqa: E712
                    TimeSlot.is_booked == False,  # noqa: E712
                    or_(
                        TimeSlot.day > today,
                        and_(
                            TimeSlot.day == today,
                            TimeSlot.start_time > now_time,
                        ),
                    ),
                    ~active_conflict_exists,
                )
                .values(is_booked=True)
            ),
        )
        if (reserve_result.rowcount or 0) != 1:
            await session.rollback()
            return None

        service = await orm_get_service(session, slot.service_id)
        service_title_snapshot = service.title if service else f"Услуга #{slot.service_id}"
        service_price_snapshot = service.price if service else None

        booking = Booking(
            tg_id=tg_id,
            service_id=slot.service_id,
            slot_id=slot.id,
            customer_name=customer_name,
            customer_phone=customer_phone,
            service_title_snapshot=service_title_snapshot,
            service_price_snapshot=service_price_snapshot,
            status="new",
        )
        session.add(booking)
        await session.commit()
        await session.refresh(booking)
        return booking
    except Exception:
        await session.rollback()
        raise

