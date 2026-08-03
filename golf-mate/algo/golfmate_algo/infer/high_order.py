"""High-order kinematic inference from a single distal IMU.

Modern approach (WIT-KinNet / Lauer lineage, compact form)
---------------------------------------------------------
A Watch does not *directly measure* clubface or a second wrist bone. We learn a
phase-anchored **principal-component regression (PCR)** that maps distal
observables (ω, body-frame gyro axes, twist/swing channels, plane rates) onto a
latent full-chain state whose coordinates are:

* lead wrist FE / RU (HackMotion-style, address-relative)
* forearm pronation/supination
* clubface open/closed and shaft lean
* pelvis / torso / arm / club plane angles + X-factor
* proximal→distal sequence timing

Training uses the independent multibody oracle with FE/face rates physically
coupled into the distal gyro (observable DoFs). At runtime the model emits
``MetricKind.INFERRED`` estimates with residual-based confidence — the correct
label for single-node high-order claims (not launch-monitor measured).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import ArrayLike, NDArray

from golfmate_algo.model.phase_normalize import (
    concatenate_phases,
    phase_normalize,
)
from golfmate_algo.quality.uncertainty import MetricKind, Validity, clip_confidence
from golfmate_algo.types import SwingPhases

ArrayF = NDArray[np.float64]

_DEFAULT_WEIGHTS = Path(__file__).with_name("high_order_weights.json")

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

# Body-frame gyro axes make FE (≈gx) and face/twist (≈gz) directly visible.
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

_DEFAULT_GRID = {"address_to_top": 48, "top_to_impact": 32, "impact_to_finish": 32}


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
    model_version: str = "high-order-pcr-v2"
    extras: dict[str, float] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        def deg(x: float) -> float:
            return float(np.degrees(x)) if np.isfinite(x) else float("nan")

        return {
            "kind": self.kind.value,
            "validity": self.validity.value,
            "confidence": self.confidence,
            "residual": self.residual,
            "model_version": self.model_version,
            "source": "high_order_pcr",
            "wrist": {
                "fe_address_deg": deg(self.wrist_fe_address_rad),
                "fe_top_deg": deg(self.wrist_fe_top_rad),
                "fe_impact_deg": deg(self.wrist_fe_impact_rad),
                "ru_impact_deg": deg(self.wrist_ru_impact_rad),
                "ps_impact_deg": deg(self.forearm_ps_impact_rad),
                "fe_delta_address_to_impact_deg": deg(
                    self.wrist_fe_impact_rad - self.wrist_fe_address_rad
                ),
            },
            "club": {
                "face_impact_deg": deg(self.clubface_impact_rad),
                "face_open_closed": (
                    "open"
                    if self.clubface_impact_rad > np.deg2rad(2.0)
                    else (
                        "closed"
                        if self.clubface_impact_rad < -np.deg2rad(2.0)
                        else "square"
                    )
                ),
                "shaft_lean_impact_deg": deg(self.shaft_lean_impact_rad),
            },
            "body": {
                "x_factor_top_deg": deg(self.x_factor_top_rad),
                "pelvis_peak_to_impact_s": self.pelvis_peak_to_impact_s,
                "torso_peak_to_impact_s": self.torso_peak_to_impact_s,
                "arm_peak_to_impact_s": self.arm_peak_to_impact_s,
                "club_peak_to_impact_s": self.club_peak_to_impact_s,
                "sequence_order_ok": self.sequence_order_ok,
            },
            "extras": self.extras,
        }


@dataclass
class HighOrderPCR:
    """Phase-anchored PCR: obs waveform → target waveforms."""

    obs_mean: ArrayF
    obs_scale: ArrayF
    obs_components: ArrayF  # (K, D_obs)
    W: ArrayF  # (K_tgt, K_obs)
    b: ArrayF  # (K_tgt,)
    tgt_mean: ArrayF
    tgt_scale: ArrayF
    tgt_components: ArrayF  # (K_tgt, D_tgt)
    obs_names: tuple[str, ...]
    target_names: tuple[str, ...]
    grid_sizes: dict[str, int]
    version: str
    n_train: int
    # Event-scalar refinement: impact FE / face from local obs scores
    event_W: ArrayF | None = None  # (2, K_obs+3)
    event_b: ArrayF | None = None  # (2,)

    def encode_obs(self, x: ArrayF) -> ArrayF:
        z = (x - self.obs_mean) / (self.obs_scale + 1e-9)
        return self.obs_components @ z

    def decode_tgt(self, scores: ArrayF) -> ArrayF:
        z = self.tgt_components.T @ scores
        return z * (self.tgt_scale + 1e-9) + self.tgt_mean

    def predict(self, x_obs: ArrayF) -> tuple[ArrayF, float]:
        s_obs = self.encode_obs(x_obs)
        s_tgt = self.W @ s_obs + self.b
        y = self.decode_tgt(s_tgt)
        z = (x_obs - self.obs_mean) / (self.obs_scale + 1e-9)
        recon = self.obs_components.T @ s_obs
        resid = float(np.linalg.norm(z - recon) / np.sqrt(z.size))
        return y, resid

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "version": self.version,
            "n_train": self.n_train,
            "obs_names": list(self.obs_names),
            "target_names": list(self.target_names),
            "grid_sizes": self.grid_sizes,
            "obs_mean": self.obs_mean.tolist(),
            "obs_scale": self.obs_scale.tolist(),
            "obs_components": self.obs_components.tolist(),
            "W": self.W.tolist(),
            "b": self.b.tolist(),
            "tgt_mean": self.tgt_mean.tolist(),
            "tgt_scale": self.tgt_scale.tolist(),
            "tgt_components": self.tgt_components.tolist(),
        }
        if self.event_W is not None and self.event_b is not None:
            d["event_W"] = self.event_W.tolist()
            d["event_b"] = self.event_b.tolist()
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "HighOrderPCR":
        return cls(
            obs_mean=np.asarray(d["obs_mean"], dtype=np.float64),
            obs_scale=np.asarray(d["obs_scale"], dtype=np.float64),
            obs_components=np.asarray(d["obs_components"], dtype=np.float64),
            W=np.asarray(d["W"], dtype=np.float64),
            b=np.asarray(d["b"], dtype=np.float64),
            tgt_mean=np.asarray(d["tgt_mean"], dtype=np.float64),
            tgt_scale=np.asarray(d["tgt_scale"], dtype=np.float64),
            tgt_components=np.asarray(d["tgt_components"], dtype=np.float64),
            obs_names=tuple(d["obs_names"]),
            target_names=tuple(d["target_names"]),
            grid_sizes={k: int(v) for k, v in d["grid_sizes"].items()},
            version=str(d.get("version", "high-order-pcr-v2")),
            n_train=int(d.get("n_train", 0)),
            event_W=(
                np.asarray(d["event_W"], dtype=np.float64) if "event_W" in d else None
            ),
            event_b=(
                np.asarray(d["event_b"], dtype=np.float64) if "event_b" in d else None
            ),
        )


def _pca_fit(X: ArrayF, k: int) -> tuple[ArrayF, ArrayF, ArrayF]:
    mean = np.median(X, axis=0)
    scale = np.median(np.abs(X - mean), axis=0) * 1.4826
    scale = np.maximum(scale, 1e-6)
    Z = (X - mean) / scale
    _, s, vt = np.linalg.svd(Z, full_matrices=False)
    kk = int(min(k, vt.shape[0], max(1, X.shape[0] - 1)))
    return mean, scale, vt[:kk]


def _obs_matrix(gyro: ArrayF, quats: ArrayF, dt: float, address_idx: int, channel_kind: str) -> ArrayF:
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
    # Channels: omega,gx,gy,gz,twist_rate,plane_rate,twist,swing
    gx = mat[:, 1]
    gz = mat[:, 3]
    twist = mat[:, 6]
    # Integrated rates over downswing ≈ net FE / face change
    d_gx = float(np.trapezoid(gx[g0 : g0 + g1])) if hasattr(np, "trapezoid") else float(np.trapz(gx[g0 : g0 + g1]))
    d_gz = float(np.trapezoid(gz[g0 : g0 + g1])) if hasattr(np, "trapezoid") else float(np.trapz(gz[g0 : g0 + g1]))
    tw_imp = float(twist[g0 + g1 - 1] - twist[0])
    return np.concatenate([s_obs, np.array([d_gx, d_gz, tw_imp], dtype=np.float64)])


def fit_high_order_pcr(
    obs_waves: list[ArrayF],
    tgt_waves: list[ArrayF],
    *,
    event_fe: ArrayF | None = None,
    event_face: ArrayF | None = None,
    obs_names: tuple[str, ...] = OBS_NAMES,
    target_names: tuple[str, ...] = TARGET_NAMES,
    grid_sizes: dict[str, int] | None = None,
    k_obs: int = 12,
    k_tgt: int = 10,
    version: str = "high-order-pcr-v2",
) -> HighOrderPCR:
    X = np.stack([np.asarray(w, dtype=np.float64).reshape(-1) for w in obs_waves])
    Y = np.stack([np.asarray(w, dtype=np.float64).reshape(-1) for w in tgt_waves])
    om, os, oc = _pca_fit(X, k_obs)
    tm, ts, tc = _pca_fit(Y, k_tgt)
    Zx = (X - om) / os
    Zy = (Y - tm) / ts
    Sx = Zx @ oc.T
    Sy = Zy @ tc.T
    kx = Sx.shape[1]
    A = Sx.T @ Sx + 1e-3 * np.eye(kx)
    W = np.linalg.solve(A, Sx.T @ Sy).T
    b = Sy.mean(axis=0) - W @ Sx.mean(axis=0)

    event_W = None
    event_b = None
    grid = dict(grid_sizes or _DEFAULT_GRID)
    if event_fe is not None and event_face is not None:
        feats = []
        for i in range(X.shape[0]):
            feats.append(_event_features(X[i], Sx[i], grid, len(obs_names)))
        F = np.stack(feats)
        Yev = np.column_stack([event_fe, event_face])
        # Ridge on event features
        d = F.shape[1]
        We = np.linalg.solve(F.T @ F + 1e-2 * np.eye(d), F.T @ Yev).T  # (2, d)
        be = Yev.mean(axis=0) - We @ F.mean(axis=0)
        event_W, event_b = We, be

    return HighOrderPCR(
        obs_mean=om,
        obs_scale=os,
        obs_components=oc,
        W=W,
        b=b,
        tgt_mean=tm,
        tgt_scale=ts,
        tgt_components=tc,
        obs_names=obs_names,
        target_names=target_names,
        grid_sizes=grid,
        version=version,
        n_train=int(X.shape[0]),
        event_W=event_W,
        event_b=event_b,
    )


def build_default_high_order_model(
    n_swings: int = 48,
    seed: int = 0,
    path: Path | None = None,
) -> HighOrderPCR:
    """Fit PCR from multibody GT (coupled IMU) and persist JSON weights."""
    from golfmate_algo.ahrs import init as ahrs_init
    from golfmate_algo.ahrs.suite import GatedAdaptive
    from golfmate_algo.synth.multibody import SwingConfig, build_swing, casting_swing

    rng = np.random.default_rng(seed)
    grid = dict(_DEFAULT_GRID)
    obs_w: list[ArrayF] = []
    tgt_w: list[ArrayF] = []
    event_fe: list[float] = []
    event_face: list[float] = []
    for i in range(n_swings):
        cfg = SwingConfig(
            plane_tilt_deg=float(rng.uniform(45.0, 62.0)),
            backswing_s=float(rng.uniform(0.65, 0.95)),
            downswing_s=float(rng.uniform(0.20, 0.32)),
            center_sway_amp_m=float(rng.uniform(0.0, 0.04)),
            mount_segment=2 if i % 5 else 3,
            wrist_fe_top_deg=float(rng.uniform(-28.0, -8.0)),
            wrist_fe_impact_deg=float(rng.uniform(-5.0, 28.0)),
            clubface_open_impact_deg=float(rng.uniform(-14.0, 14.0)),
            clubface_open_top_deg=float(rng.uniform(0.0, 15.0)),
        )
        truth = casting_swing(cfg) if i % 5 == 0 else build_swing(cfg)
        ho = truth.high_order_truth()
        # Coupled IMU: FE/face rates are observable distal DoFs.
        pkt = truth.to_imu_packet(couple_high_order=True)
        phases = truth.phases()
        dt = 1.0 / pkt.frame.fs_hz
        q0, _, _ = ahrs_init.estimate_address_orientation(
            pkt.gyro, pkt.accel, pkt.frame.fs_hz
        )
        quats, _ = GatedAdaptive(use_signed_log_tilt=True).run(
            pkt.gyro, pkt.accel, dt, q0=q0
        )
        obs_mat = _obs_matrix(
            pkt.gyro, quats, dt, phases.address_idx, channel_kind="unknown_segment"
        )
        tgt_mat = np.column_stack(
            [np.asarray(ho[name], dtype=np.float64) for name in TARGET_NAMES]
        )
        obs_n = phase_normalize(
            truth.t, obs_mat, phases, channel_names=OBS_NAMES, grid_sizes=grid
        )
        tgt_n = phase_normalize(
            truth.t, tgt_mat, phases, channel_names=TARGET_NAMES, grid_sizes=grid
        )
        obs_w.append(concatenate_phases(obs_n).reshape(-1))
        tgt_w.append(concatenate_phases(tgt_n).reshape(-1))
        event_fe.append(float(ho["fe_impact_rad"]))
        event_face.append(float(ho["clubface_impact_rad"]))

    model = fit_high_order_pcr(
        obs_w,
        tgt_w,
        event_fe=np.asarray(event_fe, dtype=np.float64),
        event_face=np.asarray(event_face, dtype=np.float64),
        grid_sizes=grid,
        k_obs=12,
        k_tgt=10,
    )
    out = path or _DEFAULT_WEIGHTS
    out.write_text(json.dumps(model.to_dict()), encoding="utf-8")
    return model


def load_high_order_model(path: Path | None = None) -> HighOrderPCR | None:
    p = path or _DEFAULT_WEIGHTS
    if not p.exists():
        return None
    return HighOrderPCR.from_dict(json.loads(p.read_text(encoding="utf-8")))


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


def infer_high_order(
    t: ArrayLike,
    gyro: ArrayLike,
    quats: ArrayLike,
    phases: SwingPhases,
    *,
    model: HighOrderPCR | None = None,
    channel_kind: str = "unknown_segment",
) -> HighOrderEstimate | None:
    """Run PCR inference; returns None if weights missing."""
    model = model or load_high_order_model()
    if model is None:
        return None
    t = np.asarray(t, dtype=np.float64)
    gyro = np.asarray(gyro, dtype=np.float64)
    quats = np.asarray(quats, dtype=np.float64)
    dt = float(np.median(np.diff(t))) if t.size > 1 else 0.005
    obs_mat = _obs_matrix(gyro, quats, dt, phases.address_idx, channel_kind)
    # Allow older weights with fewer channels by slicing
    n_expected = len(model.obs_names)
    if obs_mat.shape[1] < n_expected:
        return None
    if obs_mat.shape[1] > n_expected:
        # Map by name order if possible; else take first n
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
    y, resid = model.predict(x)
    if not np.isfinite(resid) or resid > 2.5:
        z = (x - model.obs_mean) / (model.obs_scale + 1e-9)
        z = np.clip(z, -6.0, 6.0)
        x_clip = z * (model.obs_scale + 1e-9) + model.obs_mean
        y, resid = model.predict(x_clip)
        resid = max(float(resid), 0.8)

    waves = _split_target_waveforms(y, model.target_names, model.grid_sizes)
    grid = model.grid_sizes

    fe_a = _sample_at_phase_frac(waves["wrist_fe_rad"], grid, "address", 0.0)
    fe_t = _sample_at_phase_frac(waves["wrist_fe_rad"], grid, "top", 0.0)
    fe_i = _sample_at_phase_frac(waves["wrist_fe_rad"], grid, "impact", 0.0)
    ru_i = _sample_at_phase_frac(waves["wrist_ru_rad"], grid, "impact", 0.0)
    ps_i = _sample_at_phase_frac(waves["forearm_ps_rad"], grid, "impact", 0.0)
    face_i = _sample_at_phase_frac(waves["clubface_rad"], grid, "impact", 0.0)
    lean_i = _sample_at_phase_frac(waves["shaft_lean_rad"], grid, "impact", 0.0)
    xf_t = _sample_at_phase_frac(waves["x_factor_rad"], grid, "top", 0.0)

    # Event-scalar refinement (impact FE / face) when available
    if model.event_W is not None and model.event_b is not None:
        s_obs = model.encode_obs(x)
        feat = _event_features(x, s_obs, grid, len(model.obs_names))
        if feat.size == model.event_W.shape[1]:
            ev = model.event_W @ feat + model.event_b
            # Blend waveform snapshot with event head (event head wins on impact)
            fe_i = float(0.35 * fe_i + 0.65 * ev[0])
            face_i = float(0.35 * face_i + 0.65 * ev[1])
            waves["wrist_fe_rad"] = waves["wrist_fe_rad"].copy()
            waves["clubface_rad"] = waves["clubface_rad"].copy()
            g0, g1 = grid["address_to_top"], grid["top_to_impact"]
            waves["wrist_fe_rad"][g0 + g1 - 1] = fe_i
            waves["clubface_rad"][g0 + g1 - 1] = face_i

    g0, g1 = grid["address_to_top"], grid["top_to_impact"]
    down_frac = np.linspace(0.0, 1.0, g1)
    ds = float(normed.phase_durations_s.get("top_to_impact", 0.25))

    def peak_to_imp(name: str) -> float:
        w = waves[name][g0 : g0 + g1]
        rate = np.gradient(w)
        i = int(np.argmax(np.abs(rate)))
        return float((1.0 - down_frac[i]) * ds)

    p_pel = peak_to_imp("pelvis_angle_rad")
    p_tor = peak_to_imp("torso_angle_rad")
    p_arm = peak_to_imp("arm_angle_rad")
    p_clb = peak_to_imp("club_angle_rad")
    order_ok = p_pel >= p_tor >= p_arm >= p_clb - 1e-6

    conf = clip_confidence(1.0 / (1.0 + 1.5 * resid))
    if resid > 1.2:
        validity = Validity.ABSTAIN
        conf = min(conf, 0.25)
    elif resid > 0.55:
        validity = Validity.DEGRADED
    else:
        validity = Validity.OK

    return HighOrderEstimate(
        wrist_fe_address_rad=fe_a,
        wrist_fe_top_rad=fe_t,
        wrist_fe_impact_rad=fe_i,
        wrist_ru_impact_rad=ru_i,
        forearm_ps_impact_rad=ps_i,
        clubface_impact_rad=face_i,
        shaft_lean_impact_rad=lean_i,
        x_factor_top_rad=xf_t,
        waveforms=waves,
        pelvis_peak_to_impact_s=p_pel,
        torso_peak_to_impact_s=p_tor,
        arm_peak_to_impact_s=p_arm,
        club_peak_to_impact_s=p_clb,
        sequence_order_ok=bool(order_ok),
        residual=resid,
        confidence=conf,
        validity=validity,
        kind=MetricKind.INFERRED,
        model_version=model.version,
        extras={
            "n_train": float(model.n_train),
            "channel_kind_code": float(hash(channel_kind) % 1000),
        },
    )
