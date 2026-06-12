from __future__ import annotations

import pytest

import common.ui as common_ui
from database.models import ContentItem, Section
from database.orm_query import (
    orm_add_lead_request,
    orm_get_lead_request,
    orm_get_leads_page,
    orm_set_lead_status,
    orm_update_item,
)
from profiles.registry import get_profile
from profiles.ui_contract import ProfileUI


@pytest.mark.asyncio
async def test_lead_request_create_normalizes_fields(session):
    lead = await orm_add_lead_request(
        session,
        profile_slug="  Psychologist  ",
        tg_id=123456,
        name="  Юрий  ",
        contact="  +79991234567  ",
        message="  Нужна консультация  ",
    )

    assert lead.profile_slug == "psychologist"
    assert lead.tg_id == 123456
    assert lead.name == "Юрий"
    assert lead.contact == "+79991234567"
    assert lead.message == "Нужна консультация"
    assert lead.status == "new"


@pytest.mark.asyncio
async def test_lead_request_empty_optional_fields_become_none(session):
    lead = await orm_add_lead_request(
        session,
        profile_slug="tutor",
        tg_id=100,
        name="   ",
        contact="",
        message="   ",
    )

    assert lead.name is None
    assert lead.contact is None
    assert lead.message is None


@pytest.mark.asyncio
async def test_get_lead_request_returns_created_object(session):
    created = await orm_add_lead_request(
        session,
        profile_slug="photographer",
        tg_id=555,
        name="Ирина",
        contact="@irina",
        message="Хочу узнать детали",
    )

    loaded = await orm_get_lead_request(session, created.id)

    assert loaded is not None
    assert loaded.id == created.id
    assert loaded.profile_slug == "photographer"
    assert loaded.tg_id == 555


@pytest.mark.asyncio
async def test_set_lead_status_updates_existing_lead(session):
    lead = await orm_add_lead_request(
        session,
        profile_slug="psychologist",
        tg_id=777,
        message="Запрос",
    )

    ok = await orm_set_lead_status(
        session,
        lead_id=lead.id,
        status="processed",
    )

    updated = await orm_get_lead_request(session, lead.id)

    assert ok is True
    assert updated is not None
    assert updated.status == "processed"


@pytest.mark.asyncio
async def test_set_lead_status_rejects_blank_status(session):
    lead = await orm_add_lead_request(
        session,
        profile_slug="tutor",
        tg_id=888,
        message="Нужен урок",
    )

    ok = await orm_set_lead_status(
        session,
        lead_id=lead.id,
        status="   ",
    )

    unchanged = await orm_get_lead_request(session, lead.id)

    assert ok is False
    assert unchanged is not None
    assert unchanged.status == "new"


@pytest.mark.asyncio
async def test_get_leads_page_filters_by_profile_and_mode(session):
    await orm_add_lead_request(
        session,
        profile_slug="psychologist",
        tg_id=1,
        message="psy-1",
    )
    lead_2 = await orm_add_lead_request(
        session,
        profile_slug="psychologist",
        tg_id=2,
        message="psy-2",
    )
    await orm_add_lead_request(
        session,
        profile_slug="tutor",
        tg_id=3,
        message="tutor-1",
    )

    changed = await orm_set_lead_status(
        session,
        lead_id=lead_2.id,
        status="processed",
    )
    assert changed is True

    page_new_psy = await orm_get_leads_page(
        session,
        profile_slug="psychologist",
        mode=0,
        page=1,
        per_page=10,
    )
    page_processed_psy = await orm_get_leads_page(
        session,
        profile_slug="psychologist",
        mode=1,
        page=1,
        per_page=10,
    )
    page_all_tutor = await orm_get_leads_page(
        session,
        profile_slug="tutor",
        mode=2,
        page=1,
        per_page=10,
    )

    assert [lead.profile_slug for lead in page_new_psy.items] == ["psychologist"]
    assert [lead.status for lead in page_new_psy.items] == ["new"]

    assert [lead.profile_slug for lead in page_processed_psy.items] == ["psychologist"]
    assert [lead.status for lead in page_processed_psy.items] == ["processed"]

    assert [lead.profile_slug for lead in page_all_tutor.items] == ["tutor"]


def test_get_profile_normalizes_slug() -> None:
    profile = get_profile("  PSYCHOLOGIST  ")

    assert profile.slug == "psychologist"


def test_get_profile_raises_for_unknown_slug() -> None:
    with pytest.raises(
        RuntimeError,
        match="Unknown DEMO_PROFILE='unknown-profile'",
    ):
        get_profile("unknown-profile")


def test_ui_labels_returns_labels_when_base_contract_is_satisfied(monkeypatch) -> None:
    monkeypatch.setattr(common_ui.settings, "ENABLE_BOOKING", False)

    fake_ui = ProfileUI(
        labels={
            "sections": "Разделы",
            "about": "О нас",
            "help": "Помощь",
            "contacts": "Контакты",
            "home": "Назад",
            "to_sections": "К разделам",
            "back_to_list": "К списку",
            "home_main": "На главную",
        },
        messages={},
        titles={},
    )

    monkeypatch.setattr(common_ui, "_ui", lambda: fake_ui)

    labels = common_ui.ui_labels()

    assert labels["sections"] == "Разделы"
    assert labels["home_main"] == "На главную"


def test_ui_labels_raises_when_base_labels_missing(monkeypatch) -> None:
    monkeypatch.setattr(common_ui.settings, "ENABLE_BOOKING", False)

    fake_ui = ProfileUI(
        labels={
            "sections": "Разделы",
            "about": "О нас",
        },
        messages={},
        titles={},
    )

    monkeypatch.setattr(common_ui, "_ui", lambda: fake_ui)

    with pytest.raises(RuntimeError, match="Profile UI labels missing"):
        common_ui.ui_labels()


def test_ui_labels_requires_booking_labels_when_booking_enabled(monkeypatch) -> None:
    monkeypatch.setattr(common_ui.settings, "ENABLE_BOOKING", True)

    fake_ui = ProfileUI(
        labels={
            "sections": "Разделы",
            "about": "О нас",
            "help": "Помощь",
            "contacts": "Контакты",
            "home": "Назад",
            "to_sections": "К разделам",
            "back_to_list": "К списку",
            "home_main": "На главную",
        },
        messages={},
        titles={},
    )

    monkeypatch.setattr(common_ui, "_ui", lambda: fake_ui)

    with pytest.raises(RuntimeError, match="Profile UI labels missing"):
        common_ui.ui_labels()


def test_ui_labels_accepts_booking_labels_when_booking_enabled(monkeypatch) -> None:
    monkeypatch.setattr(common_ui.settings, "ENABLE_BOOKING", True)

    fake_ui = ProfileUI(
        labels={
            "sections": "Разделы",
            "about": "О нас",
            "help": "Помощь",
            "contacts": "Контакты",
            "home": "Назад",
            "to_sections": "К разделам",
            "back_to_list": "К списку",
            "home_main": "На главную",
            "to_services": "К услугам",
            "to_days": "К датам",
            "back": "Назад",
            "to_my_bookings": "К моим записям",
        },
        messages={},
        titles={},
    )

    monkeypatch.setattr(common_ui, "_ui", lambda: fake_ui)

    labels = common_ui.ui_labels()

    assert labels["to_services"] == "К услугам"
    assert labels["to_my_bookings"] == "К моим записям"

@pytest.mark.asyncio
async def test_orm_update_item_can_clear_photo(session):
    section = Section(title="Test section")
    session.add(section)
    await session.commit()
    await session.refresh(section)

    item = ContentItem(
        section_id=section.id,
        title="Test item",
        body="Body",
        photo="photo-file-id",
        sort_order=10,
        is_active=True,
    )
    session.add(item)
    await session.commit()
    await session.refresh(item)

    await orm_update_item(
        session,
        item.id,
        clear_photo=True,
    )

    await session.refresh(item)
    assert item.photo is None