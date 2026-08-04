"""Versioned Apple Watch edge-trajectory I/O contract (``edge-trajectory-v1``).

Fixed 100 Hz IMU window in → phases / 64-pt trajectory / confidence /
``transition_rush`` out. Shared by the NumPy teacher/student baseline and the
Mac-side Core ML export hook.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

CONTRACT_VERSION = "edge-trajectory-v1"
INPUT_FS_HZ = 100.0
INPUT_CHANNELS: tuple[str, ...] = (
    "gyro_x",
    "gyro_y",
    "gyro_z",
    "accel_x",
    "accel_y",
    "accel_z",
)
MAX_SAMPLES = 512
TRAJECTORY_POINTS = 64
PHASE_NAMES: tuple[str, ...] = ("address", "top", "impact", "finish")
OUTPUT_DIM = 4 + TRAJECTORY_POINTS * 3 + 1 + 1  # 198

_SCHEMA_PATH = Path(__file__).with_name("edge_trajectory_schema.json")


@dataclass(frozen=True)
class EdgeTrajectoryOutput:
    """Structured edge-model outputs (physical units / normalized phases)."""

    version: str
    phases_norm: NDArray[np.float64]  # (4,)
    trajectory_xyz: NDArray[np.float64]  # (64, 3)
    confidence: float
    transition_rush: float

    def as_vector(self) -> NDArray[np.float64]:
        return np.concatenate(
            [
                np.asarray(self.phases_norm, dtype=np.float64).reshape(4),
                np.asarray(self.trajectory_xyz, dtype=np.float64).reshape(-1),
                np.asarray([self.confidence, self.transition_rush], dtype=np.float64),
            ]
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "phases_norm": {
                name: float(v) for name, v in zip(PHASE_NAMES, self.phases_norm)
            },
            "trajectory_xyz": np.asarray(self.trajectory_xyz, dtype=np.float64).tolist(),
            "confidence": float(self.confidence),
            "transition_rush": float(self.transition_rush),
        }

    @classmethod
    def from_vector(
        cls, vec: NDArray[np.floating], *, version: str = CONTRACT_VERSION
    ) -> EdgeTrajectoryOutput:
        v = np.asarray(vec, dtype=np.float64).reshape(-1)
        if v.size != OUTPUT_DIM:
            raise ValueError(f"edge output dim {v.size} != {OUTPUT_DIM}")
        phases = np.clip(v[:4], 0.0, 1.0)
        traj = v[4 : 4 + TRAJECTORY_POINTS * 3].reshape(TRAJECTORY_POINTS, 3)
        conf = float(np.clip(v[-2], 0.0, 1.0))
        rush = float(np.clip(v[-1], 0.0, 1.0))
        return cls(
            version=version,
            phases_norm=phases,
            trajectory_xyz=traj,
            confidence=conf,
            transition_rush=rush,
        )


def load_edge_trajectory_schema() -> dict[str, Any]:
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


def sample_trajectory_xyz(
    positions: NDArray[np.floating],
    *,
    address_idx: int,
    finish_idx: int,
    n_points: int = TRAJECTORY_POINTS,
) -> NDArray[np.float64]:
    """Uniformly sample address→finish wrist path; origin at address."""
    pos = np.asarray(positions, dtype=np.float64).reshape(-1, 3)
    n = pos.shape[0]
    if n < 2:
        raise ValueError("need >= 2 positions")
    i0 = int(np.clip(address_idx, 0, n - 1))
    i1 = int(np.clip(finish_idx, i0 + 1, n - 1))
    seg = pos[i0 : i1 + 1]
    seg = seg - seg[0]
    if seg.shape[0] == 1:
        return np.zeros((n_points, 3), dtype=np.float64)
    src = np.linspace(0.0, 1.0, seg.shape[0])
    dst = np.linspace(0.0, 1.0, n_points)
    return np.column_stack(
        [np.interp(dst, src, seg[:, axis]) for axis in range(3)]
    ).astype(np.float64)


def phases_to_norm(
    phases: dict[str, int] | Any,
    n_samples: int,
) -> NDArray[np.float64]:
    """Convert integer phase indices to [0, 1] on a length-``n_samples`` grid."""
    denom = max(int(n_samples) - 1, 1)
    if hasattr(phases, "as_dict"):
        d = phases.as_dict()
    else:
        d = dict(phases)
    return np.asarray(
        [
            float(d["address"]) / denom,
            float(d["top"]) / denom,
            float(d["impact"]) / denom,
            float(d["finish"]) / denom,
        ],
        dtype=np.float64,
    )


def transition_rush_from_report(report: Any) -> float:
    """Map early-release / casting proxies into a [0, 1] rush score."""
    extras = getattr(report.features, "extras", {}) or {}
    pro = {}
    if isinstance(report.meta, dict):
        pro = report.meta.get("pro_swing") or {}
    release = {}
    if isinstance(pro, dict):
        release = pro.get("release") or pro.get("release_profile") or {}
    morph = ""
    if isinstance(release, dict):
        morph = str(release.get("morphology", "") or "")
        onset = release.get("onset_s_to_impact")
        if onset is None:
            onset = release.get("release_onset_s_to_impact")
    else:
        onset = None

    rush = 0.25
    if morph == "early":
        rush = 0.85
    elif morph == "gradual":
        rush = 0.55
    elif morph == "abrupt":
        rush = 0.7
    elif morph == "late":
        rush = 0.2

    # Casting / early wrist peak relative to impact increases rush.
    peak_to_imp = float(getattr(report.features, "peak_omega_to_impact_s", 0.0) or 0.0)
    if peak_to_imp > 0.08:
        rush = min(1.0, rush + 0.25)
    elif peak_to_imp > 0.04:
        rush = min(1.0, rush + 0.1)

    casting = float(extras.get("casting_score", extras.get("early_release", 0.0)) or 0.0)
    rush = float(np.clip(0.7 * rush + 0.3 * casting, 0.0, 1.0))

    if onset is not None and np.isfinite(float(onset)):
        # Larger onset-to-impact ⇒ earlier release ⇒ more rush.
        rush = float(np.clip(0.6 * rush + 0.4 * min(1.0, float(onset) / 0.15), 0.0, 1.0))
    return rush


def confidence_from_report(report: Any) -> float:
    meta = report.meta if isinstance(report.meta, dict) else {}
    traj = meta.get("trajectory_quality") or meta.get("traj_quality") or {}
    if isinstance(traj, dict) and "confidence" in traj:
        return float(np.clip(traj["confidence"], 0.0, 1.0))
    impact_c = float(meta.get("impact_confidence", 0.5) or 0.5)
    pro = meta.get("pro_swing") or {}
    pro_c = 0.5
    if isinstance(pro, dict):
        release = pro.get("release") or {}
        if isinstance(release, dict) and "confidence" in release:
            pro_c = float(release.get("confidence", 0.5) or 0.5)
        elif "confidence" in pro:
            pro_c = float(pro.get("confidence", 0.5) or 0.5)
        manifold = pro.get("manifold") or {}
        if isinstance(manifold, dict) and "confidence" in manifold:
            pro_c = 0.5 * pro_c + 0.5 * float(manifold["confidence"])
    return float(np.clip(0.5 * impact_c + 0.5 * pro_c, 0.05, 0.95))
