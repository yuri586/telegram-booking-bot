# profiles/ui_contract.py
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProfileUI:
    labels: Mapping[str, str]
    messages: Mapping[str, str]
    titles: Mapping[str, str] = field(default_factory=dict)