# plugins/booking/statuses.py
from __future__ import annotations


def booking_status_icon(status: str) -> str:
    return {
        "new": "🕒",
        "confirmed": "✅",
        "done": "🏁",
        "cancelled_by_user": "🚫",
        "cancelled_by_admin": "🚫",
    }.get(status, "•")


def booking_status_text(status: str) -> str:
    return {
        "new": "ожидает подтверждения",
        "confirmed": "подтверждена",
        "done": "завершена",
        "cancelled_by_user": "отменена клиентом",
        "cancelled_by_admin": "отменена администратором",
    }.get(status, status)


def payment_status_icon(payment_status: str) -> str:
    return {
        "paid": "💳",
        "unpaid": "⌛",
    }.get(payment_status, "⌛")


def payment_status_text(payment_status: str) -> str:
    return {
        "unpaid": "⌛ не оплачено",
        "paid": "💳 оплачено",
    }.get(payment_status, payment_status)

def booking_status_label(status: str) -> str:
    return f"{booking_status_icon(status)} {booking_status_text(status)}"