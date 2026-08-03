#!/usr/bin/env python3
"""Local lab server: Watch/iPhone capture JSON → full Golf Mate analysis.

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
from typing import Any
from urllib.parse import urlparse

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


def analyze_payload(payload: dict[str, Any]) -> dict[str, Any]:
    with tempfile.NamedTemporaryFile(
        "w", suffix=".json", encoding="utf-8", delete=False
    ) as tmp:
        json.dump(payload, tmp)
        path = Path(tmp.name)
    try:
        capture = load_watch_capture(path)
        impact_hint = capture.high_rate_impact_time_s()
        report = capture.analyze()
        return {
            "schemaVersion": "golfmate-watch-analysis-v1",
            "ok": True,
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
            "meta": {
                "impact_mode": report.meta.get("impact_mode"),
                "impact_method": report.meta.get("impact_method"),
                "impact_confidence": report.meta.get("impact_confidence"),
                "fs_hz": report.meta.get("fs_hz"),
                "frame": report.meta.get("frame"),
                "pro_swing": report.meta.get("pro_swing"),
                "high_order": report.meta.get("high_order"),
            },
        }
    finally:
        path.unlink(missing_ok=True)


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
                    "captureSchema": "golfmate-watch-capture-v1",
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
            payload = json.loads(raw.decode("utf-8"))
            result = analyze_payload(payload)
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
        "POST /analyze with golfmate-watch-capture-v1 JSON"
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
