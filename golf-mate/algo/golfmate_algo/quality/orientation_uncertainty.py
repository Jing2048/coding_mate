"""Orientation uncertainty trajectory from AHRS gate / bias / innovation evidence."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from numpy.typing import ArrayLike, NDArray

ArrayF = NDArray[np.float64]


@dataclass
class OrientationUncertainty:
    """Per-sample orientation uncertainty (deg) plus swing summary stats."""

    sigma_deg: ArrayF
    summary: dict[str, float] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "sigma_deg": [float(x) if math.isfinite(float(x)) else None for x in self.sigma_deg],
            "summary": {k: float(v) for k, v in self.summary.items()},
            "meta": dict(self.meta),
        }

    def summary_only(self) -> dict[str, Any]:
        """Compact form for report meta (no full trajectory dump by default)."""
        return {
            "summary": {k: float(v) for k, v in self.summary.items()},
            "meta": dict(self.meta),
            "n": int(self.sigma_deg.shape[0]),
        }


def estimate_orientation_uncertainty(
    *,
    gate: ArrayLike | None = None,
    bias: ArrayLike | None = None,
    innovation_deg: ArrayLike | None = None,
    rest_mask: ArrayLike | None = None,
    n: int | None = None,
    base_sigma_deg: float = 1.5,
    gate_scale_deg: float = 8.0,
    innov_scale: float = 0.35,
    bias_scale_deg_per_rad_s: float = 25.0,
) -> OrientationUncertainty:
    """Build an orientation uncertainty trajectory from AHRS diagnostics.

    Heuristic (honest, not a calibrated Kalman P):
    * closed gate during dynamics → larger tilt uncertainty growth
    * accel innovation (deg) scales instantaneous uncertainty
    * gyro-bias magnitude scales a slow floor
    """
    gate_arr = None if gate is None else np.asarray(gate, dtype=np.float64).reshape(-1)
    innov = (
        None
        if innovation_deg is None
        else np.asarray(innovation_deg, dtype=np.float64).reshape(-1)
    )
    bias_arr = None if bias is None else np.asarray(bias, dtype=np.float64)
    rest = None if rest_mask is None else np.asarray(rest_mask, dtype=bool).reshape(-1)

    lengths = [a.shape[0] for a in (gate_arr, innov, rest) if a is not None]
    if n is None:
        n = int(max(lengths)) if lengths else 0
    n = int(n)
    sigma = np.full(n, float(base_sigma_deg), dtype=np.float64)
    if n == 0:
        return OrientationUncertainty(
            sigma_deg=sigma,
            summary={
                "mean_deg": float("nan"),
                "p50_deg": float("nan"),
                "p95_deg": float("nan"),
                "max_deg": float("nan"),
            },
            meta={"empty": 1.0},
        )

    bias_floor = 0.0
    if bias_arr is not None and bias_arr.size:
        b = bias_arr.reshape(-1, 3) if bias_arr.ndim == 2 else bias_arr.reshape(1, 3)
        # Interpolate bias norm onto length n if needed.
        bn = np.linalg.norm(b, axis=1)
        if bn.shape[0] == n:
            bias_floor = bias_scale_deg_per_rad_s * bn
        elif bn.shape[0] > 1:
            xp = np.linspace(0.0, 1.0, bn.shape[0])
            xq = np.linspace(0.0, 1.0, n)
            bias_floor = bias_scale_deg_per_rad_s * np.interp(xq, xp, bn)
        else:
            bias_floor = np.full(n, bias_scale_deg_per_rad_s * float(bn[-1]))

    for i in range(n):
        g = 0.0
        if gate_arr is not None and i < gate_arr.shape[0] and math.isfinite(float(gate_arr[i])):
            g = float(gate_arr[i])
        # Dynamics proxy: closed gate ⇒ less accel correction ⇒ higher uncertainty.
        dyn = gate_scale_deg * (1.0 - float(np.clip(g, 0.0, 1.0)))
        innov_term = 0.0
        if innov is not None and i < innov.shape[0] and math.isfinite(float(innov[i])):
            innov_term = innov_scale * float(innov[i])
        bf = float(bias_floor[i]) if np.size(bias_floor) == n else float(bias_floor)
        # At trusted rest with open gate, pull toward base + small innov.
        if rest is not None and i < rest.shape[0] and bool(rest[i]) and g > 0.3:
            dyn *= 0.25
        sigma[i] = max(base_sigma_deg, base_sigma_deg + dyn + innov_term + 0.15 * bf)

    finite = sigma[np.isfinite(sigma)]
    summary = {
        "mean_deg": float(np.mean(finite)) if finite.size else float("nan"),
        "p50_deg": float(np.percentile(finite, 50)) if finite.size else float("nan"),
        "p95_deg": float(np.percentile(finite, 95)) if finite.size else float("nan"),
        "max_deg": float(np.max(finite)) if finite.size else float("nan"),
        "base_sigma_deg": float(base_sigma_deg),
    }
    meta: dict[str, Any] = {
        "source": "ahrs_gate_bias_innovation",
        "calibrated": 0.0,
        "has_gate": float(gate_arr is not None),
        "has_innovation": float(innov is not None),
        "has_bias": float(bias_arr is not None),
    }
    return OrientationUncertainty(sigma_deg=sigma, summary=summary, meta=meta)


__all__ = ["OrientationUncertainty", "estimate_orientation_uncertainty"]
