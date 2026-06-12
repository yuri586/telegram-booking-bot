from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import cast

from aiogram import types
from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from common.capabilities import caps as get_caps
from database.models import Booking, ContentItem, Section, Service, TimeSlot
from keyboards.callbacks import (
    AdminCB,
    BannerAdminCB,
    BookingAdminCB,
    BookingCB,
    LeadCB,
    MenuCB,
    ServiceAdminCB,
    SlotAdminCB,
)
from plugins.booking.statuses import (
    booking_status_icon,
    payment_status_icon,
)
from plugins.registry import load_enabled_plugin_menu_buttons
from utils.paginator import Page


# ----------------------------
# COMMON: inline buttons builder
# ----------------------------
def get_inline_buttons(
    *,
    btns: Mapping[str, str],
    sizes: tuple[int, ...] = (2,),
) -> types.InlineKeyboardMarkup:
    keyboard = InlineKeyboardBuilder()

    for text, value in btns.items():
        if value.startswith(("http://", "https://", "tg://")):
            keyboard.add(InlineKeyboardButton(text=text, url=value))
        else:
            keyboard.add(InlineKeyboardButton(text=text, callback_data=value))

    return cast(types.InlineKeyboardMarkup, keyboard.adjust(*sizes).as_markup())


# ----------------------------
# USER MENU CALLBACKS
# ----------------------------



def kb_level0(
    labels: Mapping[str, str],
) -> types.InlineKeyboardMarkup:
    c = get_caps()
    plugin_btns = load_enabled_plugin_menu_buttons(c)

    btns: dict[str, str] = {}

    for text, callback_data in plugin_btns:
        btns[text] = callback_data

    btns.update(
        {
            labels["sections"]: MenuCB(level=1, page="sections").pack(),
            labels["about"]: MenuCB(level=0, page="about").pack(),
            labels["help"]: MenuCB(level=0, page="help").pack(),
            labels["contacts"]: MenuCB(level=0, page="contacts").pack(),
        }
    )

    if plugin_btns:
        return get_inline_buttons(btns=btns, sizes=(2, 2, 2))
    return get_inline_buttons(btns=btns, sizes=(2, 2))


def kb_sections(
    sections: list[Section],
    labels: Mapping[str, str],
) -> types.InlineKeyboardMarkup:
    keyboard = InlineKeyboardBuilder()

    for s in sections:
        keyboard.add(
            InlineKeyboardButton(
                text=s.title,
                callback_data=MenuCB(level=2, page="section", section=s.id).pack(),
            )
        )

    keyboard.row(
        InlineKeyboardButton(
            text=labels["home"],  # было "⬅️ Назад"
            callback_data=MenuCB(level=0, page="main").pack(),
        )
    )

    return cast(types.InlineKeyboardMarkup, keyboard.adjust(2).as_markup())


def kb_items_list(
    section_id: int,
    page: Page[ContentItem],
    labels: Mapping[str, str],
) -> types.InlineKeyboardMarkup:
    keyboard = InlineKeyboardBuilder()

    for item in page.items:
        keyboard.add(
            InlineKeyboardButton(
                text=item.title,
                callback_data=MenuCB(level=3, page="item", section=section_id, item=item.id, p=page.page).pack(),
            )
        )

    nav = []
    if page.has_prev:
        nav.append(
            InlineKeyboardButton(
                text="◀️",
                callback_data=MenuCB(level=2, page="section", section=section_id, p=page.prev_page or 1).pack(),
            )
        )
    if page.has_next:
        nav.append(
            InlineKeyboardButton(
                text="▶️",
                callback_data=MenuCB(level=2, page="section", section=section_id, p=page.next_page or (page.page + 1)).pack(),
            )
        )
    if nav:
        keyboard.row(*nav)

    keyboard.row(
        InlineKeyboardButton(
            text=labels["to_sections"],
            callback_data=MenuCB(level=1, page="sections").pack(),
        ),
        InlineKeyboardButton(
            text=labels["home_main"],
            callback_data=MenuCB(level=0, page="main").pack(),
        ),
    )

    return cast(types.InlineKeyboardMarkup, keyboard.adjust(1).as_markup())

def kb_lead_request_types(options: list[tuple[str, str]]) -> types.InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    for text, value in options:
        kb.add(
            InlineKeyboardButton(
                text=text,
                callback_data=LeadCB(action="type", request_type=value).pack(),
            )
        )

    kb.row(
        InlineKeyboardButton(
            text="🏠 На главную",
            callback_data=MenuCB(level=0, page="main").pack(),
        )
    )

    return cast(types.InlineKeyboardMarkup, kb.adjust(2).as_markup())


def kb_lead_confirm() -> types.InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    kb.row(
        InlineKeyboardButton(
            text="✅ Отправить",
            callback_data=LeadCB(action="send").pack(),
        )
    )
    kb.row(
        InlineKeyboardButton(
            text="🔁 Заполнить заново",
            callback_data=LeadCB(action="restart").pack(),
        ),
        InlineKeyboardButton(
            text="❌ Отмена",
            callback_data=LeadCB(action="cancel").pack(),
        ),
    )

    return kb.as_markup()


def kb_lead_success() -> types.InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    kb.row(
        InlineKeyboardButton(
            text="📝 Оставить заявку",
            callback_data=LeadCB(action="start").pack(),
        ),
        InlineKeyboardButton(
            text="🏠 На главную",
            callback_data=MenuCB(level=0, page="main").pack(),
        ),
    )

    return kb.as_markup()

_WEEKDAY_SHORT_RU = ("пн", "вт", "ср", "чт", "пт", "сб", "вс")


def _format_booking_day_label(day_value: date) -> str:
    return f"{day_value.strftime('%d.%m')} ({_WEEKDAY_SHORT_RU[day_value.weekday()]})"


# ----------------------------
# ADMIN CMS CALLBACKS
# ----------------------------


def kb_admin_services_for_slots(services: list[Service]) -> types.InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for s in services:
        kb.add(
            InlineKeyboardButton(
                text=s.title,
                callback_data=SlotAdminCB(action="list", service=s.id, p=1, mode=0).pack(),
            )
        )
    kb.row(
        InlineKeyboardButton(
            text="🧾 К карточкам услуг",
            callback_data=ServiceAdminCB(action="list", show=1).pack(),
        )
    )
    kb.row(InlineKeyboardButton(text="🏠 В админ-меню", callback_data=SlotAdminCB(action="home").pack()))
    return cast(types.InlineKeyboardMarkup, kb.adjust(1).as_markup())

def kb_admin_timeslots(service_id: int, page: Page[TimeSlot], *, mode: int) -> types.InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    mode_text = {0: "✅ Актуальные", 1: "🚫 Занятые", 2: "📦 Все"}.get(mode, "✅ Актуальные")
    kb.row(
        InlineKeyboardButton(
            text=f"Режим: {mode_text}",
            callback_data=SlotAdminCB(action="mode", service=service_id, p=page.page, mode=mode).pack(),
        )
    )

    for slot in page.items:
        status = "✅" if (slot.is_active and not slot.is_booked) else ("🚫" if slot.is_booked else "⏸️")
        title = f"{status} {slot.day.isoformat()} {slot.start_time.strftime('%H:%M')}"
        kb.add(
            InlineKeyboardButton(
                text=title,
                callback_data=SlotAdminCB(action="open", service=service_id, slot=slot.id, p=page.page, mode=mode).pack(),
            )
        )
    kb.adjust(1)

    nav = []
    if page.has_prev:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=SlotAdminCB(action="list", service=service_id, p=page.prev_page or 1, mode=mode).pack()))
    if page.has_next:
        nav.append(InlineKeyboardButton(text="▶️", callback_data=SlotAdminCB(action="list", service=service_id, p=page.next_page or (page.page + 1), mode=mode).pack()))
    if nav:
        kb.row(*nav)

    kb.row(
        InlineKeyboardButton(
            text="➕ Добавить слот",
            callback_data=SlotAdminCB(action="add", service=service_id, p=1, mode=mode).pack(),
        )
    )

    kb.row(
    InlineKeyboardButton(
        text="⚡ Сегодня",
        callback_data=SlotAdminCB(
            action="add_today",
            service=service_id,
            p=page.page,
            mode=mode,
        ).pack(),
    ),
    InlineKeyboardButton(
        text="⚡ Завтра",
        callback_data=SlotAdminCB(
            action="add_tomorrow",
            service=service_id,
            p=page.page,
            mode=mode,
        ).pack(),
        ),
    )

    kb.row(
        InlineKeyboardButton(
            text="⚡ Массово добавить",
            callback_data=SlotAdminCB(action="bulk_add", service=service_id, p=page.page, mode=mode).pack(),
        )
    )

    kb.row(
        InlineKeyboardButton(
            text="🗓️ Период + дни",
            callback_data=SlotAdminCB(
                action="bulk_range",
                service=service_id,
                p=page.page,
                mode=mode,
            ).pack(),
        )
    )
    
    kb.row(
        InlineKeyboardButton(
            text="📋 Копировать день",
            callback_data=SlotAdminCB(action="copy_day", service=service_id, p=page.page, mode=mode).pack(),
        )
    )

    kb.row(
        InlineKeyboardButton(text="⬅️ К услугам", callback_data=SlotAdminCB(action="services").pack()),
        InlineKeyboardButton(
            text="🧾 К карточкам услуг",
            callback_data=ServiceAdminCB(action="list", show=1).pack(),
        ),
    )
    return kb.as_markup()

def kb_admin_timeslot_card(
    service_id: int,
    slot_id: int,
    *,
    p: int,
    mode: int,
    is_active: bool,
    is_booked: bool,
    has_bookings: bool,
    ) -> types.InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    kb.row(
        InlineKeyboardButton(text="✏️ Изменить", callback_data=SlotAdminCB(action="edit", service=service_id, slot=slot_id, p=p, mode=mode).pack()),
        InlineKeyboardButton(text=("⏸️ Выкл" if is_active else "▶️ Вкл"), callback_data=SlotAdminCB(action="toggle_active", service=service_id, slot=slot_id, p=p, mode=mode).pack()),
    )
    kb.row(
        InlineKeyboardButton(text="🗑️ Удалить", callback_data=SlotAdminCB(action="del", service=service_id, slot=slot_id, p=p, mode=mode).pack()),
    )

    if is_booked:
        kb.row(
            InlineKeyboardButton(text="🔓 Освободить слот и отменить записи", callback_data=SlotAdminCB(action="free", service=service_id, slot=slot_id, p=p, mode=mode).pack())
        )
    if has_bookings:
        kb.row(
            InlineKeyboardButton(
                text="🧹 Удалить с очисткой",
                callback_data=SlotAdminCB(action="purge_ask", service=service_id, slot=slot_id, p=p, mode=mode).pack(),
            )
        )

    kb.row(
        InlineKeyboardButton(text="⬅️ К списку", callback_data=SlotAdminCB(action="list", service=service_id, p=p, mode=mode).pack()),
    )

    return kb.as_markup()


def kb_admin_timeslot_purge_confirm(service_id: int, slot_id: int, *, p: int, mode: int) -> types.InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(
            text="⚠️ Да, удалить с очисткой",
            callback_data=SlotAdminCB(action="purge_do", service=service_id, slot=slot_id, p=p, mode=mode).pack(),
        )
    )
    kb.row(
        InlineKeyboardButton(
            text="⬅️ Назад к слоту",
            callback_data=SlotAdminCB(action="open", service=service_id, slot=slot_id, p=p, mode=mode).pack(),
        )
    )
    kb.row(
        InlineKeyboardButton(
            text="⬅️ К списку",
            callback_data=SlotAdminCB(action="list", service=service_id, p=p, mode=mode).pack(),
        )
    )
    return kb.as_markup()


def kb_admin_sections(sections: list[Section]) -> types.InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    for s in sections:
        kb.add(
            InlineKeyboardButton(
                text=f"📁 {s.title}",
                callback_data=AdminCB(action="section_open", section=s.id, p=1, mode=0).pack(),
            )
        )

    kb.row(
        InlineKeyboardButton(
            text="🏠 В админ-меню",
            callback_data=AdminCB(action="home").pack(),
        )
    )

    return cast(types.InlineKeyboardMarkup, kb.adjust(2).as_markup())

def kb_admin_section_card(section_id: int) -> types.InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    kb.row(
        InlineKeyboardButton(
            text="✏️ Изменить заголовок",
            callback_data=AdminCB(action="section_edit_title", section=section_id, p=1, mode=0).pack(),
        ),
        InlineKeyboardButton(
            text="📝 Изменить описание",
            callback_data=AdminCB(action="section_edit_description", section=section_id, p=1, mode=0).pack(),
        ),
    )

    kb.row(
        InlineKeyboardButton(
            text="🖼️ Изменить фото",
            callback_data=AdminCB(action="section_edit_photo", section=section_id, p=1, mode=0).pack(),
        )
    )

    kb.row(
        InlineKeyboardButton(
            text="🧩 К элементам",
            callback_data=AdminCB(action="items", section=section_id, p=1, mode=0).pack(),
        )
    )

    kb.row(
        InlineKeyboardButton(
            text="⬅️ К разделам",
            callback_data=AdminCB(action="sections").pack(),
        ),
        InlineKeyboardButton(
            text="🏠 В админ-меню",
            callback_data=AdminCB(action="home").pack(),
        ),
    )

    return kb.as_markup()

def _mode_title(mode: int) -> str:
    return {0: "✅ Активные", 1: "🙈 Скрытые", 2: "📦 Все"}.get(mode, "✅ Активные")

def kb_admin_items(section_id: int, page: Page[ContentItem], *, mode: int) -> types.InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    kb.row(
        InlineKeyboardButton(
            text=f"Режим: {_mode_title(mode)}",
            callback_data=AdminCB(action="toggle_mode", section=section_id, p=page.page, mode=mode).pack(),
        )
    )

    for it in page.items:
        prefix = "✅" if it.is_active else "🚫"
        kb.add(
            InlineKeyboardButton(
                text=f"{prefix} {it.title}",
                callback_data=AdminCB(action="open", section=section_id, item=it.id, p=page.page, mode=mode).pack(),
            )
        )

    kb.adjust(1)

    # pagination
    nav = []
    if page.has_prev:
        nav.append(
            InlineKeyboardButton(
                text="◀️",
                callback_data=AdminCB(action="items", section=section_id, p=page.prev_page or 1, mode=mode).pack(),
            )
        )
    if page.has_next:
        nav.append(
            InlineKeyboardButton(
                text="▶️",
                callback_data=AdminCB(action="items", section=section_id, p=page.next_page or (page.page + 1), mode=mode).pack(),
            )
        )
    if nav:
        kb.row(*nav)

    # actions
    kb.row(
        InlineKeyboardButton(
            text="➕ Добавить элемент",
            callback_data=AdminCB(action="add", section=section_id, p=page.page, mode=mode).pack(),
        )
    )
    kb.row(
        InlineKeyboardButton(text="⬅️ К разделам", callback_data=AdminCB(action="sections").pack()),
        InlineKeyboardButton(text="🏠 В админ-меню", callback_data=AdminCB(action="home").pack()),
    )

    return kb.as_markup()


def kb_admin_item_card(section_id: int, item_id: int, p: int, *, is_active: bool, mode: int) -> types.InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    kb.row(
        InlineKeyboardButton(
            text="🗑️ Удалить",
            callback_data=AdminCB(action="del", section=section_id, item=item_id, p=p, mode=mode).pack(),
        ),
        InlineKeyboardButton(
            text="✏️ Редактировать",
            callback_data=AdminCB(action="edit", section=section_id, item=item_id, p=p, mode=mode).pack(),
        ),
    )

    kb.row(
        InlineKeyboardButton(
            text=("🙈 Скрыть" if is_active else "👁️ Показать"),
            callback_data=AdminCB(action="toggle", section=section_id, item=item_id, p=p, mode=mode).pack(),
        )
    )

    kb.row(
        InlineKeyboardButton(
            text="⬅️ К элементам",
            callback_data=AdminCB(action="items", section=section_id, p=p, mode=mode).pack(),
        ),
        InlineKeyboardButton(text="🏠 В админ-меню", callback_data=AdminCB(action="home").pack()),
    )

    return cast(types.InlineKeyboardMarkup, kb.adjust(2).as_markup())





def kb_booking_services(services: list[Service], labels: Mapping[str, str]) -> types.InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for s in services:
        kb.add(
            InlineKeyboardButton(
                text=s.title,
                callback_data=BookingCB(action="days", service=s.id).pack(),
            )
        )
    kb.row(
        InlineKeyboardButton(
            text=labels["home_main"],
            callback_data=MenuCB(level=0, page="main").pack(),
        )
    )
    return cast(types.InlineKeyboardMarkup, kb.adjust(1).as_markup())


def kb_booking_days(service_id: int, days: list[date], labels: Mapping[str, str]) -> types.InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for d in days:
        kb.add(
            InlineKeyboardButton(
                text=_format_booking_day_label(d),
                callback_data=BookingCB(action="times", service=service_id, day=d.isoformat()).pack(),
            )
        )
    kb.row(
        InlineKeyboardButton(text=labels["to_services"], callback_data=BookingCB(action="services").pack()),
        InlineKeyboardButton(text=labels["home_main"], callback_data=MenuCB(level=0, page="main").pack()),
    )
    return cast(types.InlineKeyboardMarkup, kb.adjust(2).as_markup())


def kb_booking_times(service_id: int, day_iso: str, slots: list[TimeSlot], labels: Mapping[str, str]) -> types.InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for s in slots:
        kb.add(
            InlineKeyboardButton(
                text=s.start_time.strftime("%H:%M"),
                callback_data=BookingCB(action="confirm", service=service_id, day=day_iso, slot=s.id).pack(),
            )
        )
    kb.row(
        InlineKeyboardButton(text=labels["to_days"], callback_data=BookingCB(action="days", service=service_id).pack()),
        InlineKeyboardButton(text=labels["home_main"], callback_data=MenuCB(level=0, page="main").pack()),
    )
    return cast(types.InlineKeyboardMarkup, kb.adjust(3).as_markup())


def kb_booking_confirm(service_id: int, day_iso: str, slot_id: int, labels: Mapping[str, str]) -> types.InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(
            text="✅ Подтвердить",
            callback_data=BookingCB(action="commit", service=service_id, day=day_iso, slot=slot_id).pack(),
        )
    )
    kb.row(
        InlineKeyboardButton(text=labels["back"], callback_data=BookingCB(action="times", service=service_id, day=day_iso).pack()),
        InlineKeyboardButton(text=labels["home_main"], callback_data=MenuCB(level=0, page="main").pack()),
    )
    return cast(types.InlineKeyboardMarkup, kb.adjust(1).as_markup())


def kb_booking_success(labels: Mapping[str, str]) -> types.InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(
            text=labels["to_my_bookings"],
            callback_data=BookingCB(action="my").pack(),
        ),
        InlineKeyboardButton(
            text=labels["home_main"],
            callback_data=MenuCB(level=0, page="main").pack(),
        ),
    )
    return kb.as_markup()


def kb_booking_resume(labels: Mapping[str, str]) -> types.InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(
            text="📅 Записаться",
            callback_data=BookingCB(action="services").pack(),
        ),
        InlineKeyboardButton(
            text=labels["home_main"],
            callback_data=MenuCB(level=0, page="main").pack(),
        ),
    )
    return kb.as_markup()

def kb_booking_payment_notice() -> types.InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(
            text="📖 Мои записи",
            callback_data=BookingCB(action="my").pack(),
        )
    )
    return kb.as_markup()

def kb_booking_empty(labels: Mapping[str, str]) -> types.InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(
            text=labels["home_main"],
            callback_data=MenuCB(level=0, page="main").pack(),
        )
    )
    return kb.as_markup()


def _booking_title(booking: Booking) -> str:
    service_title = (
        getattr(booking, "service_title_snapshot", None)
        or (booking.service.title if booking.service else None)
        or f"Услуга #{booking.service_id}"
    )
    if booking.slot:
        date_part = booking.slot.day.strftime("%d.%m.%Y")
        time_part = booking.slot.start_time.strftime("%H:%M")
        title = f"{date_part} {time_part} • {service_title}"
    else:
        title = f"Без слота • {service_title}"
    return title if len(title) <= 64 else title[:63] + "…"


def kb_booking_my_list(bookings: list[Booking], labels: Mapping[str, str]) -> types.InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for booking in bookings:
        kb.row(
            InlineKeyboardButton(
                text=_booking_title(booking),
                callback_data=BookingCB(action="my_open", booking=booking.id).pack(),
            )
        )
    kb.row(
        InlineKeyboardButton(text="📅 Записаться ещё", callback_data=BookingCB(action="services").pack()),
        InlineKeyboardButton(text=labels["home_main"], callback_data=MenuCB(level=0, page="main").pack()),
    )
    return kb.as_markup()


def kb_booking_my_card(
    booking_id: int,
    labels: Mapping[str, str],
    *,
    can_cancel: bool,
) -> types.InlineKeyboardMarkup:
    
    kb = InlineKeyboardBuilder()
    if can_cancel:
        kb.row(
            InlineKeyboardButton(
                text="❌ Отменить запись",
                callback_data=BookingCB(action="cancel", booking=booking_id).pack(),
            )
        )
    kb.row(
        InlineKeyboardButton(text=labels["to_my_bookings"], callback_data=BookingCB(action="my").pack()),
        InlineKeyboardButton(text=labels["home_main"], callback_data=MenuCB(level=0, page="main").pack()),
    )
    return kb.as_markup()


def kb_booking_reminder() -> types.InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(
            text="📖 Мои записи",
            callback_data=BookingCB(action="my").pack(),
        )
    )
    return kb.as_markup()





def kb_services_admin_list(services: list[Service], *, show: int) -> types.InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    kb.row(
        InlineKeyboardButton(
            text=("👁️ Скрытые: ВКЛ" if show else "👁️ Скрытые: ВЫКЛ"),
            callback_data=ServiceAdminCB(action="list", show=(0 if show else 1)).pack(),
        )
    )

    for s in services:
        prefix = "✅" if s.is_active else "🚫"
        kb.add(
            InlineKeyboardButton(
                text=f"{prefix} {s.title}",
                callback_data=ServiceAdminCB(action="open", service=s.id, show=show).pack(),
            )
        )

    kb.row(
        InlineKeyboardButton(
            text="➕ Добавить услугу",
            callback_data=ServiceAdminCB(action="add", show=show).pack(),
        )
    )

    kb.row(
        InlineKeyboardButton(
            text="🏠 В админ-меню",
            callback_data=ServiceAdminCB(action="home").pack()
        )
    )

    return cast(types.InlineKeyboardMarkup, kb.adjust(1).as_markup())


def kb_service_admin_card(service_id: int, *, is_active: bool, show: int) -> types.InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    kb.row(
        InlineKeyboardButton(
            text="🕒 Расписание услуги",
            callback_data=ServiceAdminCB(action="slots", service=service_id, show=show).pack(),
        )
    )

    kb.row(
        InlineKeyboardButton(
            text=("🙈 Скрыть" if is_active else "👁️ Показать"),
            callback_data=ServiceAdminCB(action="toggle", service=service_id, show=show).pack(),
        )
    )
    kb.row(
        InlineKeyboardButton(
            text="✏️ Редактировать",
            callback_data=ServiceAdminCB(action="edit", service=service_id, show=show).pack(),
        ),
        InlineKeyboardButton(
            text="🗑️ Удалить",
            callback_data=ServiceAdminCB(action="del", service=service_id, show=show).pack(),
        ),
    )
    kb.row(
        InlineKeyboardButton(
            text="🧹 Удалить с очисткой",
            callback_data=ServiceAdminCB(action="purge_ask", service=service_id, show=show).pack(),
        )
    )
    kb.row(
        InlineKeyboardButton(
            text="⬅️ К списку",
            callback_data=ServiceAdminCB(action="list", show=show).pack(),
        )
    )

    return kb.as_markup()


def kb_service_admin_purge_confirm(service_id: int, *, show: int) -> types.InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(
            text="⚠️ Да, удалить с очисткой",
            callback_data=ServiceAdminCB(action="purge_do", service=service_id, show=show).pack(),
        )
    )
    kb.row(
        InlineKeyboardButton(
            text="⬅️ Назад к услуге",
            callback_data=ServiceAdminCB(action="open", service=service_id, show=show).pack(),
        )
    )
    kb.row(
        InlineKeyboardButton(
            text="⬅️ К списку",
            callback_data=ServiceAdminCB(action="list", show=show).pack(),
        )
    )
    return kb.as_markup()





def _booking_mode_title(mode: int) -> str:
    return {
        0: "🆕 Новые",
        1: "✅ Подтв.",
        2: "🏁 Заверш.",
        3: "🚫 Отменённые",
        4: "📦 Все",
    }.get(mode, "🆕 Новые")




def _booking_day_mode_title(day_mode: int) -> str:
    return {
        0: "🗓️ Будущие",
        1: "📜 Прошедшие",
        2: "🧾 Все даты",
    }.get(day_mode, "🧾 Все даты")


def _booking_customer_short(booking: Booking) -> str:
    name = (booking.customer_name or "").strip()
    if not name:
        return f"id:{booking.tg_id}"

    first_word = name.split()[0]
    return first_word if len(first_word) <= 12 else first_word[:11] + "…"

def _booking_admin_title(booking: Booking) -> str:
    service_title = (
        getattr(booking, "service_title_snapshot", None)
        or (booking.service.title if booking.service else None)
        or f"Услуга #{booking.service_id}"
    )
    payment_icon = payment_status_icon(getattr(booking, "payment_status", "unpaid"))
    customer_short = _booking_customer_short(booking)

    if booking.slot:
        dt_text = f"{booking.slot.day.strftime('%d.%m')} {booking.slot.start_time.strftime('%H:%M')}"
    else:
        dt_text = "без слота"

    title = (
        f"{booking_status_icon(booking.status)} "
        f"{payment_icon} "
        f"{dt_text} • {customer_short} • {service_title}"
    )
    return title if len(title) <= 64 else title[:63] + "…"


def kb_admin_bookings(page: Page[Booking], *, mode: int, day_mode: int) -> types.InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    kb.row(
        InlineKeyboardButton(
            text=f"Режим: {_booking_mode_title(mode)}",
            callback_data=BookingAdminCB(action="mode", p=page.page, mode=mode, day_mode=day_mode).pack(),
        )
    )
    kb.row(
        InlineKeyboardButton(
            text=f"Даты: {_booking_day_mode_title(day_mode)}",
            callback_data=BookingAdminCB(action="day_mode", p=page.page, mode=mode, day_mode=day_mode).pack(),
        )
    )

    for booking in page.items:
        kb.add(
            InlineKeyboardButton(
                text=_booking_admin_title(booking),
                callback_data=BookingAdminCB(action="open", booking=booking.id, p=page.page, mode=mode, day_mode=day_mode).pack(),
            )
        )
    kb.adjust(1)

    nav = []
    if page.has_prev:
        nav.append(
            InlineKeyboardButton(
                text="◀️",
                callback_data=BookingAdminCB(action="list", p=page.prev_page or 1, mode=mode, day_mode=day_mode).pack(),
            )
        )
    if page.has_next:
        nav.append(
            InlineKeyboardButton(
                text="▶️",
                callback_data=BookingAdminCB(action="list", p=page.next_page or (page.page + 1), mode=mode, day_mode=day_mode).pack(),
            )
        )
    if nav:
        kb.row(*nav)

    kb.row(
        InlineKeyboardButton(
            text="⬇️ Выгрузить CSV",
            callback_data=BookingAdminCB(action="export_csv", p=page.page, mode=mode, day_mode=day_mode).pack(),
        )
    )
    
    kb.row(
        InlineKeyboardButton(
            text="📣 Рассылка активным",
            callback_data=BookingAdminCB(
                action="broadcast",
                p=page.page,
                mode=mode,
                day_mode=day_mode,
            ).pack(),
        )
    )

    kb.row(
        InlineKeyboardButton(
            text="⏰ Напоминание",
            callback_data=BookingAdminCB(
                action="reminder_settings",
                p=page.page,
                mode=mode,
                day_mode=day_mode,
            ).pack(),
        )
    )

    kb.row(
        InlineKeyboardButton(
            text="🏠 В админ-меню",
            callback_data=BookingAdminCB(action="home").pack(),
        )
    )
    return kb.as_markup()


def kb_admin_booking_card(
    booking_id: int,
    *,
    status: str,
    payment_status: str,
    can_done: bool,
    p: int,
    mode: int,
    day_mode: int,
) -> types.InlineKeyboardMarkup:
    
    kb = InlineKeyboardBuilder()
    
    can_confirm = status == "new"
    can_cancel = status in {"new", "confirmed"}
   
    if can_confirm:
        kb.row(
            InlineKeyboardButton(
                text="✅ Подтвердить",
                callback_data=BookingAdminCB(
                    action="confirm",
                    booking=booking_id,
                    p=p,
                    mode=mode,
                    day_mode=day_mode,
                ).pack(),
            )
        )

    if can_done:
        kb.row(
            InlineKeyboardButton(
                text="🏁 Завершить",
                callback_data=BookingAdminCB(
                    action="done",
                    booking=booking_id,
                    p=p,
                    mode=mode,
                    day_mode=day_mode,
                ).pack(),
            )
        )

    if can_cancel:
        kb.row(
            InlineKeyboardButton(
                text="❌ Отменить",
                callback_data=BookingAdminCB(
                    action="cancel",
                    booking=booking_id,
                    p=p,
                    mode=mode,
                    day_mode=day_mode,
                ).pack(),
            )
        )
    
    payment_editable = status in {"new", "confirmed", "done"}

    if payment_editable and payment_status == "unpaid":
        kb.row(
            InlineKeyboardButton(
                text="💳 Отметить оплату",
                callback_data=BookingAdminCB(
                    action="mark_paid",
                    booking=booking_id,
                    p=p,
                    mode=mode,
                    day_mode=day_mode,
                ).pack(),
            )
        )
    elif payment_editable and payment_status == "paid":
        kb.row(
            InlineKeyboardButton(
                text="↩️ Снять отметку оплаты",
                callback_data=BookingAdminCB(
                    action="mark_unpaid",
                    booking=booking_id,
                    p=p,
                    mode=mode,
                    day_mode=day_mode,
                ).pack(),
            )
        )


    kb.row(
        InlineKeyboardButton(
            text="⬅️ К списку",
            callback_data=BookingAdminCB(action="list", p=p, mode=mode, day_mode=day_mode).pack(),
        ),
        InlineKeyboardButton(text="🏠 В админ-меню", callback_data=BookingAdminCB(action="home").pack()),
    )

    return kb.as_markup()


def kb_admin_banners() -> types.InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    titles = {
        "main": "🏠 Главная",
        "about": "ℹ️ О проекте",
        "help": "❓ Помощь",
        "contacts": "📞 Контакты",
    }

    for page, title in titles.items():
        kb.add(
            InlineKeyboardButton(
                text=title,
                callback_data=BannerAdminCB(action="open", page=page).pack(),
            )
        )

    kb.row(
        InlineKeyboardButton(
            text="🏠 В админ-меню",
            callback_data=BannerAdminCB(action="home").pack(),
        )
    )

    return cast(types.InlineKeyboardMarkup, kb.adjust(1).as_markup())

def kb_admin_banner_card(page: str) -> types.InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    kb.row(
        InlineKeyboardButton(
            text="✏️ Изменить текст",
            callback_data=BannerAdminCB(action="edit_desc", page=page).pack(),
        ),
        InlineKeyboardButton(
            text="🖼️ Изменить фото",
            callback_data=BannerAdminCB(action="edit_photo", page=page).pack(),
        ),
    )

    kb.row(
        InlineKeyboardButton(
            text="⬅️ К страницам",
            callback_data=BannerAdminCB(action="list").pack(),
        ),
        InlineKeyboardButton(
            text="🏠 В админ-меню",
            callback_data=BannerAdminCB(action="home").pack(),
        ),
    )

    return kb.as_markup()

def kb_admin_broadcast_confirm(*, p: int, mode: int, day_mode: int) -> types.InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    kb.row(
        InlineKeyboardButton(
            text="✅ Отправить",
            callback_data=BookingAdminCB(
                action="broadcast_send",
                p=p,
                mode=mode,
                day_mode=day_mode,
            ).pack(),
        )
    )
    kb.row(
        InlineKeyboardButton(
            text="❌ Отмена",
            callback_data=BookingAdminCB(
                action="broadcast_cancel",
                p=p,
                mode=mode,
                day_mode=day_mode,
            ).pack(),
        )
    )

    return kb.as_markup()

def _reminder_lead_label(minutes: int) -> str:
    return {
        60: "1 час",
        180: "3 часа",
        1440: "24 часа",
        2880: "48 часов",
    }.get(minutes, f"{minutes} мин")


def kb_admin_reminder_settings(
    *,
    p: int,
    mode: int,
    day_mode: int,
    current_minutes: int,
) -> types.InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    for value in (60, 180, 1440, 2880):
        label = _reminder_lead_label(value)
        if value == current_minutes:
            label = f"✅ {label}"

        kb.row(
            InlineKeyboardButton(
                text=label,
                callback_data=BookingAdminCB(
                    action="reminder_set",
                    p=p,
                    mode=mode,
                    day_mode=day_mode,
                    value=value,
                ).pack(),
            )
        )

    kb.row(
        InlineKeyboardButton(
            text="⬅️ К списку",
            callback_data=BookingAdminCB(
                action="list",
                p=p,
                mode=mode,
                day_mode=day_mode,
            ).pack(),
        )
    )

    return kb.as_markup()