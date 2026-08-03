#!/usr/bin/env python3
"""Analyze a Golf Mate Apple Watch capture with the full Python pipeline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np

from golfmate_algo.devices.watch_capture import load_watch_capture


def _jsonable(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("capture", type=Path)
    parser.add_argument("-o", "--output", type=Path)
    args = parser.parse_args()

    capture = load_watch_capture(args.capture)
    impact_hint = capture.high_rate_impact_time_s()
    report = capture.analyze()
    payload = {
        "schemaVersion": "golfmate-watch-analysis-v1",
        "sourceCapture": str(args.capture),
        "sourceRatesHz": {
            "accelerometer": round(
                1.0 / float(np.median(np.diff(capture.accel_t_800))), 3
            ),
            "deviceMotion": round(capture.packet.frame.fs_hz, 3),
        },
        "highRateImpactHintS": impact_hint,
        "phases": report.phases.as_dict(),
        "features": _jsonable(vars(report.features)),
        "findings": [_jsonable(vars(item)) for item in report.findings],
        "meta": _jsonable(report.meta),
    }
    encoded = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(encoded + "\n", encoding="utf-8")
    else:
        print(encoded)


if __name__ == "__main__":
    main()
