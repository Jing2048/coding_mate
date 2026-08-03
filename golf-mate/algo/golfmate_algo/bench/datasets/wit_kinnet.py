"""WIT-KinNet download stub + layout contract (arXiv:2606.22876).

Highest product-fit golden (real smartwatch MEMS + OMC). Not publicly released
as of 2026-08 — contact authors. This module:

1. Documents the on-disk contract so drops light up CI without code changes
2. Auto-detects readiness when watch IMU + OMC files appear under data/wit_kinnet/
3. Exposes ``iter_local_swings`` compatible with MultiSense ``ExternalSwingCase``

Expected layout (per subject / swing)::

    data/wit_kinnet/
      README.md                 # optional
      manifest.json             # optional index
      Sub01/
        Swing001/
          watch_imu.npz|h5      # t, gyro(N,3) rad/s, accel(N,3) m/s^2, fs≈100
          omc_joints.npz|h5     # t_omc, quats(N,4), pos(N,3), impact_idx
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

import numpy as np

from golfmate_algo.bench.datasets.multisense import ExternalSwingCase
from golfmate_algo.types import Handedness, ImuPacket, SensorFrame, SwingPhases, WristSide

DEFAULT_ROOT = Path(__file__).resolve().parents[3] / "data" / "wit_kinnet"
ARXIV = "https://arxiv.org/abs/2606.22876"
PROVENANCE = "wit_kinnet_watch_mems_omc"
CONTRACT_VERSION = "wit-kinnet-contract-v1"

# Contract field requirements (documented for author drops / future fetchers)
WATCH_IMU_FIELDS = ("t", "gyro", "accel")
OMC_FIELDS = ("t", "quats", "pos")


def expected_layout() -> dict[str, Any]:
    return {
        "contract_version": CONTRACT_VERSION,
        "root": str(DEFAULT_ROOT),
        "per_swing": {
            "watch_imu": "watch_imu.npz|.h5 with keys t, gyro(N,3 rad/s), accel(N,3 m/s^2)",
            "omc_joints": "omc_joints.npz|.h5 with keys t, quats(N,4 wxyz), pos(N,3 m), optional impact_idx",
            "fs_watch_hz": 100.0,
            "fs_omc_hz": 120.0,
        },
        "handedness": "lead wrist; Right-handed golfer → LeftHand lead by default",
        "arxiv": ARXIV,
    }


def _find_swing_dirs(root: Path) -> list[Path]:
    if not root.exists():
        return []
    swings: list[Path] = []
    for sub in sorted(p for p in root.glob("Sub*") if p.is_dir()):
        swings.extend(sorted(p for p in sub.glob("Swing*") if p.is_dir()))
    # Also accept flat Swing* under root
    swings.extend(sorted(p for p in root.glob("Swing*") if p.is_dir()))
    return swings


def _imu_path(swing_dir: Path) -> Path | None:
    for name in ("watch_imu.npz", "watch_imu.h5", "watch_imu.hdf5", "imu.npz"):
        p = swing_dir / name
        if p.exists():
            return p
    return None


def _omc_path(swing_dir: Path) -> Path | None:
    for name in ("omc_joints.npz", "omc_joints.h5", "omc_joints.hdf5", "omc.npz"):
        p = swing_dir / name
        if p.exists():
            return p
    return None


def dataset_status(root: Path | None = None) -> dict[str, Any]:
    root = root or DEFAULT_ROOT
    swings = _find_swing_dirs(root)
    paired = [d for d in swings if _imu_path(d) and _omc_path(d)]
    ready = len(paired) > 0
    reason = (
        f"{len(paired)} paired watch+OMC swings under {root}"
        if ready
        else (
            "Dataset not publicly released; contact authors. "
            f"When available, drop synced watch IMU + OMC under {root} "
            f"per contract {CONTRACT_VERSION}."
        )
    )
    return {
        "source": "wit_kinnet",
        "arxiv": ARXIV,
        "root": str(root),
        "ready": ready,
        "reason": reason,
        "n_swing_dirs": len(swings),
        "n_paired": len(paired),
        "product_fit": "highest_single_wrist_mems_plus_omc",
        "contract": expected_layout(),
        "status": "ok" if ready else "unavailable",
        "provenance": PROVENANCE,
    }


def _load_npz(path: Path) -> dict[str, Any]:
    if path.suffix == ".npz":
        data = np.load(path, allow_pickle=False)
        return {k: data[k] for k in data.files}
    if path.suffix in {".h5", ".hdf5"}:
        import h5py

        out: dict[str, Any] = {}
        with h5py.File(path, "r") as f:
            for k in f.keys():
                out[k] = np.asarray(f[k])
        return out
    raise ValueError(f"unsupported WIT-KinNet file: {path}")


def load_swing_dir(swing_dir: Path) -> ExternalSwingCase:
    """Load one paired watch+OMC swing into ExternalSwingCase."""
    imu_p = _imu_path(swing_dir)
    omc_p = _omc_path(swing_dir)
    if imu_p is None or omc_p is None:
        raise FileNotFoundError(f"missing watch_imu or omc_joints in {swing_dir}")
    imu = _load_npz(imu_p)
    omc = _load_npz(omc_p)
    for k in WATCH_IMU_FIELDS:
        if k not in imu:
            raise KeyError(f"{imu_p} missing key {k}")
    for k in OMC_FIELDS:
        if k not in omc:
            raise KeyError(f"{omc_p} missing key {k}")

    t = np.asarray(imu["t"], dtype=np.float64).reshape(-1)
    gyro = np.asarray(imu["gyro"], dtype=np.float64).reshape(-1, 3)
    accel = np.asarray(imu["accel"], dtype=np.float64).reshape(-1, 3)
    if t.size < 2:
        raise ValueError("watch IMU too short")
    fs = float(1.0 / np.median(np.diff(t))) if t.size > 1 else 100.0
    # Prefer explicit fs if stored
    if "fs_hz" in imu:
        fs = float(np.asarray(imu["fs_hz"]).reshape(-1)[0])

    quats = np.asarray(omc["quats"], dtype=np.float64).reshape(-1, 4)
    pos = np.asarray(omc["pos"], dtype=np.float64).reshape(-1, 3)
    # Resample OMC onto watch timeline via nearest index (contract: pre-synced preferred)
    t_omc = np.asarray(omc["t"], dtype=np.float64).reshape(-1)
    if t_omc.size != t.size:
        idx = np.clip(
            np.searchsorted(t_omc, t, side="left"),
            0,
            max(t_omc.size - 1, 0),
        )
        quats = quats[idx]
        pos = pos[idx]

    impact_idx = int(omc["impact_idx"]) if "impact_idx" in omc else int(np.argmax(np.linalg.norm(gyro, axis=1)))
    top_idx = int(omc["top_idx"]) if "top_idx" in omc else max(0, impact_idx // 2)
    address_idx = int(omc["address_idx"]) if "address_idx" in omc else 0
    finish_idx = int(omc["finish_idx"]) if "finish_idx" in omc else t.size - 1
    phases = SwingPhases(
        address_idx=address_idx,
        top_idx=top_idx,
        impact_idx=impact_idx,
        finish_idx=finish_idx,
    )

    subject = swing_dir.parent.name if swing_dir.parent.name.startswith("Sub") else "WIT"
    try:
        swing_number = int("".join(ch for ch in swing_dir.name if ch.isdigit()) or "0")
    except ValueError:
        swing_number = 0

    frame = SensorFrame(
        fs_hz=fs,
        wrist=WristSide.LEAD,
        handedness=Handedness.RIGHT,
        is_canonical=False,
    )
    packet = ImuPacket(frame=frame, t=t, gyro=gyro, accel=accel)
    return ExternalSwingCase(
        packet=packet,
        subject_id=subject,
        swing_number=swing_number,
        impact_time_s=float(t[impact_idx]),
        impact_idx=impact_idx,
        phases=phases,
        quats_ref=quats,
        positions_ref=pos - pos[address_idx],
        reference={"fs_hz": fs, "omc_fs_hz": float(1.0 / np.median(np.diff(t_omc))) if t_omc.size > 1 else 120.0},
        split="holdout",
        provenance=PROVENANCE,
        adapter_meta={
            "peak_omega_rad_s": float(np.max(np.linalg.norm(gyro, axis=1))),
            "path_span_m": float(np.max(np.linalg.norm(pos - pos[address_idx], axis=1))),
            "contract_version": 1.0,
        },
    )


def iter_local_swings(
    root: Path | None = None,
    *,
    max_swings: int | None = 40,
) -> Iterator[ExternalSwingCase]:
    root = root or DEFAULT_ROOT
    count = 0
    for d in _find_swing_dirs(root):
        if _imu_path(d) is None or _omc_path(d) is None:
            continue
        yield load_swing_dir(d)
        count += 1
        if max_swings is not None and count >= max_swings:
            return


def write_contract_readme(root: Path | None = None) -> Path:
    """Drop a README describing the expected author-share layout."""
    root = root or DEFAULT_ROOT
    root.mkdir(parents=True, exist_ok=True)
    path = root / "CONTRACT.md"
    path.write_text(
        "# WIT-KinNet drop contract\n\n"
        f"Source: {ARXIV}\n"
        f"Version: `{CONTRACT_VERSION}`\n\n"
        "```json\n"
        + json.dumps(expected_layout(), indent=2)
        + "\n```\n",
        encoding="utf-8",
    )
    return path
