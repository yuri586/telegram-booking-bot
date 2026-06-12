# database/models.py
from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Numeric, String, Text, Time, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    __abstract__ = True

    created: Mapped[DateTime] = mapped_column(DateTime, default=func.now())
    updated: Mapped[DateTime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())


# ----------------------------
# CORE: banners (L0 pages)
# ----------------------------
class Banner(Base):
    __tablename__ = "banners"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo: Mapped[str | None] = mapped_column(String(255), nullable=True)


# ----------------------------
# CORE: users
# ----------------------------
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    tg_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    first_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)


# ----------------------------
# CORE: sections (L1)
# ----------------------------
class Section(Base):
    __tablename__ = "sections"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # связь: один Section -> много ContentItem
    items: Mapped[list[ContentItem]] = relationship(
        back_populates="section",
        cascade="all, delete-orphan",
        order_by="ContentItem.sort_order",
    )


# ----------------------------
# CORE: content items (L2 list + L3 card)
# ----------------------------
class ContentItem(Base):
    """
    Универсальная сущность “контент”.
    Примеры:
    - пост/страница автора
    - работа художника (картинка + описание)
    - услуга (текст + фото)
    - статья/глава/карточка и т.д.
    """
    __tablename__ = "content_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    section_id: Mapped[int] = mapped_column(
        ForeignKey("sections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # для ручной сортировки внутри раздела
    sort_order: Mapped[int] = mapped_column(default=0)

    # опционально: “скрыть, но не удалить”
    is_active: Mapped[bool] = mapped_column(default=True)

    section: Mapped[Section] = relationship(back_populates="items")


# ----------------------------
# PLUGIN/DEMO: products (оставляем как плагин)
# ----------------------------
class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    photo: Mapped[str | None] = mapped_column(String(150), nullable=True)

class Service(Base):
    __tablename__ = "services"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True)


# ----------------------------
# CORE: lead requests (универсальные заявки)
# ----------------------------
class AppSetting(Base):
    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    value: Mapped[str] = mapped_column(String(255), nullable=False)
class LeadRequest(Base):
    __tablename__ = "lead_requests"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # какой профиль породил заявку (photographer/psychologist/tutor)
    profile_slug: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # кто оставил заявку
    tg_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)

    name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    contact: Mapped[str | None] = mapped_column(String(150), nullable=True)  # телефон/ник/что угодно
    message: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(String(30), default="new", index=True)

class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    tg_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"), nullable=False)
    slot_id: Mapped[int | None] = mapped_column(ForeignKey("time_slots.id"), nullable=True, index=True)

    customer_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    customer_phone: Mapped[str | None] = mapped_column(String(30), nullable=True)

    service_title_snapshot: Mapped[str] = mapped_column(String(150), nullable=False)
    service_price_snapshot: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)

    status: Mapped[str] = mapped_column(String(30), default="new")
    payment_status: Mapped[str] = mapped_column(String(20), default="unpaid", index=True)

    reminder_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    service = relationship("Service")
    slot = relationship("TimeSlot")




class TimeSlot(Base):
    __tablename__ = "time_slots"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"), nullable=False, index=True)

    day: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)

    # слоты можно выключать без удаления
    is_active: Mapped[bool] = mapped_column(default=True)

    # занятость (чтобы не ловить гонки)
    is_booked: Mapped[bool] = mapped_column(default=False)

    service = relationship("Service")

    __table_args__ = (
        UniqueConstraint("service_id", "day", "start_time", name="uq_service_day_time"),
    )
