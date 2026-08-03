#!/usr/bin/env python3
"""Fetch MultiSenseGolf documentation + one subject (IMU streams only).

doi:10.7910/DVN/LCCLLW (CC0). Full subject archives are ~0.7–2 GB; this script
downloads Documentation.zip and optionally one subject zip, then extracts only
HDF5 stream files needed by the adapter.
"""

from __future__ import annotations

import argparse
import sys
import urllib.request
import zipfile
from pathlib import Path

from golfmate_algo.bench.datasets.multisense import (
    DEFAULT_ROOT,
    DOI,
    dataset_status,
    extract_subject_imu,
)

API = "https://dataverse.harvard.edu/api/access/datafile"
# File IDs from the Dataverse listing
DOC_ID = 14058575
SUBJECT_IDS = {
    "Sub07": 14058596,  # smallest (~663 MB)
    "Sub01": 14058591,
}


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {url} → {dest}")
    urllib.request.urlretrieve(url, dest)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    p.add_argument("--subject", default="Sub07", help="subject archive to fetch")
    p.add_argument("--max-swings", type=int, default=25)
    p.add_argument("--skip-subject", action="store_true")
    args = p.parse_args()
    root: Path = args.root
    root.mkdir(parents=True, exist_ok=True)

    doc_zip = root / "Documentation.zip"
    if not (root / "docs" / "Annotation Data.csv").exists():
        _download(f"{API}/{DOC_ID}", doc_zip)
        with zipfile.ZipFile(doc_zip, "r") as zf:
            zf.extractall(root / "docs")
        print("Extracted documentation")

    if not args.skip_subject:
        sid = SUBJECT_IDS.get(args.subject)
        if sid is None:
            print(f"Unknown subject {args.subject}; known={list(SUBJECT_IDS)}", file=sys.stderr)
            return 2
        zpath = root / f"{args.subject}.zip"
        if not zpath.exists():
            _download(f"{API}/{sid}", zpath)
        out = root / args.subject
        paths = extract_subject_imu(zpath, out, max_swings=args.max_swings)
        print(f"Extracted {len(paths)} HDF5 swings → {out}")

    st = dataset_status(root)
    print(f"doi:{DOI} ready={st['ready']} n_hdf5={st['n_hdf5_swings']} subjects={st['subjects_extracted']}")
    return 0 if st["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
