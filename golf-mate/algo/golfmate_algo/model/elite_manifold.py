"""Professional swing waveform manifold (PCA over phase-normalized channels).

Built offline from healthy synthetic / elite cohorts. Scoring is relative to a
distribution — never a single “correct posture”. Residuals flag out-of-manifold
shapes; PCA scores support coaching heatmaps by phase.

Anti-pattern: do not claim this equals optical pro mocap without subject-held-out
real IMU validation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from numpy.typing import ArrayLike, NDArray

from golfmate_algo.model.phase_normalize import (
    PhaseNormalizedSwing,
    concatenate_phases,
    phase_normalize,
)
from golfmate_algo.types import SwingPhases

ArrayF = NDArray[np.float64]

_DEFAULT_PATH = Path(__file__).with_name("pro_manifold.json")


@dataclass
class ManifoldScore:
    pca_score: float  # Hotelling-like distance in retained PCA space (0=center)
    residual: float  # reconstruction residual (normalized)
    phase_residuals: dict[str, float]
    n_components: int
    template_version: str
    confidence: float
    is_proxy: bool = True
    extras: dict[str, float] = field(default_factory=dict)


@dataclass
class ProManifold:
    mean: ArrayF  # (D,)
    components: ArrayF  # (K, D)
    eigenvalues: ArrayF  # (K,)
    channel_names: tuple[str, ...]
    grid_sizes: dict[str, int]
    version: str
    n_train: int
    scale: ArrayF  # per-dim robust scale

    @property
    def n_components(self) -> int:
        return int(self.components.shape[0])

    def transform(self, x: ArrayF) -> ArrayF:
        z = (x - self.mean) / (self.scale + 1e-9)
        return self.components @ z

    def reconstruct(self, scores: ArrayF) -> ArrayF:
        z = self.components.T @ scores
        return z * (self.scale + 1e-9) + self.mean

    def score_vector(self, x: ArrayF) -> ManifoldScore:
        x = np.asarray(x, dtype=np.float64).reshape(-1)
        if x.size != self.mean.size:
            raise ValueError("feature dimension mismatch")
        scores = self.transform(x)
        # Hotelling-ish: sum (score_k^2 / λ_k)
        lam = np.maximum(self.eigenvalues, 1e-9)
        hotelling = float(np.sqrt(np.sum((scores**2) / lam) / max(len(scores), 1)))
        recon = self.reconstruct(scores)
        resid = float(np.linalg.norm((x - recon) / (self.scale + 1e-9)) / np.sqrt(x.size))
        # Phase-local residuals
        d0 = self.grid_sizes.get("address_to_top", 48) * len(self.channel_names)
        d1 = self.grid_sizes.get("top_to_impact", 32) * len(self.channel_names)
        d2 = self.grid_sizes.get("impact_to_finish", 32) * len(self.channel_names)
        chunks = {
            "address_to_top": (0, d0),
            "top_to_impact": (d0, d0 + d1),
            "impact_to_finish": (d0 + d1, d0 + d1 + d2),
        }
        phase_res: dict[str, float] = {}
        err = (x - recon) / (self.scale + 1e-9)
        for name, (lo, hi) in chunks.items():
            if hi <= lo or hi > err.size:
                phase_res[name] = float("nan")
            else:
                phase_res[name] = float(np.linalg.norm(err[lo:hi]) / np.sqrt(max(hi - lo, 1)))
        conf = float(np.clip(1.0 / (1.0 + 0.5 * hotelling + resid), 0.05, 0.95))
        return ManifoldScore(
            pca_score=hotelling,
            residual=resid,
            phase_residuals=phase_res,
            n_components=self.n_components,
            template_version=self.version,
            confidence=conf,
            is_proxy=True,
            extras={"n_train": float(self.n_train)},
        )

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "n_train": self.n_train,
            "channel_names": list(self.channel_names),
            "grid_sizes": self.grid_sizes,
            "mean": self.mean.tolist(),
            "components": self.components.tolist(),
            "eigenvalues": self.eigenvalues.tolist(),
            "scale": self.scale.tolist(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ProManifold":
        return cls(
            mean=np.asarray(d["mean"], dtype=np.float64),
            components=np.asarray(d["components"], dtype=np.float64),
            eigenvalues=np.asarray(d["eigenvalues"], dtype=np.float64),
            channel_names=tuple(d["channel_names"]),
            grid_sizes={k: int(v) for k, v in d["grid_sizes"].items()},
            version=str(d.get("version", "pro-manifold-v1")),
            n_train=int(d.get("n_train", 0)),
            scale=np.asarray(d["scale"], dtype=np.float64),
        )


def fit_pro_manifold(
    waveforms: list[ArrayF],
    *,
    channel_names: tuple[str, ...],
    grid_sizes: dict[str, int],
    n_components: int = 6,
    version: str = "pro-manifold-v1",
) -> ProManifold:
    """Fit PCA manifold from flattened phase-normalized waveforms."""
    X = np.stack([np.asarray(w, dtype=np.float64).reshape(-1) for w in waveforms], axis=0)
    mean = np.median(X, axis=0)  # robust center
    scale = np.median(np.abs(X - mean), axis=0) * 1.4826
    scale = np.maximum(scale, 1e-6)
    Z = (X - mean) / scale
    # Economy SVD
    _, s, vt = np.linalg.svd(Z, full_matrices=False)
    k = int(min(n_components, vt.shape[0], max(1, X.shape[0] - 1)))
    components = vt[:k]
    # eigenvalues ~ s^2 / (n-1)
    eig = (s[:k] ** 2) / max(X.shape[0] - 1, 1)
    return ProManifold(
        mean=mean,
        components=components,
        eigenvalues=eig,
        channel_names=channel_names,
        grid_sizes=grid_sizes,
        version=version,
        n_train=int(X.shape[0]),
        scale=scale,
    )


def build_default_manifold(
    n_swings: int = 24,
    seed: int = 0,
    path: Path | None = None,
) -> ProManifold:
    """Fit from healthy multibody swings and optionally persist JSON."""
    from golfmate_algo.ahrs.suite import GatedAdaptive
    from golfmate_algo.ahrs import init as ahrs_init
    from golfmate_algo.biomechanics.wrist_channels import estimate_segment_channels
    from golfmate_algo.events.segmental import detect_phases_segmental
    from golfmate_algo.synth.multibody import SwingConfig, build_swing

    rng = np.random.default_rng(seed)
    waves: list[ArrayF] = []
    names = ("omega", "twist_rate", "plane_rate", "twist")
    grid = {"address_to_top": 48, "top_to_impact": 32, "impact_to_finish": 32}
    for i in range(n_swings):
        cfg = SwingConfig(
            plane_tilt_deg=float(rng.uniform(45.0, 60.0)),
            backswing_s=float(rng.uniform(0.70, 0.90)),
            downswing_s=float(rng.uniform(0.22, 0.32)),
            center_sway_amp_m=float(rng.uniform(0.0, 0.03)),
        )
        truth = build_swing(cfg)
        pkt = truth.to_imu_packet()
        fs = pkt.frame.fs_hz
        dt = 1.0 / fs
        q0, _, _ = ahrs_init.estimate_address_orientation(pkt.gyro, pkt.accel, fs)
        quats, _ = GatedAdaptive(use_signed_log_tilt=True).run(
            pkt.gyro, pkt.accel, dt, q0=q0
        )
        phases = detect_phases_segmental(pkt.t, pkt.gyro, pkt.accel)
        ch = estimate_segment_channels(
            quats, pkt.gyro, dt, address_idx=phases.address_idx
        )
        omega = np.linalg.norm(pkt.gyro, axis=1)
        mat = np.column_stack(
            [omega, ch.twist_rate_rad_s, ch.omega_plane_rad_s, ch.twist_rad]
        )
        normed = phase_normalize(
            pkt.t, mat, phases, channel_names=names, grid_sizes=grid
        )
        waves.append(concatenate_phases(normed).reshape(-1))
    man = fit_pro_manifold(waves, channel_names=names, grid_sizes=grid, n_components=6)
    out = path or _DEFAULT_PATH
    out.write_text(json.dumps(man.to_dict()), encoding="utf-8")
    return man


def load_pro_manifold(path: Path | None = None) -> ProManifold | None:
    p = path or _DEFAULT_PATH
    if not p.exists():
        return None
    return ProManifold.from_dict(json.loads(p.read_text(encoding="utf-8")))


def score_against_manifold(
    normed: PhaseNormalizedSwing,
    manifold: ProManifold | None = None,
) -> ManifoldScore | None:
    man = manifold or load_pro_manifold()
    if man is None:
        return None
    x = concatenate_phases(normed).reshape(-1)
    if x.size != man.mean.size:
        return None
    return man.score_vector(x)
