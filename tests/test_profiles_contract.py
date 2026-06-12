from __future__ import annotations

from profiles.common_labels import BASE_LABELS, BOOKING_LABELS
from profiles.registry import get_profile
from profiles.ui_contract import ProfileUI

PROFILE_SLUGS = ("photographer", "psychologist", "tutor")

REQUIRED_MESSAGE_KEYS = {
    "welcome",
    "sections_title",
    "page_not_found",
    "section_missing",
    "section_empty",
    "item_or_section_missing",
    "item_not_found",
}


def test_all_demo_profiles_load() -> None:
    for slug in PROFILE_SLUGS:
        profile = get_profile(slug)
        assert profile.slug == slug
        assert isinstance(profile.ui, ProfileUI)
        assert callable(profile.seed)


def test_all_demo_profiles_have_required_labels() -> None:
    required_labels = set(BASE_LABELS) | set(BOOKING_LABELS)

    for slug in PROFILE_SLUGS:
        profile = get_profile(slug)
        labels = profile.ui.labels

        missing = required_labels - labels.keys()
        assert not missing, f"{slug} missing labels: {sorted(missing)}"

        for key in required_labels:
            assert isinstance(labels[key], str)
            assert labels[key].strip(), f"{slug} label '{key}' is empty"


def test_all_demo_profiles_have_required_messages() -> None:
    for slug in PROFILE_SLUGS:
        profile = get_profile(slug)
        messages = profile.ui.messages

        missing = REQUIRED_MESSAGE_KEYS - messages.keys()
        assert not missing, f"{slug} missing messages: {sorted(missing)}"

        for key in REQUIRED_MESSAGE_KEYS:
            assert isinstance(messages[key], str)
            assert messages[key].strip(), f"{slug} message '{key}' is empty"


def test_all_demo_profiles_have_main_title() -> None:
    for slug in PROFILE_SLUGS:
        profile = get_profile(slug)
        main_title = profile.ui.titles.get("main")

        assert isinstance(main_title, str), f"{slug} missing titles['main']"
        assert main_title.strip(), f"{slug} titles['main'] is empty"