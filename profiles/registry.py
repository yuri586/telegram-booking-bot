from __future__ import annotations

from profiles.base import DemoProfile


def get_profile(slug: str) -> DemoProfile:
    slug = (slug or "").strip().lower()

    if slug == "photographer":
        from profiles.photographer.profile import profile
        return profile
    if slug == "psychologist":
        from profiles.psychologist.profile import profile
        return profile
    if slug == "tutor":
        from profiles.tutor.profile import profile
        return profile

    raise RuntimeError(f"Unknown DEMO_PROFILE='{slug}'. Available: photographer, psychologist, tutor")