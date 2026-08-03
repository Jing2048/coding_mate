"""MultiSenseGolf (doi:10.7910/DVN/LCCLLW) adapter → ImuPacket + labels.

The public release stores per-swing HDF5 streams with Perception-Neuron-style
21-joint mocap (quaternion, angular velocity, synthetic linear accel) plus
annotation CSV impact / launch-monitor metadata. Raw wrist MEMS is not exposed;
we therefore derive a lead-wrist IMU from the mocap joint kinematics. That is
still an *external* motion distribution (real humans, not our generators),
honestly labelled ``mocap_derived_imu``.
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
from golfmate_algo.types import ImuPacket, SensorFrame, SwingPhases, WristSide

ArrayF = NDArray[np.float64]

DOI = "10.7910/DVN/LCCLLW"
DEFAULT_ROOT = Path(__file__).resolve().parents[3] / "data" / "multisense"

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
    quats_ref: ArrayF  # mocap joint orientation, body→world
    positions_ref: ArrayF  # metres, world/root-relative
    reference: dict[str, float] = field(default_factory=dict)
    split: Literal["train", "val", "holdout"] = "val"
    provenance: str = "multisense_mocap_derived_imu"


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
            pid = row["Participant Number"].replace("Sub", "").lstrip("0") or "0"
            # Sub07 -> 7
            num = "".join(ch for ch in row["Participant Number"] if ch.isdigit())
            out[str(int(num))] = row.get("Swing Handedness", "Right")
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
        # synthetic accel may be shorter — interpolate onto quaternion timeline
        a_t = np.asarray(
            h["pns-joint-synthetic-accel/acceleration-values/time_s"], dtype=np.float64
        ).reshape(-1)
        a = np.asarray(
            h["pns-joint-synthetic-accel/acceleration-values/data"], dtype=np.float64
        ).reshape(-1, 21, 3)

    # PN quaternions are typically [w,x,y,z]; angular velocity in deg/s.
    quat = q[:, j, :]
    for i in range(1, quat.shape[0]):
        quat[i] = so3.ensure_quat_hemisphere(quat[i], quat[i - 1])
    gyro = np.deg2rad(w[:, j, :])
    pos_m = pos[:, j, :] / 100.0
    # Interp free accel onto t
    a_j = a[:, j, :]
    a_world = np.zeros((t.shape[0], 3), dtype=np.float64)
    for k in range(3):
        a_world[:, k] = np.interp(t, a_t, a_j[:, k], left=a_j[0, k], right=a_j[-1, k])
    return {"t": t, "quat": quat, "gyro": gyro, "pos": pos_m, "accel_world": a_world}


def _specific_force_body(quat: ArrayF, accel_world: ArrayF) -> ArrayF:
    """Convert world linear acceleration to body specific force."""
    n = quat.shape[0]
    out = np.zeros((n, 3), dtype=np.float64)
    for i in range(n):
        R = so3.quat_to_rotmat(quat[i])
        out[i] = R.T @ (accel_world[i] - so3.G_WORLD)
    return out


def _nearest_idx(t: ArrayF, t0: float) -> int:
    return int(np.argmin(np.abs(t - t0)))


def _infer_phases(t: ArrayF, gyro: ArrayF, impact_idx: int) -> SwingPhases:
    """Coarse phases from rate profile anchored at annotated impact."""
    speed = np.linalg.norm(gyro, axis=1)
    # address: quiet early window
    early = speed[: max(5, impact_idx // 3)]
    address_idx = int(np.argmin(early)) if early.size else 0
    # top: minimum rate in the half before impact (reversal)
    lo, hi = max(address_idx + 1, impact_idx // 4), max(impact_idx, impact_idx)
    window = speed[lo:hi] if hi > lo else speed[:impact_idx]
    top_idx = lo + int(np.argmin(window)) if window.size else max(0, impact_idx - 1)
    finish_idx = min(len(t) - 1, impact_idx + max(5, (len(t) - impact_idx) // 2))
    # ensure order
    top_idx = min(max(top_idx, address_idx + 1), impact_idx - 1) if impact_idx > address_idx + 1 else address_idx
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
) -> ExternalSwingCase:
    joint = _lead_joint(handedness)
    raw = _read_hdf5_joint(path, joint)
    t = raw["t"]
    quat = raw["quat"]
    gyro = raw["gyro"]
    accel = _specific_force_body(quat, raw["accel_world"])
    # Relative time for ImuPacket
    t0 = float(t[0])
    t_rel = t - t0
    dt = float(np.median(np.diff(t_rel))) if t_rel.size > 1 else 0.01
    fs = 1.0 / max(dt, 1e-4)

    impact_abs = annotation.get("FPV Impact Timestamp (s)", "")
    if impact_abs in ("", "-", None):
        impact_abs = annotation.get("Front-View Impact Timestamp (s)", "")
    if impact_abs in ("", "-", None):
        impact_idx = int(np.argmax(np.linalg.norm(gyro, axis=1)))
        impact_time = float(t[impact_idx])
    else:
        impact_time = float(impact_abs)
        impact_idx = _nearest_idx(t, impact_time)

    phases = _infer_phases(t_rel, gyro, impact_idx)
    # Override impact with annotation-anchored index
    phases = SwingPhases(
        address_idx=phases.address_idx,
        top_idx=phases.top_idx,
        impact_idx=impact_idx,
        finish_idx=phases.finish_idx,
    )

    packet = ImuPacket(
        frame=SensorFrame(fs_hz=fs, wrist=WristSide.LEAD, device_id=f"multisense/{subject_id}"),
        t=t_rel,
        gyro=gyro,
        accel=accel,
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

    return ExternalSwingCase(
        packet=packet,
        subject_id=subject_id,
        swing_number=int(annotation.get("Swing Number", "0")),
        impact_time_s=impact_time,
        impact_idx=impact_idx,
        phases=phases,
        quats_ref=quat,
        positions_ref=raw["pos"],
        reference=ref,
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
            swing_dir = hdf5.parent.name  # Swing01
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
        # Limit swings
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
