"""Blind holdout protocol for zero-trust evaluation.

Dev seeds are used for everyday development and documentation tables.
Holdout seeds are sealed: inputs may be regenerated from the seed list, but
scores are only accepted when compared against a frozen truth artifact produced
by ``scripts/seal_holdout.py``.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Literal

import numpy as np

from golfmate_algo.bench.harness import (
    SwingCase,
    build_cases,
    build_cases_multibody,
    build_cases_robust_golden,
)

Mode = Literal["dev", "holdout", "full"]

DEV_SEEDS: tuple[int, ...] = tuple(range(0, 8))
HOLDOUT_SEEDS: tuple[int, ...] = tuple(range(1000, 1008))

PROTOCOL_ID = "golfmate-zt-v1"
DEFAULT_HOLDOUT_DIR = Path(__file__).resolve().parents[2] / "data" / "holdout"


@dataclass(frozen=True)
class ProtocolMeta:
    protocol_id: str
    mode: Mode
    seeds: tuple[int, ...]
    generators: tuple[str, ...]
    truth_sealed: bool
    artifact_sha256: str | None = None


def seeds_for_mode(mode: Mode, n_dev: int | None = None) -> list[int]:
    if mode == "holdout":
        return list(HOLDOUT_SEEDS)
    if mode == "full":
        return list(DEV_SEEDS) + list(HOLDOUT_SEEDS)
    n = n_dev if n_dev is not None else len(DEV_SEEDS)
    return list(DEV_SEEDS[:n])


def build_protocol_cases(
    *,
    mode: Mode = "dev",
    generators: Iterable[str] = ("analytic", "multibody", "multibody_violate"),
    n_dev: int | None = None,
    error_levels: dict | None = None,
) -> dict[str, list[SwingCase]]:
    """Build cases stratified by generator track."""
    seeds = seeds_for_mode(mode, n_dev=n_dev)
    # Holdout mode uses fewer error levels for speed unless full.
    if error_levels is None and mode == "holdout":
        from golfmate_algo.synth.imu_model import ImuErrorParams

        error_levels = {
            "consumer": lambda s: ImuErrorParams.consumer_grade(seed=s),
        }

    out: dict[str, list[SwingCase]] = {}
    gens = tuple(generators)
    if "analytic" in gens:
        out["isomorphic_analytic"] = build_cases(seeds=seeds, error_levels=error_levels)
    if "multibody" in gens:
        out["cross_multibody"] = build_cases_multibody(
            seeds=seeds, error_levels=error_levels, violate=False
        )
    if "multibody_violate" in gens:
        out["violation_stress"] = build_cases_multibody(
            seeds=seeds, error_levels=error_levels, violate=True
        )
    if "robust_golden" in gens:
        # Higher-value regimes; not part of the sealed holdout fingerprint set.
        robust = build_cases_robust_golden(seeds=seeds[: max(1, min(3, len(seeds)))])
        out.update(robust)
    return out


def _case_fingerprint(case: SwingCase) -> dict[str, Any]:
    return {
        "label": case.label,
        "generator": case.generator,
        "error_label": case.error_label,
        "n": int(case.t.shape[0]),
        "t0": float(case.t[0]),
        "t1": float(case.t[-1]),
        "gyro_sha": hashlib.sha256(np.ascontiguousarray(case.gyro).tobytes()).hexdigest()[:16],
        "accel_sha": hashlib.sha256(np.ascontiguousarray(case.accel).tobytes()).hexdigest()[:16],
        "impact_idx": int(case.swing.phases_true.impact_idx),
        "address_idx": int(case.swing.phases_true.address_idx),
    }


def seal_holdout(
    out_dir: Path | None = None,
    *,
    generators: Iterable[str] = ("analytic", "multibody"),
) -> dict[str, Any]:
    """Write holdout input fingerprints + truth summaries for sealed scoring."""
    out_dir = out_dir or DEFAULT_HOLDOUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    tracks = build_protocol_cases(mode="holdout", generators=generators)
    manifest: dict[str, Any] = {
        "protocol_id": PROTOCOL_ID,
        "seeds": list(HOLDOUT_SEEDS),
        "tracks": {},
    }
    for track, cases in tracks.items():
        rows = []
        truth_rows = []
        for case in cases:
            rows.append(_case_fingerprint(case))
            ph = case.swing.phases_true
            truth_rows.append(
                {
                    "label": case.label,
                    "error_label": case.error_label,
                    "phases": ph.as_dict(),
                    "q0": case.swing.quats_true[ph.address_idx].tolist(),
                    "pos0": case.swing.positions_true[ph.address_idx].tolist(),
                    "n": int(case.swing.quats_true.shape[0]),
                    "quat_sha": hashlib.sha256(
                        np.ascontiguousarray(case.swing.quats_true).tobytes()
                    ).hexdigest(),
                    "pos_sha": hashlib.sha256(
                        np.ascontiguousarray(case.swing.positions_true).tobytes()
                    ).hexdigest(),
                }
            )
        (out_dir / f"{track}_inputs.json").write_text(
            json.dumps(rows, indent=2), encoding="utf-8"
        )
        (out_dir / f"{track}_truth.json").write_text(
            json.dumps(truth_rows, indent=2), encoding="utf-8"
        )
        manifest["tracks"][track] = {
            "n_cases": len(cases),
            "inputs": f"{track}_inputs.json",
            "truth": f"{track}_truth.json",
            "inputs_sha256": hashlib.sha256(
                json.dumps(rows, sort_keys=True).encode()
            ).hexdigest(),
            "truth_sha256": hashlib.sha256(
                json.dumps(truth_rows, sort_keys=True).encode()
            ).hexdigest(),
        }

    blob = json.dumps(manifest, sort_keys=True).encode()
    sha = hashlib.sha256(blob).hexdigest()
    manifest["artifact_sha256"] = sha
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    # Public inputs-only copy for the repo (no truth files required to regenerate)
    public = {
        "protocol_id": PROTOCOL_ID,
        "seeds": list(HOLDOUT_SEEDS),
        "artifact_sha256": sha,
        "tracks": {
            k: {
                "n_cases": v["n_cases"],
                "inputs_sha256": v["inputs_sha256"],
            }
            for k, v in manifest["tracks"].items()
        },
    }
    (out_dir / "public_manifest.json").write_text(json.dumps(public, indent=2), encoding="utf-8")
    return manifest


def load_holdout_manifest(out_dir: Path | None = None) -> dict[str, Any]:
    out_dir = out_dir or DEFAULT_HOLDOUT_DIR
    path = out_dir / "manifest.json"
    if not path.exists():
        raise FileNotFoundError(
            f"Holdout manifest missing at {path}; run scripts/seal_holdout.py first"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def verify_holdout_inputs(
    tracks: dict[str, list[SwingCase]],
    out_dir: Path | None = None,
) -> list[str]:
    """Return mismatch messages if regenerated inputs disagree with sealed fingerprints."""
    out_dir = out_dir or DEFAULT_HOLDOUT_DIR
    violations: list[str] = []
    for track, cases in tracks.items():
        path = out_dir / f"{track}_inputs.json"
        if not path.exists():
            violations.append(f"missing sealed inputs for {track}")
            continue
        sealed = json.loads(path.read_text(encoding="utf-8"))
        if len(sealed) != len(cases):
            violations.append(
                f"{track}: case count {len(cases)} != sealed {len(sealed)}"
            )
            continue
        for case, row in zip(cases, sealed):
            fp = _case_fingerprint(case)
            for key in ("gyro_sha", "accel_sha", "impact_idx", "n"):
                if fp[key] != row[key]:
                    violations.append(
                        f"{track}/{case.label}: {key} mismatch {fp[key]} vs {row[key]}"
                    )
    return violations


def protocol_meta(
    mode: Mode,
    generators: Iterable[str],
    *,
    sealed: bool = False,
    artifact_sha256: str | None = None,
) -> ProtocolMeta:
    return ProtocolMeta(
        protocol_id=PROTOCOL_ID,
        mode=mode,
        seeds=tuple(seeds_for_mode(mode)),
        generators=tuple(generators),
        truth_sealed=sealed,
        artifact_sha256=artifact_sha256,
    )
