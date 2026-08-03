"""MultiSenseGolf (doi:10.7910/DVN/LCCLLW) adapter → ImuPacket + labels.

The public release stores per-swing HDF5 streams with Perception-Neuron-style
21-joint mocap (quaternion, angular velocity, synthetic linear accel) plus
annotation CSV impact / launch-monitor metadata. Raw wrist MEMS is not exposed;
we therefore derive a lead-wrist IMU from the mocap joint kinematics. That is
still an *external* motion distribution (real humans, not our generators),
honestly labelled ``mocap_derived_imu``.

Coordinate / unit contract (verified against local Sub07 extracts)
-----------------------------------------------------------------
* PN quaternions are scalar-first ``[w,x,y,z]``.
* Stored angular velocity is already **rad/s** (NOT deg/s). Treating it as
  deg/s and calling ``np.deg2rad`` shrinks rates by ~57× and collapses AHRS.
* PN world frame is **Y-up**; Golf Mate algorithms use **Z-up** ``G=[0,0,-g]``.
  We apply one fixed proper rotation to positions, orientations, and world
  accelerations.
* Angular rate fed to the pipeline is the **body-frame** rate from the SO(3)
  logarithm of successive joint quaternions — consistent with the orientation
  reference and immune to the ambiguous PN global/body storage convention.
* Timestamps are irregular; we dedupe and resample onto a fixed grid so the
  strapdown integrator sees a true constant ``dt``.
"""

from __future__ import annotations

import csv
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Literal

import numpy as np
from numpy.typing import NDArray

from golfmate_algo.math import so3
from golfmate_algo.signal.resample import dedupe_time_series, resample_packet
from golfmate_algo.types import Handedness, ImuPacket, SensorFrame, SwingPhases, WristSide

ArrayF = NDArray[np.float64]

DOI = "10.7910/DVN/LCCLLW"
DEFAULT_ROOT = Path(__file__).resolve().parents[3] / "data" / "multisense"

# Y-up (x,y,z) → Z-up (x',y',z') = (x, -z, y); maps +Y to +Z.
R_YUP_TO_ZUP = np.array(
    [[1.0, 0.0, 0.0], [0.0, 0.0, -1.0], [0.0, 1.0, 0.0]], dtype=np.float64
)

# Perception Neuron 21-bone order used by the release.
PNS_JOINTS: tuple[str, ...] = (
    "Hips",
    "RightUpLeg",
    "RightLeg",
    "RightFoot",
    "LeftUpLeg",
    "LeftLeg",
    "LeftFoot",
    "Spine",
    "Spine1",
    "Spine2",
    "Spine3",
    "Neck",
    "Head",
    "RightShoulder",
    "RightArm",
    "RightForeArm",
    "RightHand",
    "LeftShoulder",
    "LeftArm",
    "LeftForeArm",
    "LeftHand",
)

LEAD_JOINT_RIGHT_HANDED = "LeftHand"
LEAD_JOINT_LEFT_HANDED = "RightHand"


@dataclass
class ExternalSwingCase:
    packet: ImuPacket
    subject_id: str
    swing_number: int
    impact_time_s: float  # absolute unix-ish timestamp from annotations
    impact_idx: int
    phases: SwingPhases | None
    quats_ref: ArrayF  # mocap joint orientation, body→world (Z-up)
    positions_ref: ArrayF  # metres, world/root-relative (Z-up)
    reference: dict[str, float] = field(default_factory=dict)
    split: Literal["train", "val", "holdout"] = "val"
    provenance: str = "multisense_mocap_derived_imu"
    adapter_meta: dict[str, float] = field(default_factory=dict)


def dataset_status(root: Path | None = None) -> dict[str, Any]:
    root = root or DEFAULT_ROOT
    ann = root / "docs" / "Annotation Data.csv"
    subjects = sorted(p for p in root.glob("Sub*") if p.is_dir())
    n_hdf5 = sum(1 for _ in root.glob("Sub*/Swing*/*stream_data.hdf5"))
    return {
        "doi": DOI,
        "root": str(root),
        "annotations_present": ann.exists(),
        "subjects_extracted": [p.name for p in subjects],
        "n_hdf5_swings": n_hdf5,
        "ready": ann.exists() and n_hdf5 > 0,
    }


def _joint_index(name: str) -> int:
    return PNS_JOINTS.index(name)


def _lead_joint(handedness: str) -> str:
    h = handedness.strip().lower()
    if h.startswith("left"):
        return LEAD_JOINT_LEFT_HANDED
    return LEAD_JOINT_RIGHT_HANDED


def _load_annotations(root: Path) -> list[dict[str, str]]:
    path = root / "docs" / "Annotation Data.csv"
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _load_handedness(root: Path) -> dict[str, str]:
    path = root / "docs" / "Participant Metadata.csv"
    out: dict[str, str] = {}
    if not path.exists():
        return out
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            num = "".join(ch for ch in row["Participant Number"] if ch.isdigit())
            out[str(int(num))] = row.get("Swing Handedness", "Right")
    return out


def _body_omega_from_quats(quat: ArrayF, t: ArrayF) -> ArrayF:
    """Body angular rate via SO(3) log of successive orientations."""
    n = quat.shape[0]
    out = np.zeros((n, 3), dtype=np.float64)
    for i in range(n - 1):
        dt = float(t[i + 1] - t[i])
        if dt <= 1e-9:
            out[i] = out[i - 1] if i else 0.0
            continue
        dq = so3.quat_multiply(so3.quat_conjugate(quat[i]), quat[i + 1])
        v = dq[1:]
        nv = float(np.linalg.norm(v))
        if nv < 1e-12:
            out[i] = 0.0
            continue
        ang = 2.0 * float(np.arctan2(nv, float(dq[0])))
        if ang > np.pi:
            ang -= 2.0 * np.pi
        if ang < -np.pi:
            ang += 2.0 * np.pi
        out[i] = (ang / dt) * (v / nv)
    if n >= 2:
        out[-1] = out[-2]
    return out


def _transform_quat_yup_to_zup(quat: ArrayF) -> ArrayF:
    out = np.zeros_like(quat)
    for i in range(quat.shape[0]):
        R = R_YUP_TO_ZUP @ so3.quat_to_rotmat(quat[i])
        out[i] = so3.rotmat_to_quat(R)
        if i:
            out[i] = so3.ensure_quat_hemisphere(out[i], out[i - 1])
    return out


def _slerp_quats(t_src: ArrayF, q_src: ArrayF, t_dst: ArrayF) -> ArrayF:
    """Piecewise SLERP of a quaternion track onto ``t_dst``."""
    from golfmate_algo.ahrs.suite import quat_slerp

    n = t_dst.shape[0]
    out = np.zeros((n, 4), dtype=np.float64)
    for i, ti in enumerate(t_dst):
        j = int(np.searchsorted(t_src, ti, side="right") - 1)
        j = int(np.clip(j, 0, t_src.shape[0] - 2))
        dt = float(t_src[j + 1] - t_src[j])
        alpha = 0.0 if dt <= 1e-12 else float(np.clip((ti - t_src[j]) / dt, 0.0, 1.0))
        out[i] = quat_slerp(q_src[j], q_src[j + 1], alpha)
        if i:
            out[i] = so3.ensure_quat_hemisphere(out[i], out[i - 1])
    return out


def _read_hdf5_joint(path: Path, joint: str) -> dict[str, ArrayF]:
    import h5py

    j = _joint_index(joint)
    with h5py.File(path, "r") as h:
        t = np.asarray(h["pns-joint-quaternion/angle-values/time_s"], dtype=np.float64).reshape(-1)
        q = np.asarray(h["pns-joint-quaternion/angle-values/data"], dtype=np.float64).reshape(-1, 21, 4)
        w = np.asarray(
            h["pns-joint-angular-velocity/velocity-values/data"], dtype=np.float64
        ).reshape(-1, 21, 3)
        pos = np.asarray(
            h["pns-joint-root-relative-position/cm-values/data"], dtype=np.float64
        ).reshape(-1, 21, 3)
        a_t = np.asarray(
            h["pns-joint-synthetic-accel/acceleration-values/time_s"], dtype=np.float64
        ).reshape(-1)
        a = np.asarray(
            h["pns-joint-synthetic-accel/acceleration-values/data"], dtype=np.float64
        ).reshape(-1, 21, 3)

    quat = q[:, j, :].copy()
    for i in range(1, quat.shape[0]):
        quat[i] = so3.ensure_quat_hemisphere(quat[i], quat[i - 1])
    # Already rad/s — do NOT deg2rad.
    gyro_stored = w[:, j, :].astype(np.float64, copy=True)
    pos_m = pos[:, j, :] / 100.0
    a_j = a[:, j, :]
    a_world = np.zeros((t.shape[0], 3), dtype=np.float64)
    for k in range(3):
        a_world[:, k] = np.interp(t, a_t, a_j[:, k], left=a_j[0, k], right=a_j[-1, k])
    return {
        "t": t,
        "quat": quat,
        "gyro_stored": gyro_stored,
        "pos": pos_m,
        "accel_world": a_world,
    }


def _specific_force_body(quat: ArrayF, accel_world_lin: ArrayF) -> ArrayF:
    """World linear acceleration → body specific force (Z-up gravity)."""
    n = quat.shape[0]
    out = np.zeros((n, 3), dtype=np.float64)
    for i in range(n):
        R = so3.quat_to_rotmat(quat[i])
        # Rest: a_lin≈0 → f = -G = [0,0,g]; body f_b = R.T @ f.
        out[i] = R.T @ (accel_world_lin[i] - so3.G_WORLD)
    return out


def _nearest_idx(t: ArrayF, t0: float) -> int:
    return int(np.argmin(np.abs(t - t0)))


def _infer_phases(t: ArrayF, gyro: ArrayF, impact_idx: int) -> SwingPhases:
    """Coarse phases from rate profile anchored at annotated impact."""
    speed = np.linalg.norm(gyro, axis=1)
    early = speed[: max(5, impact_idx // 3)]
    address_idx = int(np.argmin(early)) if early.size else 0
    lo, hi = max(address_idx + 1, impact_idx // 4), max(impact_idx, impact_idx)
    window = speed[lo:hi] if hi > lo else speed[:impact_idx]
    top_idx = lo + int(np.argmin(window)) if window.size else max(0, impact_idx - 1)
    finish_idx = min(len(t) - 1, impact_idx + max(5, (len(t) - impact_idx) // 2))
    top_idx = (
        min(max(top_idx, address_idx + 1), impact_idx - 1)
        if impact_idx > address_idx + 1
        else address_idx
    )
    return SwingPhases(
        address_idx=address_idx,
        top_idx=top_idx,
        impact_idx=impact_idx,
        finish_idx=finish_idx,
    )


def load_swing_hdf5(
    path: Path,
    *,
    annotation: dict[str, str],
    handedness: str = "Right",
    subject_id: str = "unknown",
    target_fs_hz: float | None = None,
) -> ExternalSwingCase:
    joint = _lead_joint(handedness)
    raw = _read_hdf5_joint(path, joint)
    t = raw["t"]
    quat_y = raw["quat"]
    pos_y = raw["pos"]
    accel_y = raw["accel_world"]

    # --- World frame: Y-up → Z-up
    quat = _transform_quat_yup_to_zup(quat_y)
    pos = (R_YUP_TO_ZUP @ pos_y.T).T
    accel_lin = (R_YUP_TO_ZUP @ accel_y.T).T

    # Relative time + dedupe (keep world-frame pose tracks aligned)
    t0 = float(t[0])
    t_rel = t - t0
    t_rel, quat, pos, accel_lin = dedupe_time_series(t_rel, quat, pos, accel_lin)

    dts = np.diff(t_rel)
    dts = dts[dts > 0]
    med_dt = float(np.median(dts)) if dts.size else 0.01
    med_fs = 1.0 / max(med_dt, 1e-4)
    fs = float(target_fs_hz) if target_fs_hz is not None else float(np.clip(round(med_fs), 50.0, 120.0))

    # Impact on original (deduped) timeline
    impact_abs = annotation.get("FPV Impact Timestamp (s)", "")
    if impact_abs in ("", "-", None):
        impact_abs = annotation.get("Front-View Impact Timestamp (s)", "")
    if impact_abs in ("", "-", None):
        # Temporary rate from irregular quat log only for fallback indexing
        gyro_tmp = _body_omega_from_quats(quat, t_rel)
        impact_idx_raw = int(np.argmax(np.linalg.norm(gyro_tmp, axis=1)))
        impact_time = float(t_rel[impact_idx_raw] + t0)
        impact_rel = float(t_rel[impact_idx_raw])
    else:
        impact_time = float(impact_abs)
        impact_rel = impact_time - t0

    # Fixed grid first, THEN body rate from SLERP'd quats (avoids aliasing
    # high-ω peaks that linear gyro interpolation would smear).
    t_end = float(t_rel[-1])
    n_grid = max(2, int(np.floor(t_end * fs)) + 1)
    tg = np.arange(n_grid, dtype=np.float64) / fs
    tg = tg[tg <= t_end + 0.5 / fs]
    if tg.size < 2:
        tg = np.array([0.0, t_end], dtype=np.float64)
    quats_ref = _slerp_quats(t_rel, quat, tg)
    positions_ref = np.column_stack(
        [np.interp(tg, t_rel, pos[:, k]) for k in range(3)]
    )
    accel_lin_g = np.column_stack(
        [np.interp(tg, t_rel, accel_lin[:, k]) for k in range(3)]
    )
    gyro = _body_omega_from_quats(quats_ref, tg)
    accel = _specific_force_body(quats_ref, accel_lin_g)

    packet = ImuPacket(
        frame=SensorFrame(
            fs_hz=fs,
            wrist=WristSide.LEAD,
            handedness=(
                Handedness.LEFT
                if str(handedness).strip().lower().startswith("left")
                else Handedness.RIGHT
            ),
            device_id=f"multisense/{subject_id}",
            is_canonical=False,
        ),
        t=tg,
        gyro=gyro,
        accel=accel,
    )
    impact_idx = _nearest_idx(tg, impact_rel)
    phases = _infer_phases(tg, packet.gyro, impact_idx)
    phases = SwingPhases(
        address_idx=phases.address_idx,
        top_idx=phases.top_idx,
        impact_idx=impact_idx,
        finish_idx=phases.finish_idx,
    )

    ref: dict[str, float] = {}
    for key, dest in (
        ("Ball Speed (m/s)", "ball_speed_m_s"),
        ("Club Speed (m/s)", "club_speed_m_s"),
        ("Carry Distance (m)", "carry_m"),
        ("Total Distance (m)", "total_m"),
    ):
        try:
            ref[dest] = float(annotation.get(key, "nan"))
        except ValueError:
            ref[dest] = float("nan")

    peak_gyro = float(np.max(np.linalg.norm(packet.gyro, axis=1)))
    rest_a = float(np.mean(np.linalg.norm(packet.accel[: max(3, int(0.05 * fs))], axis=1)))
    return ExternalSwingCase(
        packet=packet,
        subject_id=subject_id,
        swing_number=int(annotation.get("Swing Number", "0")),
        impact_time_s=impact_time,
        impact_idx=impact_idx,
        phases=phases,
        quats_ref=quats_ref,
        positions_ref=positions_ref,
        reference=ref,
        adapter_meta={
            "fs_hz": fs,
            "peak_gyro_rad_s": peak_gyro,
            "rest_accel_norm": rest_a,
            "yup_to_zup": 1.0,
            "gyro_from_quat_log": 1.0,
            "no_deg2rad": 1.0,
        },
    )


def iter_local_swings(
    root: Path | None = None,
    *,
    max_swings: int | None = 40,
    subjects: list[str] | None = None,
) -> Iterator[ExternalSwingCase]:
    """Yield swings from extracted ``SubXX/SwingYY/*.hdf5`` trees."""
    root = root or DEFAULT_ROOT
    status = dataset_status(root)
    if not status["ready"]:
        return
    anns = _load_annotations(root)
    hands = _load_handedness(root)
    ann_by: dict[tuple[str, int], dict[str, str]] = {}
    for row in anns:
        ann_by[(row["Participant Number"], int(row["Swing Number"]))] = row

    count = 0
    sub_dirs = sorted(p for p in root.glob("Sub*") if p.is_dir())
    if subjects:
        want = {s if s.startswith("Sub") else f"Sub{int(s):02d}" for s in subjects}
        sub_dirs = [p for p in sub_dirs if p.name in want]

    for sub in sub_dirs:
        num = str(int("".join(ch for ch in sub.name if ch.isdigit()) or "0"))
        handed = hands.get(num, "Right")
        for hdf5 in sorted(sub.glob("Swing*/*stream_data.hdf5")):
            swing_dir = hdf5.parent.name
            swing_n = int("".join(ch for ch in swing_dir if ch.isdigit()) or "0")
            ann = ann_by.get((num, swing_n))
            if ann is None:
                continue
            try:
                yield load_swing_hdf5(
                    hdf5, annotation=ann, handedness=handed, subject_id=sub.name
                )
            except Exception:
                continue
            count += 1
            if max_swings is not None and count >= max_swings:
                return


def extract_subject_imu(
    zip_path: Path,
    dest: Path,
    *,
    max_swings: int = 20,
) -> list[Path]:
    """Extract only HDF5 streams (+ timestamps) from a subject zip."""
    dest.mkdir(parents=True, exist_ok=True)
    extracted: list[Path] = []
    with zipfile.ZipFile(zip_path, "r") as zf:
        names = [
            n
            for n in zf.namelist()
            if n.endswith("stream_data.hdf5") or n.endswith("Timestamps.csv")
        ]
        swing_ids = sorted({n.split("/")[0] for n in names if n.startswith("Swing")})
        keep = set(swing_ids[:max_swings])
        for n in names:
            swing = n.split("/")[0]
            if swing not in keep:
                continue
            target = dest / n
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(n) as src, target.open("wb") as out:
                out.write(src.read())
            if n.endswith(".hdf5"):
                extracted.append(target)
    return extracted
