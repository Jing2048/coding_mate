#!/usr/bin/env python3
"""Local lab server: Watch/iPhone capture JSON/packed-v2 → full Golf Mate analysis.

Run on the Mac while the iPhone app points at this host:

    cd golf-mate/algo
    source .venv/bin/activate
    python scripts/watch_lab_server.py --host 0.0.0.0 --port 8765

    Then set the iPhone analysis URL to http://<mac-lan-ip>:8765
"""

from __future__ import annotations

import argparse
import json
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

import numpy as np

from golfmate_algo.devices.packed_capture_v2 import (
    decode_packed_capture_v2,
    is_packed_capture_v2,
)
from golfmate_algo.devices.watch_capture import (
    load_watch_capture,
    watch_capture_from_v1_dict,
)
from golfmate_algo.export.edge_trajectory_contract import (
    TRAJECTORY_POINTS,
    sample_trajectory_xyz,
)


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


def _trajectory_quality(report: Any, capture_mode: str) -> dict[str, Any]:
    meta = report.meta if isinstance(report.meta, dict) else {}
    traj_meta = meta.get("traj") or meta.get("trajectory_meta") or {}
    residual = None
    radius = None
    if isinstance(traj_meta, dict):
        residual = traj_meta.get("residual_rms") or traj_meta.get("rigid_residual_rms")
        radius = traj_meta.get("radius_m")
    impact_c = float(meta.get("impact_confidence", 0.5) or 0.5)
    conf = float(np.clip(0.55 * impact_c + 0.45 * (0.7 if capture_mode == "high_rate" else 0.55), 0.05, 0.95))
    reasons: list[str] = []
    if capture_mode == "compat":
        reasons.append("compat_rate")
        conf *= 0.92
    if residual is not None and float(residual) > 15.0:
        reasons.append("rigid_residual_high")
        conf *= 0.7
    validity = "ok"
    if conf < 0.25:
        validity = "abstain"
    elif reasons:
        validity = "degraded"
    return {
        "confidence": float(np.clip(conf, 0.05, 0.95)),
        "validity": validity,
        "reasons": reasons,
        "radius_m": float(radius) if radius is not None else None,
        "residual_rms": float(residual) if residual is not None else None,
        "pointCount": TRAJECTORY_POINTS,
        "source": "python_analyze_swing",
    }


def _preview_block(metadata: Mapping[str, Any]) -> dict[str, Any] | None:
    prev = metadata.get("preview")
    if not isinstance(prev, Mapping):
        return None
    traj = prev.get("trajectory")
    if traj is None:
        return None
    xyz = np.asarray(traj, dtype=np.float64).reshape(-1, 3)
    if xyz.shape[0] != TRAJECTORY_POINTS:
        # Still surface what we have; clients may ignore shape mismatches.
        pass
    return {
        "trajectory": xyz.tolist(),
        "confidence": float(prev.get("confidence", 0.0) or 0.0),
        "quality": float(prev.get("quality", prev.get("confidence", 0.0)) or 0.0),
        "pointCount": int(xyz.shape[0]),
        "source": str(prev.get("source", "on_device_preview")),
    }


def build_analysis_response(capture: Any, report: Any, impact_hint: float | None) -> dict[str, Any]:
    """Shared JSON response for file / HTTP analyze paths."""
    quality = _trajectory_quality(report, capture.capture_mode)
    final_xyz = sample_trajectory_xyz(
        report.positions,
        address_idx=report.phases.address_idx,
        finish_idx=report.phases.finish_idx,
        n_points=TRAJECTORY_POINTS,
    )
    preview = _preview_block(capture.metadata)
    final_block = {
        "trajectory": final_xyz.tolist(),
        "confidence": quality["confidence"],
        "quality": quality,
        "pointCount": TRAJECTORY_POINTS,
        "source": "python_analyze_swing",
    }
    return {
        "schemaVersion": "golfmate-watch-analysis-v1",
        "ok": True,
        "captureMode": capture.capture_mode,
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
        "finalTrajectory": final_xyz.tolist(),
        "trajectoryConfidence": quality["confidence"],
        "trajectoryQuality": quality,
        "preview": preview,
        "final": final_block,
        "meta": {
            "impact_mode": report.meta.get("impact_mode"),
            "impact_method": report.meta.get("impact_method"),
            "impact_confidence": report.meta.get("impact_confidence"),
            "fs_hz": report.meta.get("fs_hz"),
            "frame": report.meta.get("frame"),
            "pro_swing": report.meta.get("pro_swing"),
            "high_order": report.meta.get("high_order"),
            "capture_mode": capture.capture_mode,
            "trajectory": report.meta.get("trajectory"),
        },
    }


def analyze_payload(payload: dict[str, Any]) -> dict[str, Any]:
    capture = watch_capture_from_v1_dict(payload)
    impact_hint = capture.high_rate_impact_time_s()
    report = capture.analyze()
    return build_analysis_response(capture, report, impact_hint)


def analyze_bytes(raw: bytes) -> dict[str, Any]:
    """Accept JSON v1 object bytes or packed v2 file bytes."""
    if is_packed_capture_v2(raw):
        packed = decode_packed_capture_v2(raw)
        return analyze_payload(packed.to_v1_dict())
    payload = json.loads(raw.decode("utf-8"))
    return analyze_payload(payload)


def analyze_path(path: Path) -> dict[str, Any]:
    capture = load_watch_capture(path)
    impact_hint = capture.high_rate_impact_time_s()
    report = capture.analyze()
    return build_analysis_response(capture, report, impact_hint)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[watch-lab] {self.address_string()} {fmt % args}")

    def _send(self, code: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._send(204, {"ok": True})

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path in {"/", "/health"}:
            self._send(
                200,
                {
                    "ok": True,
                    "service": "golfmate-watch-lab",
                    "algorithm": "full-python-analyze_swing",
                    "captureSchema": [
                        "golfmate-watch-capture-v1",
                        "golfmate-watch-capture-v2",
                    ],
                    "analysisSchema": "golfmate-watch-analysis-v1",
                    "finalTrajectoryPoints": TRAJECTORY_POINTS,
                },
            )
            return
        self._send(404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path != "/analyze":
            self._send(404, {"ok": False, "error": "not found"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        try:
            # JSON is the iPhone lab path today; packed v2 accepted for file-like POSTs.
            ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            if ctype in {"application/octet-stream", "application/x-golfmate-packed-v2"}:
                result = analyze_bytes(raw)
            elif is_packed_capture_v2(raw):
                result = analyze_bytes(raw)
            else:
                # Preserve tempfile path for debuggability parity with prior server.
                payload = json.loads(raw.decode("utf-8"))
                with tempfile.NamedTemporaryFile(
                    "w", suffix=".json", encoding="utf-8", delete=False
                ) as tmp:
                    json.dump(payload, tmp)
                    path_tmp = Path(tmp.name)
                try:
                    result = analyze_path(path_tmp)
                finally:
                    path_tmp.unlink(missing_ok=True)
            self._send(200, result)
        except Exception as exc:  # noqa: BLE001 - lab surface
            self._send(400, {"ok": False, "error": str(exc)})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(
        f"Golf Mate Watch lab server on http://{args.host}:{args.port}\n"
        "POST /analyze with golfmate-watch-capture-v1 JSON or packed v2 bytes"
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
