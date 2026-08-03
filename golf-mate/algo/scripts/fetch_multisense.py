#!/usr/bin/env python3
"""Fetch MultiSenseGolf documentation + subject archives (IMU streams only).

doi:10.7910/DVN/LCCLLW (CC0). Full subject archives are ~0.7–2 GB; elite
subjects (Sub13–24) are often split across multiple zips. This script downloads
Documentation.zip and requested subject zip(s), then extracts only HDF5 stream
files needed by the adapter.
"""

from __future__ import annotations

import argparse
import json
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
from golfmate_algo.reference.elite import elite_subject_ids

API = "https://dataverse.harvard.edu/api/access/datafile"
DOC_ID = 14058575

# Dataverse file IDs (scraped from doi:10.7910/DVN/LCCLLW listing, 2026-08).
# Elite subjects often ship as SubXX_1.zip + SubXX_2.zip (+ _3).
SUBJECT_FILE_IDS: dict[str, list[int]] = {
    "Sub01": [14058591],
    "Sub02": [14058577],
    "Sub03": [14058592],
    "Sub04": [14058576],
    "Sub05": [14058597],
    "Sub06": [14058602],
    "Sub07": [14058596],
    "Sub08": [14058584],
    "Sub09": [14058603],
    "Sub10": [14058578],
    "Sub11": [14058589],
    "Sub12": [14058586],
    "Sub13": [14058583],
    "Sub14": [14058588],
    "Sub15": [14058593],
    "Sub16": [14058605],
    "Sub17": [14058594, 14058598],
    "Sub18": [14058582, 14058590],
    "Sub19": [14058606, 14058573],
    "Sub20": [14058587, 14058601],
    "Sub21": [14058581, 14058604],
    "Sub22": [14058585, 14058580],
    "Sub23": [14058579, 14058600],
    "Sub24": [14058595, 14058574, 14058599],
}


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {url} → {dest}", flush=True)
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "golf-mate-fetch/1.0 (+https://github.com/Jing2048/coding_mate)",
            "Accept": "*/*",
        },
    )
    tmp = dest.with_suffix(dest.suffix + ".partial")
    with urllib.request.urlopen(req, timeout=600) as resp, tmp.open("wb") as out:
        total = resp.headers.get("Content-Length")
        total_i = int(total) if total and total.isdigit() else None
        done = 0
        while True:
            chunk = resp.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)
            done += len(chunk)
            if total_i and done % (32 * 1024 * 1024) < 1024 * 1024:
                print(f"  … {done / 1e6:.0f}/{total_i / 1e6:.0f} MB", flush=True)
    tmp.replace(dest)
    print(f"  done {dest.stat().st_size / 1e6:.1f} MB", flush=True)


def _fetch_subject(root: Path, subject: str, max_swings: int) -> list[Path]:
    ids = SUBJECT_FILE_IDS.get(subject)
    if not ids:
        raise KeyError(f"Unknown subject {subject}; known={sorted(SUBJECT_FILE_IDS)}")
    out = root / subject
    extracted: list[Path] = []
    remaining = max_swings
    for i, fid in enumerate(ids):
        if remaining <= 0:
            break
        suffix = "" if len(ids) == 1 else f"_part{i + 1}"
        zpath = root / f"{subject}{suffix}.zip"
        if not zpath.exists():
            # Prefer canonical Dataverse name when single-part
            alt = root / f"{subject}.zip" if len(ids) == 1 else zpath
            if len(ids) == 1 and alt.exists():
                zpath = alt
            else:
                _download(f"{API}/{fid}", zpath)
        paths = extract_subject_imu(zpath, out, max_swings=remaining)
        extracted.extend(paths)
        remaining = max_swings - len({p.parent.name for p in extracted})
        print(
            f"  {subject} part {i + 1}/{len(ids)}: +{len(paths)} hdf5 "
            f"(swings kept≈{max_swings - remaining}/{max_swings})",
            flush=True,
        )
    return extracted


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    p.add_argument(
        "--subject",
        default=None,
        help="subject archive to fetch (e.g. Sub07, Sub13). Ignored with --elite.",
    )
    p.add_argument(
        "--elite",
        action="store_true",
        help="fetch all elite subjects from multisense_elite_manifest.json",
    )
    p.add_argument(
        "--elite-priority",
        default="Sub13,Sub19,Sub23",
        help="comma subjects to fetch first when --elite (default: compact then pros)",
    )
    p.add_argument("--max-swings", type=int, default=25)
    p.add_argument("--skip-subject", action="store_true")
    p.add_argument(
        "--write-id-map",
        action="store_true",
        help="write SUBJECT_FILE_IDS JSON under data/reference/",
    )
    args = p.parse_args()
    root: Path = args.root
    root.mkdir(parents=True, exist_ok=True)

    if args.write_id_map:
        ref = root.parent / "reference" / "multisense_dataverse_file_ids.json"
        # DEFAULT_ROOT is .../data/multisense → parent/reference
        ref = Path(__file__).resolve().parents[1] / "data" / "reference" / "multisense_dataverse_file_ids.json"
        ref.parent.mkdir(parents=True, exist_ok=True)
        ref.write_text(
            json.dumps(
                {"doi": DOI, "api": API, "doc_id": DOC_ID, "subjects": SUBJECT_FILE_IDS},
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"Wrote {ref}")

    doc_zip = root / "Documentation.zip"
    if not (root / "docs" / "Annotation Data.csv").exists():
        _download(f"{API}/{DOC_ID}", doc_zip)
        with zipfile.ZipFile(doc_zip, "r") as zf:
            zf.extractall(root / "docs")
        print("Extracted documentation")

    if not args.skip_subject:
        subjects: list[str]
        if args.elite:
            elite = elite_subject_ids()
            if not elite:
                print("Elite manifest empty — fix golfmate_algo.reference.elite path", file=sys.stderr)
                return 2
            priority = [s.strip() for s in args.elite_priority.split(",") if s.strip()]
            subjects = [s for s in priority if s in elite] + [
                s for s in elite if s not in priority
            ]
        elif args.subject:
            subjects = [args.subject]
        else:
            subjects = ["Sub07"]

        for sid in subjects:
            try:
                paths = _fetch_subject(root, sid, args.max_swings)
            except KeyError as e:
                print(str(e), file=sys.stderr)
                return 2
            print(f"Extracted {len(paths)} HDF5 swings → {root / sid}")

    st = dataset_status(root)
    print(
        f"doi:{DOI} ready={st['ready']} n_hdf5={st['n_hdf5_swings']} "
        f"subjects={st['subjects_extracted']}"
    )
    elite_local = [s for s in elite_subject_ids() if s in st.get("subjects_extracted", [])]
    print(f"elite_local={elite_local}")
    return 0 if st["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
