"""Deterministic NumPy teacher/student baseline for ``edge-trajectory-v1``.

Teacher
  Resample IMU to 100 Hz → full ``analyze_swing`` → contract outputs.

Student
  Compact random-feature nonlinear distillation model from fixed-window
  summary features → contract vector. A deterministic tanh projection plus
  ridge output keeps the model Core ML-friendly without PyTorch.

Artifacts are ``.npz`` weight dumps + the JSON schema. Core ML conversion is
intentionally deferred to ``scripts/export_edge_trajectory_coreml.py`` on macOS.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from golfmate_algo.export.edge_trajectory_contract import (
    CONTRACT_VERSION,
    INPUT_CHANNELS,
    INPUT_FS_HZ,
    MAX_SAMPLES,
    OUTPUT_DIM,
    TRAJECTORY_POINTS,
    EdgeTrajectoryOutput,
    confidence_from_report,
    phases_to_norm,
    sample_trajectory_xyz,
    transition_rush_from_report,
)
from golfmate_algo.pipeline import analyze_swing
from golfmate_algo.signal.resample import resample_packet
from golfmate_algo.types import ImuPacket, SensorFrame

FEATURE_NAMES: tuple[str, ...] = (
    "duration_s",
    "gyro_mean",
    "gyro_std",
    "gyro_max",
    "accel_mean",
    "accel_std",
    "accel_max",
    "peak_omega_frac",
    "peak_accel_frac",
    "gyro_energy_q1",
    "gyro_energy_q2",
    "gyro_energy_q3",
    "gyro_energy_q4",
    "accel_energy_q1",
    "accel_energy_q2",
    "accel_energy_q3",
    "accel_energy_q4",
    "gyro_x_rms",
    "gyro_y_rms",
    "gyro_z_rms",
    "accel_x_rms",
    "accel_y_rms",
    "accel_z_rms",
    "corr_gyro_accel",
    "early_gyro_frac",
    "late_gyro_frac",
    "jerk_proxy",
    "stillness_frac",
    "n_samples_norm",
)

DEFAULT_ARTIFACT_NAME = "edge_trajectory_student_v1.npz"
_DEFAULT_ARTIFACT = Path(__file__).with_name("artifacts") / DEFAULT_ARTIFACT_NAME


@dataclass(frozen=True)
class EdgeTrajectoryStudent:
    """Compact nonlinear student: tanh random features + ridge output."""

    version: str
    feature_names: tuple[str, ...]
    feat_mean: NDArray[np.float64]
    feat_std: NDArray[np.float64]
    projection: NDArray[np.float64]  # (F, H)
    hidden_bias: NDArray[np.float64]  # (H,)
    W: NDArray[np.float64]  # (OUTPUT_DIM, H + F)
    b: NDArray[np.float64]  # (OUTPUT_DIM,)
    train_seed: int
    projection_seed: int
    n_train: int

    def predict_vector(self, packet: ImuPacket) -> NDArray[np.float64]:
        feat = extract_edge_features(packet)
        x = (feat - self.feat_mean) / self.feat_std
        hidden = np.tanh(x @ self.projection + self.hidden_bias)
        phi = np.concatenate([hidden, x])
        y = self.W @ phi + self.b
        y = y.copy()
        y[:4] = np.clip(y[:4], 0.0, 1.0)
        # Enforce monotonic phases softly.
        for i in range(1, 4):
            y[i] = max(float(y[i]), float(y[i - 1]) + 1e-3)
        y[:4] = np.clip(y[:4], 0.0, 1.0)
        y[-2] = float(np.clip(y[-2], 0.0, 1.0))
        y[-1] = float(np.clip(y[-1], 0.0, 1.0))
        return y

    def predict(self, packet: ImuPacket) -> EdgeTrajectoryOutput:
        return EdgeTrajectoryOutput.from_vector(
            self.predict_vector(packet), version=self.version
        )

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            path,
            contract_version=np.asarray(self.version),
            feature_names=np.asarray(self.feature_names),
            feat_mean=np.asarray(self.feat_mean, dtype=np.float64),
            feat_std=np.asarray(self.feat_std, dtype=np.float64),
            projection=np.asarray(self.projection, dtype=np.float64),
            hidden_bias=np.asarray(self.hidden_bias, dtype=np.float64),
            W=np.asarray(self.W, dtype=np.float64),
            b=np.asarray(self.b, dtype=np.float64),
            train_seed=np.asarray(self.train_seed, dtype=np.int64),
            projection_seed=np.asarray(self.projection_seed, dtype=np.int64),
            n_train=np.asarray(self.n_train, dtype=np.int64),
            input_fs_hz=np.asarray(INPUT_FS_HZ, dtype=np.float64),
            output_dim=np.asarray(OUTPUT_DIM, dtype=np.int64),
            trajectory_points=np.asarray(TRAJECTORY_POINTS, dtype=np.int64),
        )
        return path


def load_edge_student(path: str | Path | None = None) -> EdgeTrajectoryStudent:
    path = Path(path) if path is not None else _DEFAULT_ARTIFACT
    if not path.is_file():
        raise FileNotFoundError(
            f"edge student artifact missing: {path}. "
            "Run scripts/export_edge_trajectory_coreml.py --numpy-only"
        )
    data = np.load(path, allow_pickle=False)
    version = str(data["contract_version"])
    if version != CONTRACT_VERSION:
        raise ValueError(f"artifact contract {version!r} != {CONTRACT_VERSION!r}")
    names = tuple(str(x) for x in data["feature_names"].tolist())
    return EdgeTrajectoryStudent(
        version=version,
        feature_names=names,
        feat_mean=np.asarray(data["feat_mean"], dtype=np.float64),
        feat_std=np.asarray(data["feat_std"], dtype=np.float64),
        projection=np.asarray(data["projection"], dtype=np.float64),
        hidden_bias=np.asarray(data["hidden_bias"], dtype=np.float64),
        W=np.asarray(data["W"], dtype=np.float64),
        b=np.asarray(data["b"], dtype=np.float64),
        train_seed=int(data["train_seed"]),
        projection_seed=int(data["projection_seed"]),
        n_train=int(data["n_train"]),
    )


def resample_to_edge_input(packet: ImuPacket) -> ImuPacket:
    """Force the edge 100 Hz input contract."""
    if abs(float(packet.frame.fs_hz) - INPUT_FS_HZ) < 1e-6 and packet.t.size >= 2:
        # Still re-grid for exact spacing.
        pass
    frame = SensorFrame(
        fs_hz=INPUT_FS_HZ,
        wrist=packet.frame.wrist,
        handedness=packet.frame.handedness,
        mount_extrinsic=packet.frame.mount_extrinsic,
        device_id=packet.frame.device_id,
        is_canonical=packet.frame.is_canonical,
    )
    return resample_packet(packet.t, packet.gyro, packet.accel, INPUT_FS_HZ, frame=frame)


def window_matrix(packet: ImuPacket) -> NDArray[np.float64]:
    """Return ``(T, 6)`` gyro|accel at the packet rate (caller should resample)."""
    gyro = np.asarray(packet.gyro, dtype=np.float64).reshape(-1, 3)
    accel = np.asarray(packet.accel, dtype=np.float64).reshape(-1, 3)
    return np.concatenate([gyro, accel], axis=1)


def extract_edge_features(packet: ImuPacket) -> NDArray[np.float64]:
    """Deterministic summary features for the student (length = len(FEATURE_NAMES))."""
    edge = resample_to_edge_input(packet)
    x = window_matrix(edge)
    t = np.asarray(edge.t, dtype=np.float64)
    n = x.shape[0]
    if n < 4:
        raise ValueError("need >= 4 edge samples")
    # Truncate/pad tracking only via n_samples_norm; features use actual window.
    if n > MAX_SAMPLES:
        x = x[:MAX_SAMPLES]
        t = t[:MAX_SAMPLES]
        n = MAX_SAMPLES

    gyro = x[:, :3]
    accel = x[:, 3:]
    gmag = np.linalg.norm(gyro, axis=1)
    amag = np.linalg.norm(accel, axis=1)
    duration = float(t[-1] - t[0]) if t.size > 1 else 0.0

    def _quad_energy(sig: NDArray[np.float64]) -> NDArray[np.float64]:
        edges = np.linspace(0, sig.size, 5).astype(int)
        out = []
        for a, b in zip(edges[:-1], edges[1:]):
            seg = sig[a:b]
            out.append(float(np.mean(seg * seg)) if seg.size else 0.0)
        return np.asarray(out, dtype=np.float64)

    peak_g = int(np.argmax(gmag))
    peak_a = int(np.argmax(amag))
    g_q = _quad_energy(gmag)
    a_q = _quad_energy(amag)
    half = max(n // 2, 1)
    early = float(np.mean(gmag[:half] ** 2))
    late = float(np.mean(gmag[half:] ** 2))
    denom = early + late + 1e-12
    dg = np.diff(gmag, prepend=gmag[0])
    jerk = float(np.mean(np.abs(dg)))
    still = float(np.mean(gmag < 0.8))
    corr = float(np.corrcoef(gmag, amag)[0, 1]) if n > 3 else 0.0
    if not np.isfinite(corr):
        corr = 0.0

    feats = np.asarray(
        [
            duration,
            float(np.mean(gmag)),
            float(np.std(gmag)),
            float(np.max(gmag)),
            float(np.mean(amag)),
            float(np.std(amag)),
            float(np.max(amag)),
            peak_g / max(n - 1, 1),
            peak_a / max(n - 1, 1),
            *g_q.tolist(),
            *a_q.tolist(),
            float(np.sqrt(np.mean(gyro[:, 0] ** 2))),
            float(np.sqrt(np.mean(gyro[:, 1] ** 2))),
            float(np.sqrt(np.mean(gyro[:, 2] ** 2))),
            float(np.sqrt(np.mean(accel[:, 0] ** 2))),
            float(np.sqrt(np.mean(accel[:, 1] ** 2))),
            float(np.sqrt(np.mean(accel[:, 2] ** 2))),
            corr,
            early / denom,
            late / denom,
            jerk,
            still,
            min(n, MAX_SAMPLES) / float(MAX_SAMPLES),
        ],
        dtype=np.float64,
    )
    if feats.size != len(FEATURE_NAMES):
        raise RuntimeError("feature size mismatch")
    assert len(INPUT_CHANNELS) == 6
    return feats


def teacher_edge_output(
    packet: ImuPacket,
    *,
    impact_hint_s: float | None = None,
    compare_to_ideal: bool = False,
) -> EdgeTrajectoryOutput:
    """Teacher labels from the full Python pipeline on a 100 Hz edge grid."""
    edge = resample_to_edge_input(packet)
    report = analyze_swing(
        edge,
        impact_hint_s=impact_hint_s,
        compare_to_ideal=compare_to_ideal,
        use_crop_lite=False,
    )
    n = int(edge.t.size)
    phases_norm = phases_to_norm(report.phases, n)
    traj = sample_trajectory_xyz(
        report.positions,
        address_idx=report.phases.address_idx,
        finish_idx=report.phases.finish_idx,
        n_points=TRAJECTORY_POINTS,
    )
    return EdgeTrajectoryOutput(
        version=CONTRACT_VERSION,
        phases_norm=phases_norm,
        trajectory_xyz=traj,
        confidence=confidence_from_report(report),
        transition_rush=transition_rush_from_report(report),
    )


def fit_edge_student(
    packets: list[ImuPacket],
    *,
    seed: int = 0,
    ridge: float = 0.5,
    hidden_dim: int = 128,
    projection_seed: int = 1,
    impact_hints: list[float | None] | None = None,
) -> EdgeTrajectoryStudent:
    """Distill teacher labels into a ridge-linear student (deterministic)."""
    if len(packets) < 2:
        raise ValueError("need >= 2 packets to fit student")
    rng = np.random.default_rng(seed)
    # Shuffle with fixed seed for stability of conditioning order.
    order = rng.permutation(len(packets))
    hints = impact_hints or [None] * len(packets)
    X_list: list[NDArray[np.float64]] = []
    Y_list: list[NDArray[np.float64]] = []
    for idx in order:
        pkt = packets[int(idx)]
        X_list.append(extract_edge_features(pkt))
        Y_list.append(teacher_edge_output(pkt, impact_hint_s=hints[int(idx)]).as_vector())
    X = np.stack(X_list, axis=0)
    Y = np.stack(Y_list, axis=0)
    feat_mean = X.mean(axis=0)
    feat_std = X.std(axis=0)
    feat_std = np.where(feat_std < 1e-8, 1.0, feat_std)
    Xn = (X - feat_mean) / feat_std
    feature_rng = np.random.default_rng(projection_seed)
    projection = feature_rng.normal(
        0.0, 1.0 / np.sqrt(Xn.shape[1]), size=(Xn.shape[1], hidden_dim)
    )
    hidden_bias = feature_rng.uniform(-0.5, 0.5, size=hidden_dim)
    hidden = np.tanh(Xn @ projection + hidden_bias)
    phi = np.concatenate([hidden, Xn], axis=1)
    # Ridge output over nonlinear and identity features.
    xtx = phi.T @ phi + ridge * np.eye(phi.shape[1])
    W = np.linalg.solve(xtx, phi.T @ Y).T
    b = Y.mean(axis=0) - W @ phi.mean(axis=0)
    return EdgeTrajectoryStudent(
        version=CONTRACT_VERSION,
        feature_names=FEATURE_NAMES,
        feat_mean=feat_mean,
        feat_std=feat_std,
        projection=projection,
        hidden_bias=hidden_bias,
        W=W,
        b=b,
        train_seed=int(seed),
        projection_seed=int(projection_seed),
        n_train=len(packets),
    )


def train_default_edge_student(
    *,
    n_train: int = 512,
    seed: int = 0,
) -> EdgeTrajectoryStudent:
    """Fit on analytic synthetic swings (no external datasets required)."""
    from golfmate_algo.synth.analytic import planar_circular_swing

    rng = np.random.default_rng(seed)
    packets: list[ImuPacket] = []
    for i in range(n_train):
        casting = bool(i % 3 == 0)
        swing = planar_circular_swing(
            fs_hz=INPUT_FS_HZ,
            casting=casting,
            casting_lead_s=float(rng.uniform(0.04, 0.15)) if casting else 0.0,
            radius_m=float(rng.uniform(0.38, 0.75)),
            backswing_s=float(rng.uniform(0.60, 0.95)),
            downswing_s=float(rng.uniform(0.18, 0.35)),
            top_angle_deg=float(rng.uniform(90.0, 130.0)),
            plane_tilt_deg=float(rng.uniform(40.0, 70.0)),
            impact_shock_g=float(rng.uniform(1.5, 10.0)),
        )
        packets.append(swing.packet)
    return fit_edge_student(packets, seed=seed)


def ensure_default_artifact(
    path: str | Path | None = None,
    *,
    force: bool = False,
) -> Path:
    """Train and write the default student artifact if missing."""
    path = Path(path) if path is not None else _DEFAULT_ARTIFACT
    if path.is_file() and not force:
        return path
    student = train_default_edge_student(seed=0, n_train=512)
    return student.save(path)


def artifact_metadata(path: str | Path | None = None) -> dict[str, Any]:
    student = load_edge_student(path)
    return {
        "contract_version": student.version,
        "feature_dim": len(student.feature_names),
        "output_dim": int(student.W.shape[0]),
        "train_seed": student.train_seed,
        "projection_seed": student.projection_seed,
        "n_train": student.n_train,
        "coreml_model_present": False,
        "note": "NumPy artifact only unless Core ML export was run on macOS",
    }
