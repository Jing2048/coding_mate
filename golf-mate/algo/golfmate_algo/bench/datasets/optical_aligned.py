"""In-house SciRep-protocol optical-aligned MEMS mini golden (200 Hz).

Until Kim & Park (SciRep 2024) raw data or WIT-KinNet watch+OMC lands, this
module synthesises a *protocol-faithful* small set:

* 200 Hz capture (SciRep ``CAPTURE_FS_HZ``)
* Bosch-like ±16 g / 2000 dps consumer MEMS error + optional clip
* Optical GT = multibody sensor pose + club-head markers (address-relative)
* Honesty: ``inhouse_optical_aligned_synth`` — not tour MEMS, not SciRep raw

Used as a CI-stable test guarantee for single-wrist MEMS+optical alignment
contracts while external author shares are pending.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

import numpy as np
from numpy.typing import NDArray

from golfmate_algo.bench.datasets.multisense import ExternalSwingCase
from golfmate_algo.bench.golden import scirep_budgets
from golfmate_algo.synth.imu_model import ImuErrorParams, apply_imu_errors
from golfmate_algo.synth.multibody import SwingConfig, build_swing, casting_swing
from golfmate_algo.types import Handedness, ImuPacket, SwingPhases

ArrayF = NDArray[np.float64]

DEFAULT_ROOT = Path(__file__).resolve().parents[3] / "data" / "optical_aligned"
PROVENANCE = "inhouse_optical_aligned_synth_v1"


@dataclass(frozen=True)
class OpticalAlignedSpec:
    """One protocol case recipe."""

    label: str
    seed: int
    plane_tilt_deg: float = 55.0
    downswing_s: float = 0.26
    casting: bool = False
    clip: bool = False
    handedness: str = "right"


DEFAULT_SPECS: tuple[OpticalAlignedSpec, ...] = (
    OpticalAlignedSpec("oa_driver_a", seed=11, plane_tilt_deg=52.0),
    OpticalAlignedSpec("oa_driver_b", seed=17, plane_tilt_deg=58.0, downswing_s=0.24),
    OpticalAlignedSpec("oa_casting", seed=23, casting=True, plane_tilt_deg=55.0),
    OpticalAlignedSpec("oa_clip", seed=29, clip=True, plane_tilt_deg=50.0, downswing_s=0.22),
    OpticalAlignedSpec("oa_lefty", seed=31, handedness="left", plane_tilt_deg=54.0),
    OpticalAlignedSpec("oa_steep", seed=37, plane_tilt_deg=62.0, downswing_s=0.28),
)


def dataset_status(root: Path | None = None) -> dict[str, Any]:
    """Always ready — cases are generated on the fly from multibody."""
    root = root or DEFAULT_ROOT
    return {
        "source": "optical_aligned_inhouse",
        "protocol": "SciRep-2024-like 200 Hz wrist MEMS + optical markers",
        "doi_ref": "10.1038/s41598-024-59949-w",
        "root": str(root),
        "ready": True,
        "n_cases": len(DEFAULT_SPECS),
        "fs_hz": scirep_budgets.CAPTURE_FS_HZ,
        "gyro_range_deg_s": scirep_budgets.GYRO_RANGE_DEG_S,
        "accel_range_g": scirep_budgets.ACCEL_RANGE_G,
        "provenance": PROVENANCE,
        "honesty": (
            "Synthetic protocol twin — optical GT from multibody markers; "
            "not Kim&Park raw MEMS and not tour Watch captures."
        ),
    }


def _build_case(spec: OpticalAlignedSpec) -> ExternalSwingCase:
    fs = float(scirep_budgets.CAPTURE_FS_HZ)
    cfg = SwingConfig(
        fs_hz=fs,
        plane_tilt_deg=spec.plane_tilt_deg,
        downswing_s=spec.downswing_s,
        handedness=Handedness.LEFT if spec.handedness.lower().startswith("l") else Handedness.RIGHT,
        mount_segment=3 if spec.casting else 2,
        wrist_fe_impact_deg=12.0 + 0.3 * spec.seed,
        clubface_open_impact_deg=float((spec.seed % 9) - 4),
    )
    truth = casting_swing(cfg) if spec.casting else build_swing(cfg)
    pkt_clean = truth.to_imu_packet(couple_high_order=True)
    err = ImuErrorParams.consumer_grade(seed=spec.seed)
    # Enforce SciRep range ceilings explicitly (already defaults on consumer_grade).
    err.gyro_range_deg_s = float(scirep_budgets.GYRO_RANGE_DEG_S)
    err.accel_range_g = float(scirep_budgets.ACCEL_RANGE_G)
    if spec.clip:
        # Force hard clip stress by lowering range so peak rates saturate.
        err.gyro_range_deg_s = 1000.0
        err.accel_range_g = 8.0
    t2, g2, a2, _ = apply_imu_errors(pkt_clean.t, pkt_clean.gyro, pkt_clean.accel, err)
    dirty = ImuPacket(frame=pkt_clean.frame, t=t2, gyro=g2, accel=a2)

    # Optical markers: sensor pose + club head (address-relative world)
    quats_ref = truth.sensor_quat.copy()
    pos_ref = truth.sensor_pos - truth.sensor_pos[int(truth.address_idx)]
    club_ref = truth.club_head_pos - truth.club_head_pos[int(truth.address_idx)]

    phases = SwingPhases(
        address_idx=int(truth.address_idx),
        top_idx=int(truth.top_idx),
        impact_idx=int(truth.impact_idx),
        finish_idx=int(truth.finish_idx),
    )
    phases.validate_order()

    return ExternalSwingCase(
        packet=dirty,
        subject_id=f"OA_{spec.label}",
        swing_number=int(spec.seed),
        impact_time_s=float(truth.t[truth.impact_idx]),
        impact_idx=int(truth.impact_idx),
        phases=phases,
        quats_ref=quats_ref,
        positions_ref=pos_ref,
        reference={
            "club_speed_m_s": float(truth.club_head_speed[truth.impact_idx]),
            "fs_hz": fs,
            "gyro_range_deg_s": float(scirep_budgets.GYRO_RANGE_DEG_S),
            "accel_range_g": float(scirep_budgets.ACCEL_RANGE_G),
            "optical_club_path_span_m": float(
                np.max(np.linalg.norm(club_ref - club_ref[0], axis=1))
            ),
        },
        split="val",
        provenance=PROVENANCE,
        adapter_meta={
            "peak_omega_rad_s": float(np.max(np.linalg.norm(dirty.gyro, axis=1))),
            "path_span_m": float(np.max(np.linalg.norm(pos_ref, axis=1))),
            "casting": float(spec.casting),
            "clip": float(spec.clip),
            "protocol_fs_hz": fs,
        },
    )


def iter_local_swings(
    *,
    max_swings: int | None = None,
    specs: tuple[OpticalAlignedSpec, ...] | None = None,
) -> Iterator[ExternalSwingCase]:
    specs = specs or DEFAULT_SPECS
    for i, spec in enumerate(specs):
        if max_swings is not None and i >= max_swings:
            return
        yield _build_case(spec)


def materialize(root: Path | None = None, *, max_swings: int | None = None) -> list[Path]:
    """Optional: write a tiny JSON index under data/optical_aligned/ for audit."""
    import json

    root = root or DEFAULT_ROOT
    root.mkdir(parents=True, exist_ok=True)
    index = []
    paths: list[Path] = []
    for case in iter_local_swings(max_swings=max_swings):
        entry = {
            "subject_id": case.subject_id,
            "swing_number": case.swing_number,
            "impact_idx": case.impact_idx,
            "fs_hz": case.packet.frame.fs_hz,
            "n": int(case.packet.t.shape[0]),
            "provenance": case.provenance,
            "reference": case.reference,
            "adapter_meta": case.adapter_meta,
        }
        index.append(entry)
    out = root / "index.json"
    out.write_text(json.dumps({"version": PROVENANCE, "cases": index}, indent=2) + "\n")
    paths.append(out)
    return paths
