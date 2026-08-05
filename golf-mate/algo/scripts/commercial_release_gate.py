#!/usr/bin/env python3
"""Print a machine-readable commercial release / device-gold readiness report.

Default target is the in-repo empty ``data/watch_gold/manifest.json`` (not ready).
Exit code 0 always on successful evaluation; use ``--require-ready`` to exit 1
when commercial_ready is false (for release checklists).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from golfmate_algo.bench.commercial_release_gate import (
    evaluate_commercial_release_gate,
)
from golfmate_algo.bench.datasets.watch_gold import (
    DEFAULT_MANIFEST,
    validate_and_summarize,
)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
        help="path to watch_gold manifest.json",
    )
    p.add_argument(
        "--root",
        type=Path,
        default=None,
        help="catalog root for relative capture paths (default: manifest parent)",
    )
    p.add_argument(
        "--json",
        action="store_true",
        default=True,
        help="print JSON report (default)",
    )
    p.add_argument(
        "--summary-only",
        action="store_true",
        help="print validation+stratification summary without commercial gate",
    )
    p.add_argument(
        "--skip-hash",
        action="store_true",
        help="skip sha256 verification (debug only)",
    )
    p.add_argument(
        "--skip-load",
        action="store_true",
        help="skip packed/json load (schema+hash only)",
    )
    p.add_argument(
        "--require-ready",
        action="store_true",
        help="exit 1 if commercial_ready is false",
    )
    args = p.parse_args(argv)

    root = args.root
    if root is None:
        root = args.manifest.parent

    if args.summary_only:
        payload = validate_and_summarize(
            args.manifest,
            root=root,
            verify_hash=not args.skip_hash,
            load_capture=not args.skip_load,
        )
    else:
        payload = evaluate_commercial_release_gate(
            args.manifest,
            root=root,
            verify_hash=not args.skip_hash,
            load_capture=not args.skip_load,
        )

    print(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False))

    if args.require_ready and not payload.get("commercial_ready", False):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
