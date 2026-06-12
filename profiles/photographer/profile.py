from __future__ import annotations

from profiles.base import DemoProfile
from profiles.photographer.seed import seed
from profiles.photographer.ui import ui

profile = DemoProfile(
    slug="photographer",
    seed=seed,
    ui=ui,
)