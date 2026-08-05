"""Optional per-swing / per-session context for strategy features."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SwingContext:
    """Context for strategy precursors. Missing fields abstain — never invent.

    ``setting``: ``practice`` | ``round`` | ``unknown``
    ``pressure``: explicit pressure flag when known; ``None`` means abstain
    ``club_id``: opaque club identifier (optional)
    ``miss_direction``: signed lateral miss when outcome known (negative = left)
    ``outcome``: free-form outcome tag when available (e.g. fairway/miss)
    """

    setting: str = "unknown"
    pressure: bool | None = None
    club_id: str | None = None
    miss_direction: float | None = None
    outcome: str | None = None
    extras: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "setting": self.setting,
            "pressure": self.pressure,
            "club_id": self.club_id,
            "miss_direction": self.miss_direction,
            "outcome": self.outcome,
            "extras": dict(self.extras),
        }

    @property
    def has_miss_context(self) -> bool:
        return self.miss_direction is not None or self.outcome is not None
