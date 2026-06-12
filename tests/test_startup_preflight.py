from __future__ import annotations

import pytest

import app as app_module
import config
import database.seed as database_seed
from database.orm_query import orm_add_service, orm_has_seeded_profile_data


def test_preflight_allows_booking_when_admin_ids_present(monkeypatch):
    monkeypatch.setattr(config.settings, "ENABLE_BOOKING", True)
    monkeypatch.setattr(config.settings, "ADMIN_IDS", {123456})

    config.validate_startup_preflight()


def test_preflight_blocks_booking_without_admin_ids(monkeypatch):
    monkeypatch.setattr(config.settings, "ENABLE_BOOKING", True)
    monkeypatch.setattr(config.settings, "ADMIN_IDS", set())

    with pytest.raises(
        RuntimeError,
        match="Booking launch preflight failed: ENABLE_BOOKING=1 requires ADMIN_IDS to be configured.",
    ):
        config.validate_startup_preflight()


def test_preflight_allows_non_booking_mode_without_admin_ids(monkeypatch):
    monkeypatch.setattr(config.settings, "ENABLE_BOOKING", False)
    monkeypatch.setattr(config.settings, "ADMIN_IDS", set())

    config.validate_startup_preflight()





@pytest.mark.asyncio
async def test_seed_demo_guard_allows_empty_db(session):
    has_data = await orm_has_seeded_profile_data(session)
    assert has_data is False


@pytest.mark.asyncio
async def test_seed_demo_guard_detects_existing_profile_data(session):
    await orm_add_service(
        session,
        title="Тестовая услуга",
        description=None,
        price=None,
    )

    has_data = await orm_has_seeded_profile_data(session)
    assert has_data is True


class _FakeProfile:
    slug = "test-profile"

    def __init__(self) -> None:
        self.seed_called = False

    async def seed(self, session) -> None:
        self.seed_called = True


class _SessionCtx:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_cli_seed_allows_empty_db(session, monkeypatch):
    profile = _FakeProfile()

    monkeypatch.setattr(database_seed, "get_profile", lambda slug: profile)
    monkeypatch.setattr(database_seed, "session_maker", lambda: _SessionCtx(session))

    await database_seed.seed()

    assert profile.seed_called is True


@pytest.mark.asyncio
async def test_cli_seed_blocks_non_empty_db(session, monkeypatch):
    profile = _FakeProfile()

    await orm_add_service(
        session,
        title="Тестовая услуга",
        description=None,
        price=None,
    )

    monkeypatch.setattr(database_seed, "get_profile", lambda slug: profile)
    monkeypatch.setattr(database_seed, "session_maker", lambda: _SessionCtx(session))

    with pytest.raises(
        RuntimeError,
        match="Demo seed requires an empty DB. One profile = one DB. Use a fresh DB_URL for another profile.",
    ):
        await database_seed.seed()

    assert profile.seed_called is False

@pytest.mark.asyncio
async def test_run_smoke_checks_db_connectivity(session, monkeypatch):
    called = False

    async def fake_get_banner(db_session, name: str):
        nonlocal called
        called = True
        assert db_session is session
        assert name == "main"
        return None

    monkeypatch.setattr(app_module, "session_maker", lambda: _SessionCtx(session))
    monkeypatch.setattr(app_module, "orm_get_banner", fake_get_banner)
    monkeypatch.setattr(app_module, "create_dispatcher", lambda c: object())
    monkeypatch.setattr(app_module, "get_profile", lambda slug: object())
    monkeypatch.setattr(app_module, "caps", lambda: object())

    await app_module.run_smoke()

    assert called is True


@pytest.mark.asyncio
async def test_run_smoke_fails_when_db_check_fails(session, monkeypatch):
    async def fake_get_banner(db_session, name: str):
        raise RuntimeError("db connectivity failed")

    monkeypatch.setattr(app_module, "session_maker", lambda: _SessionCtx(session))
    monkeypatch.setattr(app_module, "orm_get_banner", fake_get_banner)
    monkeypatch.setattr(app_module, "create_dispatcher", lambda c: object())
    monkeypatch.setattr(app_module, "get_profile", lambda slug: object())
    monkeypatch.setattr(app_module, "caps", lambda: object())

    with pytest.raises(RuntimeError, match="db connectivity failed"):
        await app_module.run_smoke()