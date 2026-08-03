"""WIT-KinNet download stub (arXiv:2606.22876).

Highest product-fit golden (real smartwatch MEMS + OMC) — not publicly
released as of 2026-08. This module documents the hook so CI can light up
when/if authors publish a DOI.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

DEFAULT_ROOT = Path(__file__).resolve().parents[3] / "data" / "wit_kinnet"
ARXIV = "https://arxiv.org/abs/2606.22876"


def dataset_status(root: Path | None = None) -> dict[str, Any]:
    root = root or DEFAULT_ROOT
    return {
        "source": "wit_kinnet",
        "arxiv": ARXIV,
        "root": str(root),
        "ready": False,
        "reason": (
            "Dataset not publicly released; contact authors. "
            "When available, drop synced watch IMU + OMC JSON/HDF5 under data/wit_kinnet/."
        ),
        "product_fit": "highest_single_wrist_mems_plus_omc",
    }
