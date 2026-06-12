from __future__ import annotations

from config import settings
from profiles.common_labels import BASE_LABELS, BOOKING_LABELS
from profiles.registry import get_profile
from profiles.ui_contract import ProfileUI


def _ui() -> ProfileUI:
    return get_profile(settings.DEMO_PROFILE).ui


def _required_labels() -> set[str]:
    required = set(BASE_LABELS.keys())

    if settings.ENABLE_BOOKING:
        required |= set(BOOKING_LABELS.keys())

    return required


def ui_labels() -> dict[str, str]:
    labels = dict(_ui().labels)

    missing = _required_labels() - labels.keys()
    if missing:
        raise RuntimeError(f"Profile UI labels missing: {sorted(missing)}")

    return labels


def ui_msg(key: str, default: str = "") -> str:
    return _ui().messages.get(key, default)


def ui_title(key: str, default: str = "") -> str:
    return _ui().titles.get(key, default)