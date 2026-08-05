"""Calibrated multi-head high-order kinematic inference from a single distal IMU.

Modern approach (WIT-KinNet / Lauer lineage, compact form)
---------------------------------------------------------
A Watch does not *directly measure* clubface or a second wrist bone. We learn a
phase-anchored **principal-component regression (PCR)** that maps distal
observables (ω, body-frame gyro axes, twist/swing channels, plane rates) onto
latent full-chain coordinates grouped into independent heads:

    * wrist  — FE / RU / forearm PS
    * club   — clubface open/closed + shaft lean
    * body   — X-factor + pelvis→torso→arm→club sequence angles

Each head carries its own residual calibration envelope (held-out quantiles).
Each emitted scalar additionally carries a status from **held-out scalar MAE**
against fixed commercial budgets (not training-tuned): if calib MAE exceeds the
degraded budget the scalar abstains even when the head residual is in-envelope.
Runtime head OOD status can only *worsen* scalar status. An optional personal
prior applies additive/linear corrections per scalar without mutating global
weights.

Training uses the independent multibody oracle with FE/face rates physically
coupled into the distal gyro. Labels always come from analytic truth — IMU
noise / violation corruptions never rewrite the label contract. All outputs
remain ``MetricKind.INFERRED`` (not launch-monitor measured).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np
from numpy.typing import ArrayLike, NDArray

from golfmate_algo.model.phase_normalize import (
    concatenate_phases,
    phase_normalize,
)
from golfmate_algo.quality.uncertainty import MetricKind, Validity, clip_confidence
from golfmate_algo.types import Handedness, SwingPhases

ArrayF = NDArray[np.float64]

_DEFAULT_WEIGHTS = Path(__file__).with_name("high_order_weights.json")

MODEL_VERSION = "high-order-pcr-v3"
PERSONAL_PRIOR_VERSION = "high-order-personal-v1"

TARGET_NAMES: tuple[str, ...] = (
    "wrist_fe_rad",
    "wrist_ru_rad",
    "forearm_ps_rad",
    "clubface_rad",
    "shaft_lean_rad",
    "x_factor_rad",
    "pelvis_angle_rad",
    "torso_angle_rad",
    "arm_angle_rad",
    "club_angle_rad",
)

OBS_NAMES: tuple[str, ...] = (
    "omega",
    "gx",
    "gy",
    "gz",
    "twist_rate",
    "plane_rate",
    "twist",
    "swing",
)

HEAD_SPECS: dict[str, dict[str, Any]] = {
    "wrist": {
        "targets": ("wrist_fe_rad", "wrist_ru_rad", "forearm_ps_rad"),
        "obs_channels": ("omega", "gx", "twist_rate", "twist", "swing"),
        "k_tgt": 4,
    },
    "club": {
        "targets": ("clubface_rad", "shaft_lean_rad"),
        "obs_channels": ("omega", "gz", "twist_rate", "plane_rate", "twist"),
        "k_tgt": 3,
    },
    "body": {
        "targets": (
            "x_factor_rad",
            "pelvis_angle_rad",
            "torso_angle_rad",
            "arm_angle_rad",
            "club_angle_rad",
        ),
        "obs_channels": ("omega", "gy", "plane_rate", "swing", "twist_rate"),
        "k_tgt": 5,
    },
}

HEAD_NAMES: tuple[str, ...] = tuple(HEAD_SPECS.keys())

# Scalar outputs that personal calibration may adjust (radians).
PERSONAL_SCALAR_KEYS: tuple[str, ...] = (
    "wrist_fe_address_rad",
    "wrist_fe_top_rad",
    "wrist_fe_impact_rad",
    "wrist_ru_impact_rad",
    "forearm_ps_impact_rad",
    "clubface_impact_rad",
    "shaft_lean_impact_rad",
    "x_factor_top_rad",
)

SCALAR_TO_HEAD: dict[str, str] = {
    "wrist_fe_address_rad": "wrist",
    "wrist_fe_top_rad": "wrist",
    "wrist_fe_impact_rad": "wrist",
    "wrist_ru_impact_rad": "wrist",
    "forearm_ps_impact_rad": "wrist",
    "clubface_impact_rad": "club",
    "shaft_lean_impact_rad": "club",
    "x_factor_top_rad": "body",
}

# ---------------------------------------------------------------------------
# Commercial held-out MAE budgets (radians). Fixed a priori — NOT tuned on
# the training set or shipped calib MAE. Conservative consumer Watch gates.
#
#   FE / RU / clubface / shaft lean : ok ≤ 8°, degraded ≤ 15°
#   forearm PS / X-factor           : ok ≤ 10°, degraded ≤ 20°
# ---------------------------------------------------------------------------
_DEG = float(np.pi / 180.0)
SCALAR_MAE_BUDGETS_RAD: dict[str, tuple[float, float]] = {
    "wrist_fe_address_rad": (8.0 * _DEG, 15.0 * _DEG),
    "wrist_fe_top_rad": (8.0 * _DEG, 15.0 * _DEG),
    "wrist_fe_impact_rad": (8.0 * _DEG, 15.0 * _DEG),
    "wrist_ru_impact_rad": (8.0 * _DEG, 15.0 * _DEG),
    "forearm_ps_impact_rad": (10.0 * _DEG, 20.0 * _DEG),
    "clubface_impact_rad": (8.0 * _DEG, 15.0 * _DEG),
    "shaft_lean_impact_rad": (8.0 * _DEG, 15.0 * _DEG),
    "x_factor_top_rad": (10.0 * _DEG, 20.0 * _DEG),
}

# Wire-facing metric keys inside wrist/club/body.metrics (commercial + dict).
SCALAR_METRIC_ALIASES: dict[str, str] = {
    "wrist_fe_address_rad": "fe_address",
    "wrist_fe_top_rad": "fe_top",
    "wrist_fe_impact_rad": "fe_impact",
    "wrist_ru_impact_rad": "ru_impact",
    "forearm_ps_impact_rad": "ps_impact",
    "clubface_impact_rad": "face_impact",
    "shaft_lean_impact_rad": "shaft_lean_impact",
    "x_factor_top_rad": "x_factor_top",
}
DERIVED_METRIC_KEYS: tuple[str, ...] = ("fe_delta_address_to_impact",)

_DEFAULT_GRID = {"address_to_top": 40, "top_to_impact": 28, "impact_to_finish": 28}

# Generator family ids used for training splits / leave-generator-out eval.
GENERATOR_FAMILIES: tuple[str, ...] = (
    "nominal",
    "casting",
    "left",
    "mount_club",
    "mount_perturb",
    "consumer",
    "violation_mild",
    "high_speed",
    "low_speed",
    "canonical",
)

_VALIDITY_RANK = {Validity.OK: 0, Validity.DEGRADED: 1, Validity.ABSTAIN: 2}


@dataclass
class HeadCalibration:
    """Held-out residual / error calibration for one target head."""

    resid_quantiles: dict[str, float]
    ok_resid_max: float
    degraded_resid_max: float
    scalar_mae: dict[str, float] = field(default_factory=dict)
    n_calib: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "resid_quantiles": {k: float(v) for k, v in self.resid_quantiles.items()},
            "ok_resid_max": float(self.ok_resid_max),
            "degraded_resid_max": float(self.degraded_resid_max),
            "scalar_mae": {k: float(v) for k, v in self.scalar_mae.items()},
            "n_calib": int(self.n_calib),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "HeadCalibration":
        return cls(
            resid_quantiles={str(k): float(v) for k, v in (d.get("resid_quantiles") or {}).items()},
            ok_resid_max=float(d.get("ok_resid_max", 0.55)),
            degraded_resid_max=float(d.get("degraded_resid_max", 1.2)),
            scalar_mae={str(k): float(v) for k, v in (d.get("scalar_mae") or {}).items()},
            n_calib=int(d.get("n_calib", 0)),
        )


@dataclass
class HeadPCR:
    """Per-head target PCR on shared observation scores."""

    name: str
    target_names: tuple[str, ...]
    obs_channel_idx: tuple[int, ...]
    W: ArrayF
    b: ArrayF
    tgt_mean: ArrayF
    tgt_scale: ArrayF
    tgt_components: ArrayF
    calibration: HeadCalibration

    def decode(self, scores: ArrayF) -> ArrayF:
        z = self.tgt_components.T @ scores
        return z * (self.tgt_scale + 1e-9) + self.tgt_mean

    def predict_from_obs_scores(self, s_obs: ArrayF) -> ArrayF:
        s_tgt = self.W @ s_obs + self.b
        return self.decode(s_tgt)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "target_names": list(self.target_names),
            "obs_channel_idx": list(self.obs_channel_idx),
            "W": _round_list(self.W),
            "b": _round_list(self.b),
            "tgt_mean": _round_list(self.tgt_mean),
            "tgt_scale": _round_list(self.tgt_scale),
            "tgt_components": _round_list(self.tgt_components),
            "calibration": self.calibration.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "HeadPCR":
        return cls(
            name=str(d["name"]),
            target_names=tuple(d["target_names"]),
            obs_channel_idx=tuple(int(i) for i in d.get("obs_channel_idx", [])),
            W=np.asarray(d["W"], dtype=np.float64),
            b=np.asarray(d["b"], dtype=np.float64),
            tgt_mean=np.asarray(d["tgt_mean"], dtype=np.float64),
            tgt_scale=np.asarray(d["tgt_scale"], dtype=np.float64),
            tgt_components=np.asarray(d["tgt_components"], dtype=np.float64),
            calibration=HeadCalibration.from_dict(d.get("calibration") or {}),
        )


@dataclass
class HeadStatus:
    validity: Validity
    confidence: float
    residual: float
    reasons: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "validity": self.validity.value,
            "confidence": float(self.confidence),
            "residual": float(self.residual) if np.isfinite(self.residual) else None,
            "reasons": list(self.reasons),
        }


@dataclass
class ScalarStatus:
    """Per-scalar commercial status from held-out MAE budget ∩ head OOD."""

    validity: Validity
    confidence: float
    calib_mae_rad: float
    residual: float
    reasons: list[str] = field(default_factory=list)
    ok_budget_rad: float = float("nan")
    degraded_budget_rad: float = float("nan")

    def as_dict(self) -> dict[str, Any]:
        return {
            "validity": self.validity.value,
            "confidence": float(self.confidence),
            "calib_mae_rad": (
                float(self.calib_mae_rad) if np.isfinite(self.calib_mae_rad) else None
            ),
            "residual": float(self.residual) if np.isfinite(self.residual) else None,
            "ok_budget_rad": (
                float(self.ok_budget_rad) if np.isfinite(self.ok_budget_rad) else None
            ),
            "degraded_budget_rad": (
                float(self.degraded_budget_rad)
                if np.isfinite(self.degraded_budget_rad)
                else None
            ),
            "reasons": list(self.reasons),
        }


@dataclass
class HighOrderEstimate:
    """Inferred high-order kinematics (radians unless noted)."""

    wrist_fe_address_rad: float
    wrist_fe_top_rad: float
    wrist_fe_impact_rad: float
    wrist_ru_impact_rad: float
    forearm_ps_impact_rad: float
    clubface_impact_rad: float
    shaft_lean_impact_rad: float
    x_factor_top_rad: float
    waveforms: dict[str, ArrayF] = field(default_factory=dict)
    pelvis_peak_to_impact_s: float = float("nan")
    torso_peak_to_impact_s: float = float("nan")
    arm_peak_to_impact_s: float = float("nan")
    club_peak_to_impact_s: float = float("nan")
    sequence_order_ok: bool = False
    residual: float = 1.0
    confidence: float = 0.3
    validity: Validity = Validity.DEGRADED
    kind: MetricKind = MetricKind.INFERRED
    model_version: str = MODEL_VERSION
    heads: dict[str, HeadStatus] = field(default_factory=dict)
    scalars: dict[str, ScalarStatus] = field(default_factory=dict)
    extras: dict[str, float] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)

    def head_status(self, name: str) -> HeadStatus | None:
        return self.heads.get(name)

    def scalar_status(self, key: str) -> ScalarStatus | None:
        return self.scalars.get(key)

    def as_dict(self) -> dict[str, Any]:
        def deg(x: float) -> float:
            return float(np.degrees(x)) if np.isfinite(x) else float("nan")

        wrist_st = self.heads.get("wrist")
        club_st = self.heads.get("club")
        body_st = self.heads.get("body")

        def _metrics_for_head(head: str) -> dict[str, Any]:
            out: dict[str, Any] = {}
            for sk, alias in SCALAR_METRIC_ALIASES.items():
                if SCALAR_TO_HEAD.get(sk) != head:
                    continue
                st = self.scalars.get(sk)
                if st is not None:
                    out[alias] = st.as_dict()
            if head == "wrist":
                # Derived FE delta: worst of address + impact scalar statuses.
                fe_a = self.scalars.get("wrist_fe_address_rad")
                fe_i = self.scalars.get("wrist_fe_impact_rad")
                if fe_a is not None and fe_i is not None:
                    out["fe_delta_address_to_impact"] = _combine_scalar_status(
                        fe_a, fe_i, reason="derived_fe_delta"
                    ).as_dict()
            return out

        def _pack_head(
            st: HeadStatus | None,
            payload: dict[str, Any],
            head: str,
        ) -> dict[str, Any]:
            out = dict(payload)
            if st is None:
                out.update(
                    {
                        "validity": self.validity.value,
                        "confidence": self.confidence,
                        "residual": self.residual,
                        "reasons": list(self.reasons) or ["legacy_global"],
                    }
                )
            else:
                out.update(st.as_dict())
            out["metrics"] = _metrics_for_head(head)
            return out

        return {
            "kind": self.kind.value,
            "validity": self.validity.value,
            "confidence": self.confidence,
            "residual": self.residual,
            "reasons": list(self.reasons),
            "model_version": self.model_version,
            "source": "high_order_pcr",
            "heads": {k: v.as_dict() for k, v in self.heads.items()},
            "scalars": {k: v.as_dict() for k, v in self.scalars.items()},
            "wrist": _pack_head(
                wrist_st,
                {
                    "fe_address_deg": deg(self.wrist_fe_address_rad),
                    "fe_top_deg": deg(self.wrist_fe_top_rad),
                    "fe_impact_deg": deg(self.wrist_fe_impact_rad),
                    "ru_impact_deg": deg(self.wrist_ru_impact_rad),
                    "ps_impact_deg": deg(self.forearm_ps_impact_rad),
                    "fe_delta_address_to_impact_deg": deg(
                        self.wrist_fe_impact_rad - self.wrist_fe_address_rad
                        if np.isfinite(self.wrist_fe_impact_rad)
                        and np.isfinite(self.wrist_fe_address_rad)
                        else float("nan")
                    ),
                },
                "wrist",
            ),
            "club": _pack_head(
                club_st,
                {
                    "face_impact_deg": deg(self.clubface_impact_rad),
                    "face_open_closed": (
                        "open"
                        if np.isfinite(self.clubface_impact_rad)
                        and self.clubface_impact_rad > np.deg2rad(2.0)
                        else (
                            "closed"
                            if np.isfinite(self.clubface_impact_rad)
                            and self.clubface_impact_rad < -np.deg2rad(2.0)
                            else "square"
                        )
                    ),
                    "shaft_lean_impact_deg": deg(self.shaft_lean_impact_rad),
                },
                "club",
            ),
            "body": _pack_head(
                body_st,
                {
                    "x_factor_top_deg": deg(self.x_factor_top_rad),
                    "pelvis_peak_to_impact_s": self.pelvis_peak_to_impact_s,
                    "torso_peak_to_impact_s": self.torso_peak_to_impact_s,
                    "arm_peak_to_impact_s": self.arm_peak_to_impact_s,
                    "club_peak_to_impact_s": self.club_peak_to_impact_s,
                    "sequence_order_ok": self.sequence_order_ok,
                },
                "body",
            ),
            "extras": self.extras,
        }


@dataclass
class PersonalHighOrderPrior:
    """Serializable additive/linear personal prior — does not mutate global weights.

    For each scalar key: ``corrected = scale[key] * raw + bias[key]`` (radians).
    """

    version: str = PERSONAL_PRIOR_VERSION
    scale: dict[str, float] = field(default_factory=dict)
    bias: dict[str, float] = field(default_factory=dict)
    n_fit: int = 0
    keys_fit: tuple[str, ...] = ()
    reasons: list[str] = field(default_factory=list)

    def apply_scalar(self, key: str, value: float) -> float:
        if not np.isfinite(value):
            return float("nan")
        a = float(self.scale.get(key, 1.0))
        b = float(self.bias.get(key, 0.0))
        return float(a * value + b)

    def apply(self, est: HighOrderEstimate) -> HighOrderEstimate:
        """Return a copy with non-abstained scalar outputs corrected."""
        out = replace(est)
        for key in PERSONAL_SCALAR_KEYS:
            st = est.scalars.get(key)
            if st is not None and st.validity == Validity.ABSTAIN:
                setattr(out, key, float("nan"))
                continue
            setattr(out, key, self.apply_scalar(key, float(getattr(est, key))))
        extras = dict(est.extras)
        extras["personal_prior_n_fit"] = float(self.n_fit)
        extras["personal_prior_applied"] = 1.0
        out.extras = extras
        out.scalars = dict(est.scalars)
        reasons = list(est.reasons)
        if "personal_prior_applied" not in reasons:
            reasons.append("personal_prior_applied")
        out.reasons = reasons
        return out

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "scale": {k: float(v) for k, v in self.scale.items()},
            "bias": {k: float(v) for k, v in self.bias.items()},
            "n_fit": int(self.n_fit),
            "keys_fit": list(self.keys_fit),
            "reasons": list(self.reasons),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "PersonalHighOrderPrior":
        return cls(
            version=str(d.get("version", PERSONAL_PRIOR_VERSION)),
            scale={str(k): float(v) for k, v in (d.get("scale") or {}).items()},
            bias={str(k): float(v) for k, v in (d.get("bias") or {}).items()},
            n_fit=int(d.get("n_fit", 0)),
            keys_fit=tuple(str(k) for k in (d.get("keys_fit") or ())),
            reasons=list(d.get("reasons") or []),
        )


@dataclass
class HighOrderPCR:
    """Shared obs PCA + per-head target PCR with held-out residual calibration."""

    obs_mean: ArrayF
    obs_scale: ArrayF
    obs_components: ArrayF  # (K, D_obs)
    heads: dict[str, HeadPCR]
    obs_names: tuple[str, ...]
    target_names: tuple[str, ...]
    grid_sizes: dict[str, int]
    version: str
    n_train: int
    n_calib: int = 0
    split_seed: int = 0
    train_families: tuple[str, ...] = ()
    event_W: ArrayF | None = None  # (2, K_obs+3) impact FE / face
    event_b: ArrayF | None = None
    # Legacy monolithic fields (v2 load path)
    W: ArrayF | None = None
    b: ArrayF | None = None
    tgt_mean: ArrayF | None = None
    tgt_scale: ArrayF | None = None
    tgt_components: ArrayF | None = None

    def encode_obs(self, x: ArrayF) -> ArrayF:
        z = (x - self.obs_mean) / (self.obs_scale + 1e-9)
        return self.obs_components @ z

    def obs_residual(self, x: ArrayF) -> float:
        z = (x - self.obs_mean) / (self.obs_scale + 1e-9)
        s = self.obs_components @ z
        recon = self.obs_components.T @ s
        return float(np.linalg.norm(z - recon) / np.sqrt(max(1, z.size)))

    def head_residual(self, x: ArrayF, head: HeadPCR) -> float:
        """Reconstruction residual restricted to the head's observation channels."""
        z = (x - self.obs_mean) / (self.obs_scale + 1e-9)
        s = self.obs_components @ z
        recon = self.obs_components.T @ s
        err = z - recon
        n_ch = len(self.obs_names)
        T = err.size // n_ch
        if T * n_ch != err.size or not head.obs_channel_idx:
            return self.obs_residual(x)
        mat = err.reshape(T, n_ch)
        cols = list(head.obs_channel_idx)
        sub = mat[:, cols].reshape(-1)
        return float(np.linalg.norm(sub) / np.sqrt(max(1, sub.size)))

    def predict_targets(self, x_obs: ArrayF) -> tuple[dict[str, ArrayF], dict[str, float], float]:
        s_obs = self.encode_obs(x_obs)
        global_resid = self.obs_residual(x_obs)
        waves: dict[str, ArrayF] = {}
        head_resids: dict[str, float] = {}
        grid = self.grid_sizes
        g0 = grid["address_to_top"]
        g1 = grid["top_to_impact"]
        g2 = grid["impact_to_finish"]
        T = g0 + g1 + g2

        if self.heads:
            for name, head in self.heads.items():
                y_flat = head.predict_from_obs_scores(s_obs)
                n_tgt = len(head.target_names)
                mat = y_flat.reshape(T, n_tgt)
                for c, tname in enumerate(head.target_names):
                    waves[tname] = mat[:, c].copy()
                head_resids[name] = self.head_residual(x_obs, head)
        elif (
            self.W is not None
            and self.b is not None
            and self.tgt_mean is not None
            and self.tgt_scale is not None
            and self.tgt_components is not None
        ):
            # Legacy monolithic decode
            s_tgt = self.W @ s_obs + self.b
            z = self.tgt_components.T @ s_tgt
            y = z * (self.tgt_scale + 1e-9) + self.tgt_mean
            waves = _split_target_waveforms(y, self.target_names, grid)
            for hname in HEAD_NAMES:
                head_resids[hname] = global_resid
        return waves, head_resids, global_resid

    def predict(self, x_obs: ArrayF) -> tuple[ArrayF, float]:
        """Backward-compatible flat target prediction + global residual."""
        waves, _, resid = self.predict_targets(x_obs)
        grid = self.grid_sizes
        g0 = grid["address_to_top"]
        g1 = grid["top_to_impact"]
        g2 = grid["impact_to_finish"]
        T = g0 + g1 + g2
        cols = []
        for name in self.target_names:
            if name not in waves:
                cols.append(np.zeros(T, dtype=np.float64))
            else:
                cols.append(waves[name])
        y = np.column_stack(cols).reshape(-1)
        return y, resid

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "version": self.version,
            "n_train": self.n_train,
            "n_calib": self.n_calib,
            "split_seed": self.split_seed,
            "train_families": list(self.train_families),
            "obs_names": list(self.obs_names),
            "target_names": list(self.target_names),
            "grid_sizes": self.grid_sizes,
            "obs_mean": _round_list(self.obs_mean),
            "obs_scale": _round_list(self.obs_scale),
            "obs_components": _round_list(self.obs_components),
            "heads": {k: v.to_dict() for k, v in self.heads.items()},
        }
        if self.event_W is not None and self.event_b is not None:
            d["event_W"] = _round_list(self.event_W)
            d["event_b"] = _round_list(self.event_b)
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "HighOrderPCR":
        heads_raw = d.get("heads")
        heads: dict[str, HeadPCR] = {}
        if isinstance(heads_raw, dict) and heads_raw:
            heads = {str(k): HeadPCR.from_dict(v) for k, v in heads_raw.items()}
        return cls(
            obs_mean=np.asarray(d["obs_mean"], dtype=np.float64),
            obs_scale=np.asarray(d["obs_scale"], dtype=np.float64),
            obs_components=np.asarray(d["obs_components"], dtype=np.float64),
            heads=heads,
            obs_names=tuple(d["obs_names"]),
            target_names=tuple(d["target_names"]),
            grid_sizes={k: int(v) for k, v in d["grid_sizes"].items()},
            version=str(d.get("version", MODEL_VERSION)),
            n_train=int(d.get("n_train", 0)),
            n_calib=int(d.get("n_calib", 0)),
            split_seed=int(d.get("split_seed", 0)),
            train_families=tuple(d.get("train_families") or ()),
            event_W=(
                np.asarray(d["event_W"], dtype=np.float64) if "event_W" in d else None
            ),
            event_b=(
                np.asarray(d["event_b"], dtype=np.float64) if "event_b" in d else None
            ),
            W=np.asarray(d["W"], dtype=np.float64) if "W" in d else None,
            b=np.asarray(d["b"], dtype=np.float64) if "b" in d else None,
            tgt_mean=np.asarray(d["tgt_mean"], dtype=np.float64) if "tgt_mean" in d else None,
            tgt_scale=np.asarray(d["tgt_scale"], dtype=np.float64) if "tgt_scale" in d else None,
            tgt_components=(
                np.asarray(d["tgt_components"], dtype=np.float64)
                if "tgt_components" in d
                else None
            ),
        )


def _round_list(a: ArrayLike, ndigits: int = 6) -> list[Any]:
    arr = np.asarray(a, dtype=np.float64)
    return np.round(arr, ndigits).tolist()


def _pca_fit(X: ArrayF, k: int) -> tuple[ArrayF, ArrayF, ArrayF]:
    mean = np.median(X, axis=0)
    scale = np.median(np.abs(X - mean), axis=0) * 1.4826
    scale = np.maximum(scale, 1e-6)
    Z = (X - mean) / scale
    _, s, vt = np.linalg.svd(Z, full_matrices=False)
    kk = int(min(k, vt.shape[0], max(1, X.shape[0] - 1)))
    return mean, scale, vt[:kk]


def _obs_matrix(
    gyro: ArrayF, quats: ArrayF, dt: float, address_idx: int, channel_kind: str
) -> ArrayF:
    from golfmate_algo.biomechanics.wrist_channels import estimate_segment_channels

    ch = estimate_segment_channels(
        quats, gyro, dt, address_idx=address_idx, channel_kind=channel_kind
    )
    omega = np.linalg.norm(gyro, axis=1)
    return np.column_stack(
        [
            omega,
            gyro[:, 0],
            gyro[:, 1],
            gyro[:, 2],
            ch.twist_rate_rad_s,
            ch.omega_plane_rad_s,
            ch.twist_rad,
            ch.swing_rad,
        ]
    )


def _event_features(x_flat: ArrayF, s_obs: ArrayF, grid: dict[str, int], n_ch: int) -> ArrayF:
    """Compact features for impact FE/face scalar refinement."""
    g0, g1, g2 = grid["address_to_top"], grid["top_to_impact"], grid["impact_to_finish"]
    T = g0 + g1 + g2
    mat = x_flat.reshape(T, n_ch)
    gx = mat[:, 1]
    gz = mat[:, 3]
    twist = mat[:, 6]
    trap = np.trapezoid if hasattr(np, "trapezoid") else np.trapz
    d_gx = float(trap(gx[g0 : g0 + g1]))
    d_gz = float(trap(gz[g0 : g0 + g1]))
    tw_imp = float(twist[g0 + g1 - 1] - twist[0])
    return np.concatenate([s_obs, np.array([d_gx, d_gz, tw_imp], dtype=np.float64)])


def _channel_indices(obs_names: Sequence[str], wanted: Sequence[str]) -> tuple[int, ...]:
    name_to_i = {n: i for i, n in enumerate(obs_names)}
    return tuple(name_to_i[n] for n in wanted if n in name_to_i)


def _small_mount_quat(seed: int) -> tuple[float, float, float, float]:
    """Deterministic small extrinsic mount perturbation (~a few degrees)."""
    rng = np.random.default_rng(10_000 + int(seed))
    axis = rng.normal(size=3)
    axis = axis / (np.linalg.norm(axis) + 1e-12)
    ang = float(np.deg2rad(rng.uniform(3.0, 12.0)))
    half = 0.5 * ang
    s = float(np.sin(half))
    q = np.array([np.cos(half), axis[0] * s, axis[1] * s, axis[2] * s], dtype=np.float64)
    q = q / (np.linalg.norm(q) + 1e-12)
    return (float(q[0]), float(q[1]), float(q[2]), float(q[3]))


def _scale_rates(
    rates: tuple[float, float, float, float], scale: float
) -> tuple[float, float, float, float]:
    return tuple(float(r * scale) for r in rates)  # type: ignore[return-value]


@dataclass(frozen=True)
class TeacherSampleSpec:
    """Deterministic teacher sample descriptor (does not rewrite labels)."""

    index: int
    family: str
    seed: int


def iter_teacher_specs(
    n_swings: int,
    seed: int = 0,
    families: Sequence[str] | None = None,
) -> list[TeacherSampleSpec]:
    """Deterministic round-robin over generator families."""
    fams = tuple(families) if families is not None else GENERATOR_FAMILIES
    if not fams:
        raise ValueError("families must be non-empty")
    out: list[TeacherSampleSpec] = []
    for i in range(int(n_swings)):
        fam = fams[i % len(fams)]
        out.append(TeacherSampleSpec(index=i, family=str(fam), seed=int(seed) + i * 17))
    return out


def train_calib_split(
    n: int, *, seed: int, calib_frac: float = 0.25
) -> tuple[np.ndarray, np.ndarray]:
    """Deterministic held-out calibration indices (sorted)."""
    n = int(n)
    if n < 4:
        idx = np.arange(n, dtype=np.int64)
        return idx, idx[:0]
    rng = np.random.default_rng(int(seed) + 901)
    perm = rng.permutation(n)
    n_calib = int(max(1, round(n * float(calib_frac))))
    n_calib = min(n_calib, n - 2)
    calib = np.sort(perm[:n_calib].astype(np.int64))
    train_mask = np.ones(n, dtype=bool)
    train_mask[calib] = False
    train = np.sort(np.arange(n, dtype=np.int64)[train_mask])
    return train, calib


def _build_swing_for_spec(spec: TeacherSampleSpec, *, fs_hz: float):
    from golfmate_algo.synth.multibody import SwingConfig, build_swing, casting_swing

    rng = np.random.default_rng(spec.seed)
    family = spec.family
    plane = float(rng.uniform(45.0, 62.0))
    bs = float(rng.uniform(0.65, 0.95))
    ds = float(rng.uniform(0.20, 0.32))
    sway = float(rng.uniform(0.0, 0.04))
    fe_top = float(rng.uniform(-28.0, -8.0))
    fe_imp = float(rng.uniform(-5.0, 28.0))
    face_imp = float(rng.uniform(-14.0, 14.0))
    face_top = float(rng.uniform(0.0, 15.0))
    mount = 2
    handed = Handedness.RIGHT
    ext = (1.0, 0.0, 0.0, 0.0)
    rate_scale = 1.0

    if family == "casting":
        mount = 3
    elif family == "left":
        handed = Handedness.LEFT
    elif family == "mount_club":
        mount = 3
    elif family == "mount_perturb":
        ext = _small_mount_quat(spec.seed)
        mount = 2 if spec.index % 2 == 0 else 3
    elif family == "high_speed":
        ds = float(rng.uniform(0.16, 0.22))
        rate_scale = float(rng.uniform(1.15, 1.35))
    elif family == "low_speed":
        ds = float(rng.uniform(0.30, 0.40))
        rate_scale = float(rng.uniform(0.65, 0.85))
    elif family == "canonical":
        mount = 2
        handed = Handedness.RIGHT
        ext = (1.0, 0.0, 0.0, 0.0)

    base = SwingConfig()
    cfg = SwingConfig(
        fs_hz=float(fs_hz),
        plane_tilt_deg=plane,
        backswing_s=bs,
        downswing_s=ds,
        center_sway_amp_m=sway,
        mount_segment=mount,
        mount_extrinsic_quat=ext,
        handedness=handed,
        wrist_fe_top_deg=fe_top,
        wrist_fe_impact_deg=fe_imp,
        clubface_open_impact_deg=face_imp,
        clubface_open_top_deg=face_top,
        backswing_peak_rate_deg_s=_scale_rates(base.backswing_peak_rate_deg_s, rate_scale),
        downswing_peak_rate_deg_s=_scale_rates(base.downswing_peak_rate_deg_s, rate_scale),
    )
    if family == "casting":
        truth = casting_swing(cfg)
    else:
        truth = build_swing(cfg)
    return truth, family


def _corrupt_packet_imu(truth, family: str, seed: int):
    """Optionally corrupt measured IMU; labels stay on analytic truth."""
    from golfmate_algo.synth.imu_model import ImuErrorParams, apply_imu_errors
    from golfmate_algo.synth.violations import apply_violations, mild_violation

    pkt = truth.to_imu_packet(couple_high_order=True)
    gyro = pkt.gyro.copy()
    accel = pkt.accel.copy()
    t = pkt.t

    if family == "consumer":
        params = ImuErrorParams.consumer_grade(seed=seed)
        # Milder dropout/jitter off for phase stability in teacher set.
        params.dropout_prob = 0.0
        params.jitter_std_s = 0.0
        t2, gyro, accel, _ = apply_imu_errors(t, gyro, accel, params)
        t = t2
    elif family == "violation_mild":
        g2, a2, _ = apply_violations(
            t,
            gyro,
            accel,
            quats_true=truth.sensor_quat,
            positions_true=truth.sensor_pos,
            impact_idx=truth.impact_idx,
            spec=mild_violation(seed=seed),
        )
        gyro, accel = g2, a2

    # Rebuild packet with possibly corrupted streams (frame unchanged).
    from golfmate_algo.types import ImuPacket

    return ImuPacket(frame=pkt.frame, t=t, gyro=gyro, accel=accel)


def _extract_obs_tgt(
    truth,
    pkt,
    *,
    grid: dict[str, int],
    channel_kind: str = "unknown_segment",
) -> tuple[ArrayF, ArrayF, float, float, dict[str, float]]:
    from golfmate_algo.ahrs import init as ahrs_init
    from golfmate_algo.ahrs.suite import GatedAdaptive
    from golfmate_algo.devices.normalize import normalize_packet

    # Normalize so left-handed device frames map to canonical observables.
    pkt_n, _ = normalize_packet(pkt)
    phases = truth.phases()
    dt = float(np.median(np.diff(pkt_n.t))) if pkt_n.t.size > 1 else 1.0 / 200.0
    q0, _, _ = ahrs_init.estimate_address_orientation(
        pkt_n.gyro, pkt_n.accel, 1.0 / max(dt, 1e-4)
    )
    quats, _ = GatedAdaptive(use_signed_log_tilt=True).run(
        pkt_n.gyro, pkt_n.accel, dt, q0=q0
    )
    ho = truth.high_order_truth()
    obs_mat = _obs_matrix(
        pkt_n.gyro, quats, dt, phases.address_idx, channel_kind=channel_kind
    )
    tgt_mat = np.column_stack(
        [np.asarray(ho[name], dtype=np.float64) for name in TARGET_NAMES]
    )
    obs_n = phase_normalize(
        truth.t if truth.t.shape[0] == obs_mat.shape[0] else pkt_n.t,
        obs_mat,
        phases,
        channel_names=OBS_NAMES,
        grid_sizes=grid,
    )
    # Target phase-normalize on truth timeline (labels never follow IMU corruption).
    tgt_n = phase_normalize(
        truth.t,
        tgt_mat,
        phases,
        channel_names=TARGET_NAMES,
        grid_sizes=grid,
    )
    obs_flat = concatenate_phases(obs_n).reshape(-1)
    tgt_flat = concatenate_phases(tgt_n).reshape(-1)
    scalars = {
        "wrist_fe_address_rad": float(ho["fe_address_rad"]),
        "wrist_fe_impact_rad": float(ho["fe_impact_rad"]),
        "clubface_impact_rad": float(ho["clubface_impact_rad"]),
        "shaft_lean_impact_rad": float(ho["shaft_lean_impact_rad"]),
        "x_factor_top_rad": float(np.asarray(ho["x_factor_rad"])[truth.top_idx]),
        "wrist_ru_impact_rad": float(np.asarray(ho["wrist_ru_rad"])[truth.impact_idx]),
        "forearm_ps_impact_rad": float(np.asarray(ho["forearm_ps_rad"])[truth.impact_idx]),
        "wrist_fe_top_rad": float(np.asarray(ho["wrist_fe_rad"])[truth.top_idx]),
    }
    return obs_flat, tgt_flat, float(ho["fe_impact_rad"]), float(ho["clubface_impact_rad"]), scalars


def generate_teacher_dataset(
    n_swings: int = 320,
    seed: int = 0,
    *,
    fs_hz: float = 200.0,
    families: Sequence[str] | None = None,
    grid_sizes: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Build deterministic teacher features/labels across generator families."""
    specs = iter_teacher_specs(n_swings, seed=seed, families=families)
    grid = dict(grid_sizes or _DEFAULT_GRID)
    obs_w: list[ArrayF] = []
    tgt_w: list[ArrayF] = []
    event_fe: list[float] = []
    event_face: list[float] = []
    scalars: list[dict[str, float]] = []
    fam_ids: list[str] = []
    for spec in specs:
        truth, family = _build_swing_for_spec(spec, fs_hz=fs_hz)
        pkt = _corrupt_packet_imu(truth, family, seed=spec.seed)
        o, y, fe_i, face_i, sc = _extract_obs_tgt(truth, pkt, grid=grid)
        obs_w.append(o)
        tgt_w.append(y)
        event_fe.append(fe_i)
        event_face.append(face_i)
        scalars.append(sc)
        fam_ids.append(family)
    return {
        "obs": obs_w,
        "tgt": tgt_w,
        "event_fe": np.asarray(event_fe, dtype=np.float64),
        "event_face": np.asarray(event_face, dtype=np.float64),
        "scalars": scalars,
        "families": fam_ids,
        "specs": specs,
        "grid_sizes": grid,
        "seed": int(seed),
    }


def _fit_head(
    name: str,
    Sx: ArrayF,
    Y_all: ArrayF,
    target_names_all: Sequence[str],
    head_targets: Sequence[str],
    obs_channel_idx: Sequence[int],
    k_tgt: int,
) -> tuple[ArrayF, ArrayF, ArrayF, ArrayF, ArrayF]:
    idxs = [list(target_names_all).index(t) for t in head_targets]
    # Y_all is (N, T * n_all_targets) — extract head columns after reshape
    n = Y_all.shape[0]
    n_all = len(target_names_all)
    T = Y_all.shape[1] // n_all
    mats = Y_all.reshape(n, T, n_all)
    Yh = mats[:, :, idxs].reshape(n, -1)
    tm, ts, tc = _pca_fit(Yh, k_tgt)
    Zy = (Yh - tm) / ts
    Sy = Zy @ tc.T
    kx = Sx.shape[1]
    A = Sx.T @ Sx + 1e-3 * np.eye(kx)
    W = np.linalg.solve(A, Sx.T @ Sy).T
    b = Sy.mean(axis=0) - W @ Sx.mean(axis=0)
    return W, b, tm, ts, tc


def _scalar_from_waves(
    waves: dict[str, ArrayF], grid: dict[str, int]
) -> dict[str, float]:
    fe = waves.get("wrist_fe_rad")
    ru = waves.get("wrist_ru_rad")
    ps = waves.get("forearm_ps_rad")
    face = waves.get("clubface_rad")
    lean = waves.get("shaft_lean_rad")
    xf = waves.get("x_factor_rad")
    out = {k: float("nan") for k in PERSONAL_SCALAR_KEYS}
    if fe is not None:
        out["wrist_fe_address_rad"] = _sample_at_phase_frac(fe, grid, "address", 0.0)
        out["wrist_fe_top_rad"] = _sample_at_phase_frac(fe, grid, "top", 0.0)
        out["wrist_fe_impact_rad"] = _sample_at_phase_frac(fe, grid, "impact", 0.0)
    if ru is not None:
        out["wrist_ru_impact_rad"] = _sample_at_phase_frac(ru, grid, "impact", 0.0)
    if ps is not None:
        out["forearm_ps_impact_rad"] = _sample_at_phase_frac(ps, grid, "impact", 0.0)
    if face is not None:
        out["clubface_impact_rad"] = _sample_at_phase_frac(face, grid, "impact", 0.0)
    if lean is not None:
        out["shaft_lean_impact_rad"] = _sample_at_phase_frac(lean, grid, "impact", 0.0)
    if xf is not None:
        out["x_factor_top_rad"] = _sample_at_phase_frac(xf, grid, "top", 0.0)
    return out


def _calibrate_head(
    residuals: ArrayF,
    pred_scalars: list[dict[str, float]],
    true_scalars: list[dict[str, float]],
    head_name: str,
) -> HeadCalibration:
    res = np.asarray(residuals, dtype=np.float64)
    res = res[np.isfinite(res)]
    if res.size == 0:
        return HeadCalibration(
            resid_quantiles={"p50": 0.5, "p90": 1.0, "p95": 1.2, "p99": 1.5},
            ok_resid_max=0.55,
            degraded_resid_max=1.2,
            n_calib=0,
        )
    qs = {
        "p50": float(np.quantile(res, 0.50)),
        "p90": float(np.quantile(res, 0.90)),
        "p95": float(np.quantile(res, 0.95)),
        "p99": float(np.quantile(res, 0.99)),
    }
    # Envelope from held-out residual distribution only (not training residuals).
    ok_max = float(max(qs["p90"], qs["p50"] + 1e-6))
    deg_max = float(max(qs["p99"], ok_max * 1.05))
    mae: dict[str, float] = {}
    for key, h in SCALAR_TO_HEAD.items():
        if h != head_name:
            continue
        errs = []
        for p, t in zip(pred_scalars, true_scalars):
            pv, tv = float(p.get(key, float("nan"))), float(t.get(key, float("nan")))
            if np.isfinite(pv) and np.isfinite(tv):
                errs.append(abs(pv - tv))
        if errs:
            mae[key] = float(np.mean(errs))
    return HeadCalibration(
        resid_quantiles=qs,
        ok_resid_max=ok_max,
        degraded_resid_max=deg_max,
        scalar_mae=mae,
        n_calib=int(res.size),
    )


def fit_high_order_pcr(
    obs_waves: list[ArrayF],
    tgt_waves: list[ArrayF],
    *,
    event_fe: ArrayF | None = None,
    event_face: ArrayF | None = None,
    scalars: list[dict[str, float]] | None = None,
    obs_names: tuple[str, ...] = OBS_NAMES,
    target_names: tuple[str, ...] = TARGET_NAMES,
    grid_sizes: dict[str, int] | None = None,
    k_obs: int = 10,
    version: str = MODEL_VERSION,
    calib_frac: float = 0.25,
    split_seed: int = 0,
    train_families: Sequence[str] | None = None,
) -> HighOrderPCR:
    """Fit shared obs PCA + per-head PCR; calibrate residual envelopes on holdout."""
    X = np.stack([np.asarray(w, dtype=np.float64).reshape(-1) for w in obs_waves])
    Y = np.stack([np.asarray(w, dtype=np.float64).reshape(-1) for w in tgt_waves])
    n = X.shape[0]
    train_idx, calib_idx = train_calib_split(n, seed=split_seed, calib_frac=calib_frac)
    if train_idx.size < 2:
        train_idx = np.arange(n, dtype=np.int64)
        calib_idx = train_idx[:0]

    Xtr, Ytr = X[train_idx], Y[train_idx]
    om, os, oc = _pca_fit(Xtr, k_obs)
    Zx = (Xtr - om) / os
    Sx = Zx @ oc.T

    grid = dict(grid_sizes or _DEFAULT_GRID)
    heads: dict[str, HeadPCR] = {}
    for hname, spec in HEAD_SPECS.items():
        W, b, tm, ts, tc = _fit_head(
            hname,
            Sx,
            Ytr,
            target_names,
            spec["targets"],
            _channel_indices(obs_names, spec["obs_channels"]),
            int(spec["k_tgt"]),
        )
        heads[hname] = HeadPCR(
            name=hname,
            target_names=tuple(spec["targets"]),
            obs_channel_idx=_channel_indices(obs_names, spec["obs_channels"]),
            W=W,
            b=b,
            tgt_mean=tm,
            tgt_scale=ts,
            tgt_components=tc,
            calibration=HeadCalibration(
                resid_quantiles={},
                ok_resid_max=0.55,
                degraded_resid_max=1.2,
            ),
        )

    event_W = None
    event_b = None
    if event_fe is not None and event_face is not None and train_idx.size > 0:
        feats = []
        for i in train_idx:
            s = oc @ ((X[i] - om) / os)
            feats.append(_event_features(X[i], s, grid, len(obs_names)))
        F = np.stack(feats)
        Yev = np.column_stack([event_fe[train_idx], event_face[train_idx]])
        d = F.shape[1]
        We = np.linalg.solve(F.T @ F + 1e-2 * np.eye(d), F.T @ Yev).T
        be = Yev.mean(axis=0) - We @ F.mean(axis=0)
        event_W, event_b = We, be

    model = HighOrderPCR(
        obs_mean=om,
        obs_scale=os,
        obs_components=oc,
        heads=heads,
        obs_names=obs_names,
        target_names=target_names,
        grid_sizes=grid,
        version=version,
        n_train=int(train_idx.size),
        n_calib=int(calib_idx.size),
        split_seed=int(split_seed),
        train_families=tuple(train_families or ()),
        event_W=event_W,
        event_b=event_b,
    )

    # Held-out calibration: residual envelopes + scalar MAE (never on train set).
    if calib_idx.size > 0:
        pred_sc: list[dict[str, float]] = []
        true_sc: list[dict[str, float]] = []
        head_res_lists: dict[str, list[float]] = {h: [] for h in heads}
        for j in calib_idx:
            waves, hres, _ = model.predict_targets(X[j])
            # Optional event refinement for calib MAE fairness with runtime.
            if model.event_W is not None and model.event_b is not None:
                s_obs = model.encode_obs(X[j])
                feat = _event_features(X[j], s_obs, grid, len(obs_names))
                if feat.size == model.event_W.shape[1]:
                    ev = model.event_W @ feat + model.event_b
                    if "wrist_fe_rad" in waves:
                        waves["wrist_fe_rad"] = waves["wrist_fe_rad"].copy()
                        g0, g1 = grid["address_to_top"], grid["top_to_impact"]
                        waves["wrist_fe_rad"][g0 + g1 - 1] = float(
                            0.35 * waves["wrist_fe_rad"][g0 + g1 - 1] + 0.65 * ev[0]
                        )
                    if "clubface_rad" in waves:
                        waves["clubface_rad"] = waves["clubface_rad"].copy()
                        g0, g1 = grid["address_to_top"], grid["top_to_impact"]
                        waves["clubface_rad"][g0 + g1 - 1] = float(
                            0.35 * waves["clubface_rad"][g0 + g1 - 1] + 0.65 * ev[1]
                        )
            ps = _scalar_from_waves(waves, grid)
            if scalars is not None:
                ts_ = dict(scalars[int(j)])
            else:
                ts_ = dict(ps)  # unavailable — MAE skipped
            pred_sc.append(ps)
            true_sc.append(ts_)
            for h, r in hres.items():
                head_res_lists[h].append(float(r))
        for hname, head in heads.items():
            head.calibration = _calibrate_head(
                np.asarray(head_res_lists[hname], dtype=np.float64),
                pred_sc,
                true_sc,
                hname,
            )
    return model


def build_default_high_order_model(
    n_swings: int = 320,
    seed: int = 0,
    path: Path | None = None,
    *,
    calib_frac: float = 0.25,
    fs_hz: float = 200.0,
    families: Sequence[str] | None = None,
) -> HighOrderPCR:
    """Fit calibrated multi-head PCR from multibody GT and persist JSON weights."""
    data = generate_teacher_dataset(
        n_swings=n_swings,
        seed=seed,
        fs_hz=fs_hz,
        families=families,
        grid_sizes=dict(_DEFAULT_GRID),
    )
    model = fit_high_order_pcr(
        data["obs"],
        data["tgt"],
        event_fe=data["event_fe"],
        event_face=data["event_face"],
        scalars=data["scalars"],
        grid_sizes=data["grid_sizes"],
        k_obs=10,
        version=MODEL_VERSION,
        calib_frac=calib_frac,
        split_seed=seed,
        train_families=sorted(set(data["families"])),
    )
    out = path or _DEFAULT_WEIGHTS
    out.write_text(json.dumps(model.to_dict(), separators=(",", ":")), encoding="utf-8")
    return model


def load_high_order_model(path: Path | None = None) -> HighOrderPCR | None:
    p = path or _DEFAULT_WEIGHTS
    if not p.exists():
        return None
    return HighOrderPCR.from_dict(json.loads(p.read_text(encoding="utf-8")))


def fit_personal_high_order_prior(
    predictions: Sequence[dict[str, float] | HighOrderEstimate],
    labels: Sequence[dict[str, float]],
    *,
    min_samples: int = 3,
    keys: Sequence[str] | None = None,
) -> PersonalHighOrderPrior:
    """Fit per-target scale/bias from a small labeled set (does not touch global PCR)."""
    keys_use = tuple(keys) if keys is not None else PERSONAL_SCALAR_KEYS
    preds: list[dict[str, float]] = []
    for p in predictions:
        if isinstance(p, HighOrderEstimate):
            preds.append({k: float(getattr(p, k)) for k in PERSONAL_SCALAR_KEYS})
        else:
            preds.append({str(k): float(v) for k, v in p.items()})
    if len(preds) != len(labels):
        raise ValueError("predictions and labels must have equal length")

    scale: dict[str, float] = {}
    bias: dict[str, float] = {}
    keys_fit: list[str] = []
    reasons: list[str] = ["personal_linear_prior"]
    for key in keys_use:
        xs: list[float] = []
        ys: list[float] = []
        for p, y in zip(preds, labels):
            xv = float(p.get(key, float("nan")))
            yv = float(y.get(key, float("nan")))
            if np.isfinite(xv) and np.isfinite(yv):
                xs.append(xv)
                ys.append(yv)
        if len(xs) < int(min_samples):
            continue
        x = np.asarray(xs, dtype=np.float64)
        y = np.asarray(ys, dtype=np.float64)
        # Bias-only if variance is tiny; else linear least squares y ≈ a x + b.
        if float(np.std(x)) < 1e-6:
            a, b = 1.0, float(np.mean(y - x))
        else:
            A = np.column_stack([x, np.ones(len(x))])
            coef, _, _, _ = np.linalg.lstsq(A, y, rcond=None)
            a, b = float(coef[0]), float(coef[1])
            # Keep mild regularization toward identity.
            a = float(0.85 * a + 0.15 * 1.0)
            b = float(0.85 * b)
        scale[key] = a
        bias[key] = b
        keys_fit.append(key)
    if not keys_fit:
        reasons.append("insufficient_labeled_samples")
    return PersonalHighOrderPrior(
        version=PERSONAL_PRIOR_VERSION,
        scale=scale,
        bias=bias,
        n_fit=len(preds),
        keys_fit=tuple(keys_fit),
        reasons=reasons,
    )


def _split_target_waveforms(
    flat: ArrayF, names: tuple[str, ...], grid: dict[str, int]
) -> dict[str, ArrayF]:
    n_ch = len(names)
    g0, g1, g2 = grid["address_to_top"], grid["top_to_impact"], grid["impact_to_finish"]
    T = g0 + g1 + g2
    mat = flat.reshape(T, n_ch)
    return {names[c]: mat[:, c].copy() for c in range(n_ch)}


def _sample_at_phase_frac(wave: ArrayF, grid: dict[str, int], which: str, frac: float) -> float:
    g0, g1, g2 = grid["address_to_top"], grid["top_to_impact"], grid["impact_to_finish"]
    if which == "address":
        return float(wave[0])
    if which == "top":
        return float(wave[g0 - 1])
    if which == "impact":
        return float(wave[g0 + g1 - 1])
    if which == "mid_down":
        idx = g0 + int(np.clip(frac, 0, 1) * (g1 - 1))
        return float(wave[idx])
    return float(wave[-1])


def _status_from_resid(resid: float, calib: HeadCalibration) -> HeadStatus:
    reasons: list[str] = ["high_order_pcr_head"]
    if not np.isfinite(resid):
        return HeadStatus(
            Validity.ABSTAIN, 0.05, float("nan"), reasons + ["residual_nonfinite"]
        )
    if resid > calib.degraded_resid_max:
        conf = clip_confidence(0.15 / (1.0 + resid))
        return HeadStatus(
            Validity.ABSTAIN,
            conf,
            resid,
            reasons + ["outside_calib_envelope"],
        )
    if resid > calib.ok_resid_max:
        # Map residual between ok and degraded max into degraded band.
        span = max(1e-6, calib.degraded_resid_max - calib.ok_resid_max)
        t = (resid - calib.ok_resid_max) / span
        conf = clip_confidence(0.55 * (1.0 - 0.5 * t) / (1.0 + resid))
        return HeadStatus(
            Validity.DEGRADED,
            conf,
            resid,
            reasons + ["near_calib_edge"],
        )
    conf = clip_confidence(1.0 / (1.0 + 1.5 * resid))
    return HeadStatus(Validity.OK, conf, resid, reasons + ["inside_calib_envelope"])


def _scalar_status_from_mae(
    key: str,
    calib_mae: float,
    head_st: HeadStatus,
) -> ScalarStatus:
    """Status from fixed MAE budget, then worsen by runtime head OOD."""
    budgets = SCALAR_MAE_BUDGETS_RAD.get(key)
    reasons: list[str] = ["scalar_mae_budget"]
    if budgets is None:
        # No commercial budget → inherit head only (conservative: never invent OK).
        return ScalarStatus(
            validity=head_st.validity,
            confidence=head_st.confidence,
            calib_mae_rad=float(calib_mae) if np.isfinite(calib_mae) else float("nan"),
            residual=head_st.residual,
            reasons=reasons + ["no_mae_budget_inherit_head"],
            ok_budget_rad=float("nan"),
            degraded_budget_rad=float("nan"),
        )
    ok_max, deg_max = float(budgets[0]), float(budgets[1])
    if not np.isfinite(calib_mae):
        base = Validity.ABSTAIN
        conf = 0.05
        reasons.append("calib_mae_unavailable")
    elif calib_mae > deg_max:
        base = Validity.ABSTAIN
        conf = 0.1
        reasons.append("calib_mae_exceeds_degraded_budget")
    elif calib_mae > ok_max:
        span = max(1e-6, deg_max - ok_max)
        t = (calib_mae - ok_max) / span
        base = Validity.DEGRADED
        conf = clip_confidence(0.55 * (1.0 - 0.5 * t))
        reasons.append("calib_mae_exceeds_ok_budget")
    else:
        base = Validity.OK
        conf = clip_confidence(1.0 / (1.0 + calib_mae / max(ok_max, 1e-6)))
        reasons.append("calib_mae_within_ok_budget")

    # Head OOD can only worsen scalar status.
    if head_st.validity == Validity.ABSTAIN:
        if base != Validity.ABSTAIN:
            reasons.append("head_ood_abstain")
        base = Validity.ABSTAIN
        conf = min(conf, float(head_st.confidence))
    elif head_st.validity == Validity.DEGRADED:
        if _VALIDITY_RANK[base] < _VALIDITY_RANK[Validity.DEGRADED]:
            base = Validity.DEGRADED
            reasons.append("head_ood_degraded")
        conf = min(conf, float(head_st.confidence))

    return ScalarStatus(
        validity=base,
        confidence=conf,
        calib_mae_rad=float(calib_mae) if np.isfinite(calib_mae) else float("nan"),
        residual=float(head_st.residual),
        reasons=reasons,
        ok_budget_rad=ok_max,
        degraded_budget_rad=deg_max,
    )


def _combine_scalar_status(
    a: ScalarStatus, b: ScalarStatus, *, reason: str
) -> ScalarStatus:
    """Worst-of combine for derived scalars (e.g. FE delta)."""
    if _VALIDITY_RANK[a.validity] >= _VALIDITY_RANK[b.validity]:
        worst, other = a, b
    else:
        worst, other = b, a
    reasons = list(worst.reasons) + [reason]
    if other.validity != worst.validity:
        reasons.append(f"combined_with_{other.validity.value}")
    return ScalarStatus(
        validity=worst.validity,
        confidence=min(float(a.confidence), float(b.confidence)),
        calib_mae_rad=max(
            float(a.calib_mae_rad) if np.isfinite(a.calib_mae_rad) else 0.0,
            float(b.calib_mae_rad) if np.isfinite(b.calib_mae_rad) else 0.0,
        ),
        residual=max(
            float(a.residual) if np.isfinite(a.residual) else 0.0,
            float(b.residual) if np.isfinite(b.residual) else 0.0,
        ),
        reasons=reasons,
        ok_budget_rad=min(
            float(a.ok_budget_rad) if np.isfinite(a.ok_budget_rad) else float("inf"),
            float(b.ok_budget_rad) if np.isfinite(b.ok_budget_rad) else float("inf"),
        ),
        degraded_budget_rad=min(
            float(a.degraded_budget_rad)
            if np.isfinite(a.degraded_budget_rad)
            else float("inf"),
            float(b.degraded_budget_rad)
            if np.isfinite(b.degraded_budget_rad)
            else float("inf"),
        ),
    )


def _worst_validity(statuses: Iterable[HeadStatus | ScalarStatus]) -> Validity:
    worst = Validity.OK
    for st in statuses:
        if _VALIDITY_RANK[st.validity] > _VALIDITY_RANK[worst]:
            worst = st.validity
    return worst


def _nan_if_abstain(value: float, st: HeadStatus | ScalarStatus | None) -> float:
    if st is not None and st.validity == Validity.ABSTAIN:
        return float("nan")
    return float(value)


def _lookup_scalar_mae(model: HighOrderPCR, key: str) -> float:
    head_name = SCALAR_TO_HEAD.get(key)
    if head_name and head_name in model.heads:
        mae = model.heads[head_name].calibration.scalar_mae.get(key)
        if mae is not None:
            return float(mae)
    return float("nan")


def build_scalar_statuses(
    model: HighOrderPCR,
    head_status: dict[str, HeadStatus],
) -> dict[str, ScalarStatus]:
    """Build per-scalar status from calib MAE budgets ∩ head OOD."""
    out: dict[str, ScalarStatus] = {}
    for key in PERSONAL_SCALAR_KEYS:
        head_name = SCALAR_TO_HEAD[key]
        hst = head_status.get(head_name) or HeadStatus(
            Validity.ABSTAIN, 0.05, float("nan"), ["missing_head"]
        )
        out[key] = _scalar_status_from_mae(key, _lookup_scalar_mae(model, key), hst)
    return out


def infer_high_order(
    t: ArrayLike,
    gyro: ArrayLike,
    quats: ArrayLike,
    phases: SwingPhases,
    *,
    model: HighOrderPCR | None = None,
    channel_kind: str = "unknown_segment",
    personal: PersonalHighOrderPrior | None = None,
) -> HighOrderEstimate | None:
    """Run multi-head PCR inference; returns None if weights missing."""
    model = model or load_high_order_model()
    if model is None:
        return None
    t = np.asarray(t, dtype=np.float64)
    gyro = np.asarray(gyro, dtype=np.float64)
    quats = np.asarray(quats, dtype=np.float64)
    dt = float(np.median(np.diff(t))) if t.size > 1 else 0.005
    obs_mat = _obs_matrix(gyro, quats, dt, phases.address_idx, channel_kind)
    n_expected = len(model.obs_names)
    if obs_mat.shape[1] < n_expected:
        return None
    if obs_mat.shape[1] > n_expected:
        obs_mat = obs_mat[:, :n_expected]
    normed = phase_normalize(
        t,
        obs_mat,
        phases,
        channel_names=model.obs_names,
        grid_sizes=model.grid_sizes,
    )
    x = concatenate_phases(normed).reshape(-1)
    if x.size != model.obs_mean.size:
        return None

    waves, head_resids, global_resid = model.predict_targets(x)
    if not np.isfinite(global_resid) or global_resid > 2.5:
        z = (x - model.obs_mean) / (model.obs_scale + 1e-9)
        z = np.clip(z, -6.0, 6.0)
        x_clip = z * (model.obs_scale + 1e-9) + model.obs_mean
        waves, head_resids, global_resid = model.predict_targets(x_clip)
        global_resid = max(float(global_resid), 0.8)
        for k in list(head_resids.keys()):
            head_resids[k] = max(float(head_resids[k]), 0.8)

    grid = model.grid_sizes

    # Event-scalar refinement (impact FE / face) when available — wrist/club heads.
    if model.event_W is not None and model.event_b is not None:
        s_obs = model.encode_obs(x)
        feat = _event_features(x, s_obs, grid, len(model.obs_names))
        if feat.size == model.event_W.shape[1]:
            ev = model.event_W @ feat + model.event_b
            if "wrist_fe_rad" in waves:
                fe_i0 = _sample_at_phase_frac(waves["wrist_fe_rad"], grid, "impact", 0.0)
                fe_i = float(0.35 * fe_i0 + 0.65 * ev[0])
                waves["wrist_fe_rad"] = waves["wrist_fe_rad"].copy()
                g0, g1 = grid["address_to_top"], grid["top_to_impact"]
                waves["wrist_fe_rad"][g0 + g1 - 1] = fe_i
            if "clubface_rad" in waves:
                face_i0 = _sample_at_phase_frac(waves["clubface_rad"], grid, "impact", 0.0)
                face_i = float(0.35 * face_i0 + 0.65 * ev[1])
                waves["clubface_rad"] = waves["clubface_rad"].copy()
                g0, g1 = grid["address_to_top"], grid["top_to_impact"]
                waves["clubface_rad"][g0 + g1 - 1] = face_i

    head_status: dict[str, HeadStatus] = {}
    for hname in HEAD_NAMES:
        if hname in model.heads:
            calib = model.heads[hname].calibration
            resid = float(head_resids.get(hname, global_resid))
            head_status[hname] = _status_from_resid(resid, calib)
        else:
            # Legacy weights: shared residual thresholds.
            resid = float(global_resid)
            if resid > 1.2:
                head_status[hname] = HeadStatus(
                    Validity.ABSTAIN, min(0.25, clip_confidence(1.0 / (1.0 + 1.5 * resid))), resid,
                    ["legacy_global", "outside_calib_envelope"],
                )
            elif resid > 0.55:
                head_status[hname] = HeadStatus(
                    Validity.DEGRADED, clip_confidence(1.0 / (1.0 + 1.5 * resid)), resid,
                    ["legacy_global", "near_calib_edge"],
                )
            else:
                head_status[hname] = HeadStatus(
                    Validity.OK, clip_confidence(1.0 / (1.0 + 1.5 * resid)), resid,
                    ["legacy_global", "inside_calib_envelope"],
                )

    def _get(name: str, which: str) -> float:
        w = waves.get(name)
        if w is None:
            return float("nan")
        return _sample_at_phase_frac(w, grid, which, 0.0)

    fe_a = _get("wrist_fe_rad", "address")
    fe_t = _get("wrist_fe_rad", "top")
    fe_i = _get("wrist_fe_rad", "impact")
    ru_i = _get("wrist_ru_rad", "impact")
    ps_i = _get("forearm_ps_rad", "impact")
    face_i = _get("clubface_rad", "impact")
    lean_i = _get("shaft_lean_rad", "impact")
    xf_t = _get("x_factor_rad", "top")

    g0, g1 = grid["address_to_top"], grid["top_to_impact"]
    down_frac = np.linspace(0.0, 1.0, g1)
    ds = float(normed.phase_durations_s.get("top_to_impact", 0.25))

    def peak_to_imp(name: str) -> float:
        w = waves.get(name)
        if w is None:
            return float("nan")
        seg = w[g0 : g0 + g1]
        rate = np.gradient(seg)
        i = int(np.argmax(np.abs(rate)))
        return float((1.0 - down_frac[i]) * ds)

    body_st = head_status["body"]
    if body_st.validity != Validity.ABSTAIN:
        p_pel = peak_to_imp("pelvis_angle_rad")
        p_tor = peak_to_imp("torso_angle_rad")
        p_arm = peak_to_imp("arm_angle_rad")
        p_clb = peak_to_imp("club_angle_rad")
        order_ok = bool(
            np.isfinite(p_pel)
            and np.isfinite(p_tor)
            and np.isfinite(p_arm)
            and np.isfinite(p_clb)
            and p_pel >= p_tor >= p_arm >= p_clb - 1e-6
        )
    else:
        p_pel = p_tor = p_arm = p_clb = float("nan")
        order_ok = False

    wrist_st, club_st = head_status["wrist"], head_status["club"]
    scalar_status = build_scalar_statuses(model, head_status)

    overall = _worst_validity(list(head_status.values()) + list(scalar_status.values()))
    confs = [st.confidence for st in head_status.values()]
    confs += [st.confidence for st in scalar_status.values() if st.validity != Validity.ABSTAIN]
    overall_conf = clip_confidence(float(np.mean(confs))) if confs else 0.2
    reasons = ["high_order_multihead_pcr"]
    if overall == Validity.ABSTAIN:
        reasons.append("one_or_more_heads_or_scalars_abstain")
    elif overall == Validity.DEGRADED:
        reasons.append("one_or_more_heads_or_scalars_degraded")

    est = HighOrderEstimate(
        wrist_fe_address_rad=_nan_if_abstain(fe_a, scalar_status.get("wrist_fe_address_rad")),
        wrist_fe_top_rad=_nan_if_abstain(fe_t, scalar_status.get("wrist_fe_top_rad")),
        wrist_fe_impact_rad=_nan_if_abstain(fe_i, scalar_status.get("wrist_fe_impact_rad")),
        wrist_ru_impact_rad=_nan_if_abstain(ru_i, scalar_status.get("wrist_ru_impact_rad")),
        forearm_ps_impact_rad=_nan_if_abstain(
            ps_i, scalar_status.get("forearm_ps_impact_rad")
        ),
        clubface_impact_rad=_nan_if_abstain(
            face_i, scalar_status.get("clubface_impact_rad")
        ),
        shaft_lean_impact_rad=_nan_if_abstain(
            lean_i, scalar_status.get("shaft_lean_impact_rad")
        ),
        x_factor_top_rad=_nan_if_abstain(xf_t, scalar_status.get("x_factor_top_rad")),
        waveforms=waves,
        pelvis_peak_to_impact_s=p_pel,
        torso_peak_to_impact_s=p_tor,
        arm_peak_to_impact_s=p_arm,
        club_peak_to_impact_s=p_clb,
        sequence_order_ok=order_ok,
        residual=float(global_resid),
        confidence=overall_conf,
        validity=overall,
        kind=MetricKind.INFERRED,
        model_version=model.version,
        heads=head_status,
        scalars=scalar_status,
        extras={
            "n_train": float(model.n_train),
            "n_calib": float(model.n_calib),
            "channel_kind_code": float(hash(channel_kind) % 1000),
            "wrist_residual": float(wrist_st.residual),
            "club_residual": float(club_st.residual),
            "body_residual": float(body_st.residual),
        },
        reasons=reasons,
    )
    if personal is not None:
        est = personal.apply(est)
    return est


def evaluate_leave_generator_out(
    *,
    holdout_family: str,
    n_train: int = 60,
    n_test: int = 12,
    seed: int = 0,
    fs_hz: float = 200.0,
    calib_frac: float = 0.25,
) -> dict[str, Any]:
    """Train excluding one generator family; score on held-out family vs mean baseline.

    Thresholds / envelopes come only from the training split's calibration holdout
    (still excluding the left-out family). Test metrics are never used to set
    success gates inside this utility.
    """
    if holdout_family not in GENERATOR_FAMILIES:
        raise ValueError(f"unknown family: {holdout_family}")
    train_fams = [f for f in GENERATOR_FAMILIES if f != holdout_family]
    train_data = generate_teacher_dataset(
        n_swings=n_train, seed=seed, fs_hz=fs_hz, families=train_fams
    )
    model = fit_high_order_pcr(
        train_data["obs"],
        train_data["tgt"],
        event_fe=train_data["event_fe"],
        event_face=train_data["event_face"],
        scalars=train_data["scalars"],
        grid_sizes=train_data["grid_sizes"],
        calib_frac=calib_frac,
        split_seed=seed,
        train_families=train_fams,
    )
    test_data = generate_teacher_dataset(
        n_swings=n_test,
        seed=seed + 10_007,
        fs_hz=fs_hz,
        families=(holdout_family,),
        grid_sizes=train_data["grid_sizes"],
    )

    # Baseline: train-set mean of scalar labels.
    base: dict[str, float] = {}
    for key in ("wrist_fe_impact_rad", "clubface_impact_rad", "x_factor_top_rad"):
        vals = [float(s[key]) for s in train_data["scalars"] if np.isfinite(s[key])]
        base[key] = float(np.mean(vals)) if vals else 0.0

    model_errs: dict[str, list[float]] = {k: [] for k in base}
    base_errs: dict[str, list[float]] = {k: [] for k in base}
    abstain_counts = {h: 0 for h in HEAD_NAMES}
    n_ok = 0
    for obs, sc in zip(test_data["obs"], test_data["scalars"]):
        waves, hres, _ = model.predict_targets(obs)
        statuses = {
            h: _status_from_resid(float(hres[h]), model.heads[h].calibration)
            for h in model.heads
        }
        for h, st in statuses.items():
            if st.validity == Validity.ABSTAIN:
                abstain_counts[h] += 1
        if all(st.validity != Validity.ABSTAIN for st in statuses.values()):
            n_ok += 1
        pred = _scalar_from_waves(waves, model.grid_sizes)
        for key in base:
            head = SCALAR_TO_HEAD[key]
            if statuses[head].validity == Validity.ABSTAIN:
                continue
            pe, te = float(pred[key]), float(sc[key])
            if np.isfinite(pe) and np.isfinite(te):
                model_errs[key].append(abs(pe - te))
                base_errs[key].append(abs(base[key] - te))

    def _mean(xs: list[float]) -> float:
        return float(np.mean(xs)) if xs else float("nan")

    return {
        "holdout_family": holdout_family,
        "n_train": int(model.n_train),
        "n_calib": int(model.n_calib),
        "n_test": int(n_test),
        "model_mae": {k: _mean(v) for k, v in model_errs.items()},
        "baseline_mae": {k: _mean(v) for k, v in base_errs.items()},
        "abstain_rate": {h: abstain_counts[h] / max(1, n_test) for h in HEAD_NAMES},
        "all_heads_ok_rate": n_ok / max(1, n_test),
        "model_version": model.version,
    }


def heldout_errors_vs_baseline(
    model: HighOrderPCR,
    obs_waves: Sequence[ArrayF],
    scalars: Sequence[dict[str, float]],
    *,
    train_scalars: Sequence[dict[str, float]],
) -> dict[str, Any]:
    """Compare model MAE vs train-mean baseline on a held-out feature set."""
    base: dict[str, float] = {}
    keys = ("wrist_fe_impact_rad", "clubface_impact_rad", "x_factor_top_rad")
    for key in keys:
        vals = [float(s[key]) for s in train_scalars if np.isfinite(float(s[key]))]
        base[key] = float(np.mean(vals)) if vals else 0.0
    model_errs = {k: [] for k in keys}
    base_errs = {k: [] for k in keys}
    grid = model.grid_sizes
    for obs, sc in zip(obs_waves, scalars):
        x = np.asarray(obs, dtype=np.float64)
        waves, _, _ = model.predict_targets(x)
        if model.event_W is not None and model.event_b is not None:
            s_obs = model.encode_obs(x)
            feat = _event_features(x, s_obs, grid, len(model.obs_names))
            if feat.size == model.event_W.shape[1]:
                ev = model.event_W @ feat + model.event_b
                g0, g1 = grid["address_to_top"], grid["top_to_impact"]
                if "wrist_fe_rad" in waves:
                    waves["wrist_fe_rad"] = waves["wrist_fe_rad"].copy()
                    waves["wrist_fe_rad"][g0 + g1 - 1] = float(
                        0.35 * waves["wrist_fe_rad"][g0 + g1 - 1] + 0.65 * ev[0]
                    )
                if "clubface_rad" in waves:
                    waves["clubface_rad"] = waves["clubface_rad"].copy()
                    waves["clubface_rad"][g0 + g1 - 1] = float(
                        0.35 * waves["clubface_rad"][g0 + g1 - 1] + 0.65 * ev[1]
                    )
        pred = _scalar_from_waves(waves, grid)
        for key in keys:
            pe, te = float(pred[key]), float(sc[key])
            if np.isfinite(pe) and np.isfinite(te):
                model_errs[key].append(abs(pe - te))
                base_errs[key].append(abs(base[key] - te))
    return {
        "model_mae": {k: float(np.mean(v)) if v else float("nan") for k, v in model_errs.items()},
        "baseline_mae": {k: float(np.mean(v)) if v else float("nan") for k, v in base_errs.items()},
    }


__all__ = [
    "GENERATOR_FAMILIES",
    "HEAD_NAMES",
    "HEAD_SPECS",
    "MODEL_VERSION",
    "OBS_NAMES",
    "PERSONAL_PRIOR_VERSION",
    "PERSONAL_SCALAR_KEYS",
    "SCALAR_MAE_BUDGETS_RAD",
    "SCALAR_METRIC_ALIASES",
    "SCALAR_TO_HEAD",
    "TARGET_NAMES",
    "HeadCalibration",
    "HeadPCR",
    "HeadStatus",
    "HighOrderEstimate",
    "HighOrderPCR",
    "PersonalHighOrderPrior",
    "ScalarStatus",
    "TeacherSampleSpec",
    "build_default_high_order_model",
    "build_scalar_statuses",
    "evaluate_leave_generator_out",
    "fit_high_order_pcr",
    "fit_personal_high_order_prior",
    "generate_teacher_dataset",
    "heldout_errors_vs_baseline",
    "infer_high_order",
    "iter_teacher_specs",
    "load_high_order_model",
    "train_calib_split",
]
