#!/usr/bin/env python3
"""Export the edge-trajectory student artifact (+ optional Core ML on macOS).

Always writes the deterministic NumPy ``.npz`` weights. Core ML conversion is
attempted only when ``coremltools`` imports successfully (typically macOS).
This script never claims a ``.mlmodel`` was produced if conversion is skipped.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from golfmate_algo.export.edge_trajectory_contract import (
    CONTRACT_VERSION,
    INPUT_CHANNELS,
    INPUT_FS_HZ,
    OUTPUT_DIM,
    TRAJECTORY_POINTS,
    load_edge_trajectory_schema,
)
from golfmate_algo.export.edge_trajectory_model import (
    DEFAULT_ARTIFACT_NAME,
    ensure_default_artifact,
    load_edge_student,
    train_default_edge_student,
)


def _try_coreml_export(npz_path: Path, mlmodel_path: Path) -> dict:
    """Best-effort Core ML export. Returns status dict; never raises on missing ct."""
    try:
        import coremltools as ct  # type: ignore
    except Exception as exc:  # noqa: BLE001 - optional Mac dependency
        return {
            "ok": False,
            "skipped": True,
            "reason": f"coremltools unavailable: {exc}",
            "mlmodel_path": None,
        }

    try:
        from coremltools.converters.mil import Builder as mb  # type: ignore
        from coremltools.converters.mil.mil import types  # type: ignore
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "skipped": True,
            "reason": f"coremltools MIL API unavailable: {exc}",
            "mlmodel_path": None,
        }

    student = load_edge_student(npz_path)
    feat_dim = len(student.feature_names)
    W = student.W.astype("float32")
    b = student.b.astype("float32")
    mean = student.feat_mean.astype("float32")
    std = student.feat_std.astype("float32")
    projection = student.projection.astype("float32")
    hidden_bias = student.hidden_bias.astype("float32")

    try:
        # Minimal MIL program: y = W @ ((x - mean) / std) + b.
        # The function argument names the Core ML input in current MIL APIs.
        @mb.program(
            input_specs=[
                mb.TensorSpec(shape=(1, feat_dim), dtype=types.fp32)
            ]
        )
        def edge_prog(features):  # noqa: ANN001
            x = mb.sub(x=features, y=mean.reshape(1, -1), name="centered")
            x = mb.real_div(x=x, y=std.reshape(1, -1), name="normalized")
            hidden = mb.matmul(x=x, y=projection, name="hidden_projection")
            hidden = mb.add(
                x=hidden,
                y=hidden_bias.reshape(1, -1),
                name="hidden_pre_activation",
            )
            hidden = mb.tanh(x=hidden, name="hidden")
            phi = mb.concat(values=[hidden, x], axis=1, name="student_features")
            y = mb.matmul(x=phi, y=W.T, name="linear")
            y = mb.add(x=y, y=b.reshape(1, -1), name="edge_outputs")
            return y

        mlmodel = ct.convert(
            edge_prog,
            convert_to="mlprogram",
            compute_units=ct.ComputeUnit.ALL,
            # coremltools exposes spec targets by iOS generation. iOS16 maps
            # to Core ML specification 7, supported by our watchOS 10 target.
            minimum_deployment_target=ct.target.iOS16,
        )
        mlmodel.author = "Golf Mate"
        mlmodel.short_description = (
            f"{CONTRACT_VERSION} student (feature→phases/traj/conf/rush)"
        )
        mlmodel_path.parent.mkdir(parents=True, exist_ok=True)
        if mlmodel_path.exists():
            shutil.rmtree(mlmodel_path)
        mlmodel.save(str(mlmodel_path))
        return {
            "ok": True,
            "skipped": False,
            "reason": None,
            "mlmodel_path": mlmodel_path.name,
        }
    except Exception as exc:  # noqa: BLE001 - conversion is best-effort
        return {
            "ok": False,
            "skipped": False,
            "reason": f"coremltools convert failed: {exc}",
            "mlmodel_path": None,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "golfmate_algo"
        / "export"
        / "artifacts",
    )
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--n-train", type=int, default=512)
    parser.add_argument(
        "--numpy-only",
        action="store_true",
        help="Skip Core ML attempt even if coremltools is installed",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Retrain even if the default npz already exists",
    )
    args = parser.parse_args()

    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    npz_path = out_dir / DEFAULT_ARTIFACT_NAME
    meta_path = out_dir / "edge_trajectory_export_meta.json"
    mlmodel_path = out_dir / "edge_trajectory_v1.mlpackage"

    if args.force or not npz_path.is_file():
        student = train_default_edge_student(n_train=args.n_train, seed=args.seed)
        student.save(npz_path)
    else:
        ensure_default_artifact(npz_path)
        student = load_edge_student(npz_path)

    schema = load_edge_trajectory_schema()
    coreml_status: dict
    if args.numpy_only:
        coreml_status = {
            "ok": False,
            "skipped": True,
            "reason": "numpy-only flag set",
            "mlmodel_path": None,
        }
    else:
        coreml_status = _try_coreml_export(npz_path, mlmodel_path)

    meta = {
        "contract_version": CONTRACT_VERSION,
        "input_fs_hz": INPUT_FS_HZ,
        "input_channels": list(INPUT_CHANNELS),
        "output_dim": OUTPUT_DIM,
        "trajectory_points": TRAJECTORY_POINTS,
        "numpy_artifact": npz_path.name,
        "numpy_artifact_present": npz_path.is_file(),
        "train_seed": student.train_seed,
        "projection_seed": student.projection_seed,
        "n_train": student.n_train,
        "schema_contract_version": schema.get("contract_version"),
        "coreml": coreml_status,
        "coreml_model_present": bool(
            coreml_status.get("ok") and coreml_status.get("mlmodel_path")
        ),
    }
    meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(meta, indent=2))
    if not meta["numpy_artifact_present"]:
        print("ERROR: NumPy artifact missing after export", file=sys.stderr)
        return 1
    if coreml_status.get("skipped"):
        print(
            f"NOTE: Core ML not produced ({coreml_status.get('reason')})",
            file=sys.stderr,
        )
    elif not coreml_status.get("ok"):
        print(
            f"NOTE: Core ML conversion failed ({coreml_status.get('reason')})",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
