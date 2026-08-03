"""MultiSenseGolf elite (pro / high expertise) subject selection."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# golfmate_algo/reference/elite.py → parents[2] == golf-mate/algo
_ALGO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = _ALGO_ROOT / "data" / "reference" / "multisense_elite_manifest.json"
# Fallback for older layouts / misplaced manifests
_FALLBACKS = (
    _ALGO_ROOT.parent / "data" / "reference" / "multisense_elite_manifest.json",
    Path(__file__).resolve().parents[3] / "data" / "reference" / "multisense_elite_manifest.json",
)


def _resolve_manifest(path: Path | None = None) -> Path:
    if path is not None:
        return path
    if DEFAULT_MANIFEST.exists():
        return DEFAULT_MANIFEST
    for p in _FALLBACKS:
        if p.exists():
            return p
    return DEFAULT_MANIFEST


def load_elite_manifest(path: Path | None = None) -> dict[str, Any]:
    p = _resolve_manifest(path)
    if not p.exists():
        return {
            "version": "multisense-elite-v1",
            "subject_ids": [],
            "status": "missing_manifest",
            "resolved_path": str(p),
        }
    data = json.loads(p.read_text(encoding="utf-8"))
    data["resolved_path"] = str(p)
    data.setdefault("status", "ok")
    return data


def elite_subject_ids(path: Path | None = None) -> list[str]:
    return list(load_elite_manifest(path).get("subject_ids", []))
