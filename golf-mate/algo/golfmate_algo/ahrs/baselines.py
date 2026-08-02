"""Optional Madgwick baseline (lazy import)."""

from __future__ import annotations

from typing import Any


def try_madgwick(*_args: Any, **_kwargs: Any) -> None:
    """Placeholder for A/B baseline; install ``ahrs`` to enable in future."""
    raise NotImplementedError(
        "Madgwick baseline is optional; use GolfGatedAHRS for P0."
    )
