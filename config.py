from __future__ import annotations

import os
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env", override=False)


TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"0", "false", "no", "off"}
LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
ENV_VALUES = {"dev", "prod"}


def get_required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(
            f"Environment variable '{name}' is missing. "
            f"Set it in environment or .env file."
        )
    return value


def env_bool(name: str, default: str = "0") -> bool:
    raw = os.getenv(name, default).strip().lower()

    if raw in TRUE_VALUES:
        return True
    if raw in FALSE_VALUES:
        return False

    raise RuntimeError(
        f"Environment variable '{name}' must be one of: "
        f"1/0/true/false/yes/no/on/off"
    )


def parse_admin_ids(value: str) -> set[int]:
    raw = value.strip()
    if not raw:
        return set()

    parts = [x.strip() for x in raw.split(",")]
    bad = [x for x in parts if not x.isdigit()]

    if bad:
        raise RuntimeError(
            f"ADMIN_IDS contains invalid values: {', '.join(bad)}"
        )

    return {int(x) for x in parts}


def env_choice(name: str, allowed: set[str], default: str) -> str:
    value = os.getenv(name, default).strip()

    if value not in allowed:
        raise RuntimeError(
            f"Environment variable '{name}' must be one of: "
            f"{', '.join(sorted(allowed))}"
        )

    return value

def env_timezone(name: str, default: str) -> str:
    value = os.getenv(name, default).strip()

    try:
        ZoneInfo(value)
    except ZoneInfoNotFoundError as e:
        raise RuntimeError(
            f"Environment variable '{name}' must be a valid IANA timezone, "
            "for example: UTC, Europe/Riga, Europe/Moscow"
        ) from e

    return value


class Settings:
    TOKEN: str = get_required_env("TOKEN")

    DEBUG: bool = env_bool("DEBUG", "0")

    DEBUG_INCOMING: bool = env_bool("DEBUG_INCOMING", "1")
    DEBUG_UPDATES_FULL: bool = env_bool("DEBUG_UPDATES_FULL", "0")
    DEBUG_OUTGOING: bool = env_bool("DEBUG_OUTGOING", "0")
    DEBUG_SQL: bool = env_bool("DEBUG_SQL", "0")

    RESET_DB: bool = env_bool("RESET_DB", "0")
    DB_URL: str = os.getenv("DB_URL", "sqlite+aiosqlite:///./db.sqlite3").strip()
    DB_ECHO: bool = DEBUG_SQL

    ADMIN_IDS: set[int] = parse_admin_ids(os.getenv("ADMIN_IDS", ""))

    ENABLE_DEBUG_MW: bool = DEBUG and env_bool("ENABLE_DEBUG_MW", "0")

    ENABLE_GROUPS: bool = env_bool("ENABLE_GROUPS", "0") or env_bool("ENABLE_PLUGIN_GROUPS", "0")
    ENABLE_SHOP: bool = env_bool("ENABLE_SHOP", "0") or env_bool("ENABLE_PLUGIN_SHOP", "0")
    ENABLE_BOOKING: bool = env_bool("ENABLE_BOOKING", "0")
    ENABLE_LEADS: bool = env_bool("ENABLE_LEADS", "0")

    # обратная совместимость
    ENABLE_PLUGIN_SHOP: bool = ENABLE_SHOP
    ENABLE_PLUGIN_GROUPS: bool = ENABLE_GROUPS

    ENV: str = env_choice("ENV", ENV_VALUES, "dev")
    DEMO_PROFILE: str = os.getenv("DEMO_PROFILE", "photographer").strip()
    SEED_DEMO: bool = env_bool("SEED_DEMO", "0")
    LOG_LEVEL: str = env_choice("LOG_LEVEL", LOG_LEVELS, "INFO")

    BOOKING_TIMEZONE: str = env_timezone("BOOKING_TIMEZONE", "UTC")


settings = Settings()

def validate_startup_preflight() -> None:
    if settings.ENABLE_BOOKING and not settings.ADMIN_IDS:
        raise RuntimeError(
            "Booking launch preflight failed: ENABLE_BOOKING=1 requires ADMIN_IDS to be configured."
        )