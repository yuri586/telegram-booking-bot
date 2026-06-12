from __future__ import annotations

from profiles.base import DemoProfile
from profiles.psychologist.seed import seed
from profiles.psychologist.ui import ui

profile = DemoProfile(
    slug="psychologist",
    seed=seed,
    ui=ui,
)