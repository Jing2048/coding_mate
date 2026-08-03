#!/usr/bin/env python3
"""Seal holdout fingerprints for the zero-trust protocol."""

from __future__ import annotations

import argparse
from pathlib import Path

from golfmate_algo.bench.protocol import DEFAULT_HOLDOUT_DIR, seal_holdout


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_HOLDOUT_DIR,
        help="directory for sealed holdout artifacts",
    )
    args = p.parse_args()
    manifest = seal_holdout(args.out)
    print(f"Sealed holdout → {args.out}")
    print(f"protocol={manifest['protocol_id']} sha256={manifest['artifact_sha256']}")
    for track, info in manifest["tracks"].items():
        print(f"  {track}: {info['n_cases']} cases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
