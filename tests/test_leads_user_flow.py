from __future__ import annotations

import pytest

from database.orm_query import orm_get_lead_request, orm_get_leads_page
from plugins.leads.handlers_user_leads import (
    build_lead_message,
    normalize_lead_contact,
    save_lead_request,
)


def test_normalize_lead_contact_accepts_phone():
    assert normalize_lead_contact("+79991234567") == "+79991234567"
    assert normalize_lead_contact("8 999 123 45 67") == "89991234567"


def test_normalize_lead_contact_accepts_username():
    assert normalize_lead_contact("@legal_helper") == "@legal_helper"


def test_normalize_lead_contact_rejects_bad_value():
    assert normalize_lead_contact("abc") is None
    assert normalize_lead_contact("@ab") is None


def test_build_lead_message_includes_request_type():
    text = build_lead_message("family", "Нужно понять порядок общения с ребёнком.")
    assert "Тип запроса: Семейный вопрос" in text
    assert "Нужно понять порядок общения с ребёнком." in text


@pytest.mark.asyncio
async def test_save_lead_request_persists_new_lead(session):
    lead = await save_lead_request(
        session,
        profile_slug="lawyer-demo",
        tg_id=101,
        request_type="money",
        name="Юрий",
        contact="+79991234567",
        description="Нужно разобраться с договором займа.",
    )

    assert lead.id > 0
    assert lead.status == "new"

    stored = await orm_get_lead_request(session, lead.id)
    assert stored is not None
    assert stored.profile_slug == "lawyer-demo"
    assert stored.tg_id == 101
    assert stored.name == "Юрий"
    assert stored.contact == "+79991234567"
    assert "Тип запроса: Договор / деньги" in (stored.message or "")


@pytest.mark.asyncio
async def test_saved_lead_appears_in_new_leads_page(session):
    lead = await save_lead_request(
        session,
        profile_slug="lawyer-demo",
        tg_id=202,
        request_type="bankruptcy",
        name="Ирина",
        contact="@irina_law",
        description="Нужна первичная консультация по банкротству.",
    )

    page = await orm_get_leads_page(session, page=1, per_page=10, profile_slug="lawyer-demo", mode=0)

    lead_ids = [item.id for item in page.items]
    assert lead.id in lead_ids