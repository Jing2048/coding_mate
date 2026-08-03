#!/usr/bin/env python3
"""Fetch CMU Subject 64 golf ASF/AMC into data/cmu64/raw."""

from __future__ import annotations

import argparse

from golfmate_algo.bench.datasets import cmu64


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--trials", type=str, default="01,02,03,04,05,06,07,08,09,10")
    args = p.parse_args()
    trials = [t.strip() for t in args.trials.split(",") if t.strip()]
    paths = cmu64.fetch_trials(trials=trials)
    st = cmu64.dataset_status()
    print(f"fetched {len(paths)} files; ready={st['ready']} n_amc={st['n_amc']}")
    print(st.get("license_note"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
