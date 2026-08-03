"""MultiSenseGolf elite (pro / high expertise) subject selection."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_MANIFEST = (
    Path(__file__).resolve().parents[3] / "data" / "reference" / "multisense_elite_manifest.json"
)


def load_elite_manifest(path: Path | None = None) -> dict[str, Any]:
    p = path or DEFAULT_MANIFEST
    if not p.exists():
        return {
            "version": "multisense-elite-v1",
            "subject_ids": [],
            "status": "missing_manifest",
        }
    return json.loads(p.read_text(encoding="utf-8"))


def elite_subject_ids(path: Path | None = None) -> list[str]:
    return list(load_elite_manifest(path).get("subject_ids", []))
