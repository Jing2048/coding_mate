"""Biomechanical proxy features from wrist IMU (not absolute full-body truth).

A small linear map — fitted offline on multibody ground truth — predicts
proximal timing / X-factor *proxies* from wrist angular-rate envelope features.
All outputs are labelled as proxies with an explicit confidence score.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import ArrayLike, NDArray

from golfmate_algo.types import SwingPhases

ArrayF = NDArray[np.float64]

_WEIGHTS_PATH = Path(__file__).with_name("proxy_weights.json")

# Default weights: identity-ish fallbacks until fit_proxy_weights refreshes JSON.
_DEFAULT = {
    "feature_names": [
        "peak_omega",
        "mean_omega_down",
        "tempo_s",
        "rhythm",
        "peak_to_impact_s",
        "omega_skew_down",
    ],
    "targets": {
        "x_factor_proxy_deg": [8.0, 0.02, 2.0, 1.5, -5.0, 0.5, 25.0],
        "pelvis_peak_to_impact_s": [0.0, 0.0, 0.15, 0.02, 0.4, 0.0, 0.12],
        "torso_peak_to_impact_s": [0.0, 0.0, 0.08, 0.01, 0.25, 0.0, 0.08],
        "sequence_score": [0.01, 0.002, 0.1, 0.05, -0.2, 0.05, 0.7],
    },
    "confidence_scale": 0.35,
}


def _load_weights() -> dict:
    if _WEIGHTS_PATH.exists():
        return json.loads(_WEIGHTS_PATH.read_text(encoding="utf-8"))
    return _DEFAULT


@dataclass
class BiomechProxies:
    x_factor_proxy_deg: float
    pelvis_peak_to_impact_s: float
    torso_peak_to_impact_s: float
    sequence_score: float
    confidence: float
    is_proxy: bool = True


def wrist_feature_vector(
    t: ArrayLike,
    gyro: ArrayLike,
    phases: SwingPhases,
) -> ArrayF:
    t = np.asarray(t, dtype=np.float64).reshape(-1)
    gyro = np.asarray(gyro, dtype=np.float64).reshape(-1, 3)
    omega = np.linalg.norm(gyro, axis=1)
    a, top, imp = phases.address_idx, phases.top_idx, phases.impact_idx
    down = omega[top : imp + 1]
    peak_idx = top + int(np.argmax(down)) if down.size else imp
    peak_omega = float(omega[peak_idx])
    mean_down = float(np.mean(down)) if down.size else 0.0
    tempo = float(t[imp] - t[a])
    rhythm = float((t[top] - t[a]) / max(t[imp] - t[top], 1e-9))
    peak_to_impact = float(t[imp] - t[peak_idx])
    skew = float(
        ((down - mean_down) ** 3).mean() / (np.std(down) ** 3 + 1e-9)
    ) if down.size > 2 else 0.0
    return np.array(
        [peak_omega, mean_down, tempo, rhythm, peak_to_impact, skew], dtype=np.float64
    )


def estimate_biomech_proxies(
    t: ArrayLike,
    gyro: ArrayLike,
    phases: SwingPhases,
) -> BiomechProxies:
    w = _load_weights()
    feat = wrist_feature_vector(t, gyro, phases)
    x = np.concatenate([feat, np.ones(1)])  # bias term
    outs: dict[str, float] = {}
    for name, coef in w["targets"].items():
        c = np.asarray(coef, dtype=np.float64)
        outs[name] = float(np.dot(c[: x.size], x))
    # Confidence: higher when rhythm is in a typical band and peak ω is strong
    rhythm = float(feat[3])
    peak = float(feat[0])
    conf = float(
        np.clip(
            w.get("confidence_scale", 0.35)
            * (1.0 - abs(rhythm - 3.0) / 5.0)
            * np.tanh(peak / 8.0),
            0.05,
            0.95,
        )
    )
    return BiomechProxies(
        x_factor_proxy_deg=outs.get("x_factor_proxy_deg", 0.0),
        pelvis_peak_to_impact_s=outs.get("pelvis_peak_to_impact_s", 0.0),
        torso_peak_to_impact_s=outs.get("torso_peak_to_impact_s", 0.0),
        sequence_score=float(np.clip(outs.get("sequence_score", 0.5), 0.0, 1.0)),
        confidence=conf,
        is_proxy=True,
    )


def fit_proxy_weights(n_swings: int = 24, seed: int = 0) -> dict:
    """Offline ridge fit on multibody ground truth; writes ``proxy_weights.json``."""
    from golfmate_algo.synth.multibody import SwingConfig, build_swing, casting_swing

    rng = np.random.default_rng(seed)
    X_rows: list[ArrayF] = []
    Y: dict[str, list[float]] = {
        "x_factor_proxy_deg": [],
        "pelvis_peak_to_impact_s": [],
        "torso_peak_to_impact_s": [],
        "sequence_score": [],
    }
    for i in range(n_swings):
        cfg = SwingConfig(
            fs_hz=200.0,
            plane_tilt_deg=float(rng.choice([45.0, 55.0, 65.0])),
            backswing_s=float(rng.uniform(0.65, 0.95)),
            downswing_s=float(rng.uniform(0.20, 0.32)),
        )
        truth = casting_swing(cfg) if i % 4 == 0 else build_swing(cfg)
        ph = truth.phases()
        feat = wrist_feature_vector(truth.t, truth.gyro_body, ph)
        X_rows.append(np.concatenate([feat, np.ones(1)]))
        # Targets from multibody analytics
        Y["x_factor_proxy_deg"].append(float(truth.meta.get("x_factor_top_deg", 0.0)))
        # segment peak times relative to impact
        imp_t = float(truth.t[ph.impact_idx])
        Y["pelvis_peak_to_impact_s"].append(imp_t - float(truth.seg_peak_speed_time[0]))
        Y["torso_peak_to_impact_s"].append(imp_t - float(truth.seg_peak_speed_time[1]))
        Y["sequence_score"].append(1.0 if truth.kinematic_sequence_ok() else 0.0)

    X = np.asarray(X_rows, dtype=np.float64)
    ridge = 1e-2
    targets = {}
    for name, vals in Y.items():
        y = np.asarray(vals, dtype=np.float64)
        coef = np.linalg.solve(X.T @ X + ridge * np.eye(X.shape[1]), X.T @ y)
        targets[name] = coef.tolist()
    payload = {
        "feature_names": _DEFAULT["feature_names"],
        "targets": targets,
        "confidence_scale": 0.4,
        "n_train": n_swings,
    }
    _WEIGHTS_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload
