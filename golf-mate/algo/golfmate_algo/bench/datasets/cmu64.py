"""CMU Graphics Lab Subject 64 (golf) → wrist ImuPacket + orientation GT.

Commercial-friendly mocap (may ship in products; do not resell the mocap).
We synthesise a lead-wrist 6-axis IMU from ASF/AMC forward kinematics — same
honesty class as MultiSenseGolf (real human kinematics, synthetic IMU).

URL: http://mocap.cs.cmu.edu/search.php?subjectnumber=64
"""

from __future__ import annotations

import re
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

import numpy as np
from numpy.typing import NDArray

from golfmate_algo.math import so3
from golfmate_algo.types import Handedness, ImuPacket, SensorFrame, SwingPhases, WristSide

ArrayF = NDArray[np.float64]

DOI_NOTE = "cmu-mocap-subject-64"
DEFAULT_ROOT = Path(__file__).resolve().parents[3] / "data" / "cmu64"
BASE_URL = "http://mocap.cs.cmu.edu/subjects/64"
FS_HZ = 120.0
# Lead wrist for a right-handed golfer ≈ left hand chain in CMU naming.
WRIST_BONE = "lwrist"
HAND_BONE = "lhand"


@dataclass
class Bone:
    name: str
    direction: ArrayF
    length: float
    axis: ArrayF  # Euler XYZ deg of local C
    dof: list[str]
    parent: str | None = None
    children: list[str] = field(default_factory=list)


@dataclass
class CmuSwingCase:
    packet: ImuPacket
    trial: str
    quats_ref: ArrayF
    positions_ref: ArrayF
    phases: SwingPhases
    provenance: str = "cmu64_mocap_synth_imu"
    adapter_meta: dict[str, float] = field(default_factory=dict)


def _rot_x(a: float) -> ArrayF:
    c, s = np.cos(a), np.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]], dtype=np.float64)


def _rot_y(a: float) -> ArrayF:
    c, s = np.cos(a), np.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]], dtype=np.float64)


def _rot_z(a: float) -> ArrayF:
    c, s = np.cos(a), np.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]], dtype=np.float64)


def _euler_xyz_deg(rx: float, ry: float, rz: float) -> ArrayF:
    return _rot_x(np.deg2rad(rx)) @ _rot_y(np.deg2rad(ry)) @ _rot_z(np.deg2rad(rz))


def parse_asf(text: str) -> dict[str, Bone]:
    """Parse CMU ASF into a bone dict with hierarchy links."""
    bones: dict[str, Bone] = {}
    # Root synthetic bone
    bones["root"] = Bone(
        name="root",
        direction=np.array([0.0, 0.0, 0.0]),
        length=0.0,
        axis=np.zeros(3),
        dof=["tx", "ty", "tz", "rx", "ry", "rz"],
    )
    # Bone blocks
    for block in re.findall(r"begin(.*?)end", text, flags=re.S | re.I):
        name_m = re.search(r"name\s+(\w+)", block)
        if not name_m:
            continue
        name = name_m.group(1)
        dir_m = re.search(r"direction\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)", block)
        len_m = re.search(r"length\s+([-\d.eE+]+)", block)
        ax_m = re.search(
            r"axis\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)", block
        )
        dof_m = re.search(r"dof\s+([^\n]+)", block)
        direction = (
            np.array([float(dir_m.group(i)) for i in range(1, 4)], dtype=np.float64)
            if dir_m
            else np.zeros(3)
        )
        length = float(len_m.group(1)) if len_m else 0.0
        axis = (
            np.array([float(ax_m.group(i)) for i in range(1, 4)], dtype=np.float64)
            if ax_m
            else np.zeros(3)
        )
        dof = dof_m.group(1).split() if dof_m else []
        bones[name] = Bone(name=name, direction=direction, length=length, axis=axis, dof=dof)

    hier = re.search(r":hierarchy\s+begin(.*?)end", text, flags=re.S | re.I)
    if hier:
        for line in hier.group(1).strip().splitlines():
            parts = line.split()
            if len(parts) < 2:
                continue
            parent, kids = parts[0], parts[1:]
            if parent not in bones:
                continue
            bones[parent].children = kids
            for k in kids:
                if k in bones:
                    bones[k].parent = parent
    return bones


def parse_amc(text: str) -> list[dict[str, ArrayF]]:
    """Parse AMC frames → list of {bone: channel_values}."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]
    # skip headers until first integer frame
    i = 0
    while i < len(lines) and not lines[i][0].isdigit():
        i += 1
    frames: list[dict[str, ArrayF]] = []
    cur: dict[str, ArrayF] | None = None
    while i < len(lines):
        ln = lines[i]
        if ln[0].isdigit() and " " not in ln:
            if cur is not None:
                frames.append(cur)
            cur = {}
            i += 1
            continue
        parts = ln.split()
        name, vals = parts[0], np.array([float(x) for x in parts[1:]], dtype=np.float64)
        if cur is None:
            cur = {}
        cur[name] = vals
        i += 1
    if cur is not None:
        frames.append(cur)
    return frames


def _bone_C(bone: Bone) -> ArrayF:
    return _euler_xyz_deg(float(bone.axis[0]), float(bone.axis[1]), float(bone.axis[2]))


def _channels_to_R(bone: Bone, vals: ArrayF) -> ArrayF:
    """Map dof channel values (deg / cm) to a local rotation (ignore translations)."""
    R = np.eye(3)
    if bone.name == "root":
        # root: tx ty tz rx ry rz
        if vals.size >= 6:
            R = _euler_xyz_deg(float(vals[3]), float(vals[4]), float(vals[5]))
        return R
    idx = 0
    rx = ry = rz = 0.0
    for d in bone.dof:
        if idx >= vals.size:
            break
        v = float(vals[idx])
        idx += 1
        if d == "rx":
            rx = v
        elif d == "ry":
            ry = v
        elif d == "rz":
            rz = v
    if bone.dof:
        C = _bone_C(bone)
        M = _euler_xyz_deg(rx, ry, rz)
        R = C @ M @ C.T
    return R


def forward_kinematics(
    bones: dict[str, Bone],
    frame: dict[str, ArrayF],
    *,
    length_scale_m: float = 0.0254 * 0.45,  # ASF length unit → metres (approx)
) -> tuple[dict[str, ArrayF], dict[str, ArrayF]]:
    """Return world positions and rotation matrices for all bones."""
    pos: dict[str, ArrayF] = {}
    rot: dict[str, ArrayF] = {}

    def walk(name: str, parent_R: ArrayF, parent_p: ArrayF) -> None:
        bone = bones[name]
        vals = frame.get(name, np.zeros(len(bone.dof) or 1))
        R_local = _channels_to_R(bone, vals)
        if name == "root":
            # root translation in ASF units
            if vals.size >= 3:
                p = np.array(vals[:3], dtype=np.float64) * length_scale_m
            else:
                p = parent_p.copy()
            R = R_local
        else:
            offset = bone.direction / (np.linalg.norm(bone.direction) + 1e-12) * bone.length
            p = parent_p + parent_R @ (offset * length_scale_m)
            R = parent_R @ R_local
        pos[name] = p
        rot[name] = R
        for child in bone.children:
            if child in bones:
                walk(child, R, p)

    walk("root", np.eye(3), np.zeros(3))
    return pos, rot


def _body_omega_from_R(R: ArrayF, dt: float) -> ArrayF:
    n = R.shape[0]
    out = np.zeros((n, 3), dtype=np.float64)
    for i in range(n - 1):
        dR = R[i].T @ R[i + 1]
        # vee(log SO3)
        cos_th = float(np.clip((np.trace(dR) - 1.0) * 0.5, -1.0, 1.0))
        th = float(np.arccos(cos_th))
        if th < 1e-9:
            w = np.zeros(3)
        else:
            w_hat = (dR - dR.T) * (th / (2.0 * np.sin(th)))
            w = np.array([w_hat[2, 1], w_hat[0, 2], w_hat[1, 0]]) / dt
        out[i] = w
    if n >= 2:
        out[-1] = out[-2]
    return out


def _smooth_rotations(R: ArrayF, win: int = 5) -> ArrayF:
    """Chordal mean filter on SO(3) to kill Euler-singularity spikes."""
    n = R.shape[0]
    out = R.copy()
    half = max(1, win // 2)
    for i in range(n):
        lo, hi = max(0, i - half), min(n, i + half + 1)
        # Chordal mean via SVD of sum of rotation matrices
        S = np.sum(R[lo:hi], axis=0)
        U, _, Vt = np.linalg.svd(S)
        Rm = U @ Vt
        if np.linalg.det(Rm) < 0:
            U[:, -1] *= -1
            Rm = U @ Vt
        # Keep hemisphere continuity vs previous
        if i and np.trace(out[i - 1].T @ Rm) < 0:
            # flip 180 — rare; fall back to previous
            Rm = out[i - 1]
        out[i] = Rm
    return out


def trial_to_case(
    bones: dict[str, Bone],
    frames: list[dict[str, ArrayF]],
    trial: str,
) -> CmuSwingCase:
    n = len(frames)
    dt = 1.0 / FS_HZ
    t = np.arange(n, dtype=np.float64) * dt
    R_w = np.zeros((n, 3, 3), dtype=np.float64)
    pos = np.zeros((n, 3), dtype=np.float64)
    bone = HAND_BONE if HAND_BONE in bones else WRIST_BONE
    for i, fr in enumerate(frames):
        pmap, rmap = forward_kinematics(bones, fr)
        R_w[i] = rmap[bone]
        pos[i] = pmap[bone]

    # CMU is Y-up-ish (Vicon); map to Z-up like MultiSense adapter.
    R_yup_zup = np.array(
        [[1.0, 0.0, 0.0], [0.0, 0.0, -1.0], [0.0, 1.0, 0.0]], dtype=np.float64
    )
    R_w = np.einsum("ij,njk->nik", R_yup_zup, R_w)
    R_w = _smooth_rotations(R_w, win=5)
    pos = (R_yup_zup @ pos.T).T
    pos = pos - pos[0]

    quats = np.stack([so3.rotmat_to_quat(R_w[i]) for i in range(n)])
    for i in range(1, n):
        quats[i] = so3.ensure_quat_hemisphere(quats[i], quats[i - 1])

    gyro = _body_omega_from_R(R_w, dt)
    # Soft-clip pathological spikes from residual singularities (keep shape).
    peak = float(np.percentile(np.linalg.norm(gyro, axis=1), 99))
    lim = max(25.0, 1.5 * peak)
    gn = np.linalg.norm(gyro, axis=1, keepdims=True) + 1e-9
    gyro = np.where(gn > lim, gyro * (lim / gn), gyro)

    # Specific force at rest = -R^T g; add linear accel of wrist.
    vel = np.gradient(pos, dt, axis=0)
    acc_w = np.gradient(vel, dt, axis=0)
    # Light accel smooth — mocap differentiation is noisy at 120 Hz.
    acc_w = np.column_stack([np.convolve(acc_w[:, k], np.ones(5) / 5, mode="same") for k in range(3)])
    accel = np.zeros((n, 3), dtype=np.float64)
    for i in range(n):
        accel[i] = R_w[i].T @ (acc_w[i] - so3.G_WORLD)

    # Crude phase labels from |ω|
    omega = np.linalg.norm(gyro, axis=1)
    peak_i = int(np.argmax(omega))
    top = int(np.argmin(omega[: max(2, int(0.7 * n))]))
    if top >= peak_i:
        top = max(1, peak_i - int(0.2 * FS_HZ))
    impact = peak_i  # kinematic proxy (no ball)
    address = max(0, top - int(0.4 * FS_HZ))
    finish = min(n - 1, impact + int(0.4 * FS_HZ))
    phases = SwingPhases(
        address_idx=address, top_idx=top, impact_idx=impact, finish_idx=finish
    )
    phases.validate_order()

    packet = ImuPacket(
        t=t,
        gyro=gyro,
        accel=accel,
        frame=SensorFrame(
            fs_hz=FS_HZ,
            device_id="cmu64_synth_wrist",
            handedness=Handedness.RIGHT,
            wrist=WristSide.LEAD,
            is_canonical=True,
        ),
    )
    return CmuSwingCase(
        packet=packet,
        trial=trial,
        quats_ref=quats,
        positions_ref=pos,
        phases=phases,
        adapter_meta={
            "fs_hz": FS_HZ,
            "n": float(n),
            "peak_omega_rad_s": float(np.max(omega)),
            "path_span_m": float(np.max(np.linalg.norm(pos - pos[0], axis=1))),
            "omega_clip_lim": float(lim),
        },
    )


def dataset_status(root: Path | None = None) -> dict[str, Any]:
    root = root or DEFAULT_ROOT
    raw = root / "raw"
    asf = raw / "64.asf"
    amcs = sorted(raw.glob("64_*.amc"))
    return {
        "source": DOI_NOTE,
        "root": str(root),
        "asf_present": asf.exists(),
        "n_amc": len(amcs),
        "ready": asf.exists() and len(amcs) > 0,
        "license_note": (
            "CMU mocap free for research & commercial products; do not resell data"
        ),
    }


def fetch_trials(
    root: Path | None = None,
    *,
    trials: list[str] | None = None,
    timeout_s: float = 60.0,
) -> list[Path]:
    """Download ASF + selected AMC trials into ``data/cmu64/raw``."""
    root = root or DEFAULT_ROOT
    raw = root / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    trials = trials or [f"{i:02d}" for i in range(1, 11)]
    out: list[Path] = []
    asf_path = raw / "64.asf"
    if not asf_path.exists():
        urllib.request.urlretrieve(f"{BASE_URL}/64.asf", asf_path)  # noqa: S310
    out.append(asf_path)
    for tr in trials:
        path = raw / f"64_{tr}.amc"
        if not path.exists():
            urllib.request.urlretrieve(f"{BASE_URL}/64_{tr}.amc", path)  # noqa: S310
        out.append(path)
    return out


def iter_local_swings(
    root: Path | None = None,
    *,
    max_swings: int | None = 10,
) -> Iterator[CmuSwingCase]:
    root = root or DEFAULT_ROOT
    st = dataset_status(root)
    if not st["ready"]:
        return
    bones = parse_asf((root / "raw" / "64.asf").read_text(encoding="utf-8", errors="ignore"))
    count = 0
    for amc in sorted((root / "raw").glob("64_*.amc")):
        frames = parse_amc(amc.read_text(encoding="utf-8", errors="ignore"))
        if len(frames) < 30:
            continue
        yield trial_to_case(bones, frames, trial=amc.stem)
        count += 1
        if max_swings is not None and count >= max_swings:
            return
