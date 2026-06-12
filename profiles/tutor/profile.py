from profiles.base import DemoProfile

from .seed import seed
from .ui import ui

profile = DemoProfile(
    slug="tutor",
    seed=seed,
    ui=ui,
)