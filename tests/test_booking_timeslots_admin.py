from __future__ import annotations

from datetime import date, datetime, time

import plugins.booking.handlers_admin_timeslots as admin_timeslots


def test_slot_in_past_treats_current_minute_as_unavailable(monkeypatch):
    monkeypatch.setattr(
        admin_timeslots,
        "booking_now",
        lambda: datetime(2026, 3, 20, 12, 0),
    )

    assert admin_timeslots._slot_in_past(date(2026, 3, 20), time(12, 0)) is True
    assert admin_timeslots._slot_in_past(date(2026, 3, 20), time(12, 1)) is False