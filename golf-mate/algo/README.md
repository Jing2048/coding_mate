# Golf Mate Algorithm Core (P0)

Hardware-agnostic golf swing analysis from a single wrist / glove-card 6-axis IMU,
validated by head-to-head benchmarking against classical baselines rather than by
inspection.

Results: [`../docs/research/06_zero_trust_benchmark.md`](../docs/research/06_zero_trust_benchmark.md)
(summary: [`../docs/research/04_benchmark.md`](../docs/research/04_benchmark.md)).

## Install and test

```bash
cd golf-mate/algo
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
python scripts/fetch_multisense.py --max-swings 30   # optional external gate
python scripts/seal_holdout.py
python -m golfmate_algo.bench.evaluate --mode full   # zero-trust dual-track report
```

## Conventions

- Quaternion `[w, x, y, z]`, float64, body to world
- Gyro `rad/s`, accel `m/s^2`, world gravity `[0, 0, -9.80665]`
- At rest `a_meas = -R^T g_world`
- Integration `q <- q (x) quat(w dt)` (right-invariant body rates)

## Pipeline

```text
ImuPacket (device mount frame)
  -> devices.normalize_packet  # extrinsic + handedness/wrist -> canonical lead-right
  -> dual-path / CROP-lite (optional)
  -> address init + GatedAdaptive AHRS
  -> segmental phases
  -> hybrid | lever_arm | dead_reckon trajectory
  -> wrist features + biomech proxies + ideal reference band score
  -> SwingReport (+ export.SwingFeatureVector for future Core ML)
```

```python
from golfmate_algo.synth.analytic import planar_circular_swing
from golfmate_algo.pipeline import analyze_swing
from golfmate_algo.export import export_feature_vector
from golfmate_algo.types import Handedness

syn = planar_circular_swing(handedness=Handedness.LEFT)
report = analyze_swing(syn.packet)
print(report.features.rhythm, report.meta["frame"], export_feature_vector(report).version)
```

## Canonical anatomical frame

After normalization: `handedness=RIGHT`, `wrist=LEAD`, identity extrinsic.

| Axis | Meaning |
|------|---------|
| +X | Distal along forearm |
| +Y | Ulnar → radial (mirrored for lefties) |
| +Z | Completes right-handed triad |

Adapters (Watch / glove) fill the **device** frame; algo owns mirroring.

## Modules

| Path | Role |
|------|------|
| `devices/` | Adapter protocol, `normalize_packet`, Watch/glove specs |
| `math/so3.py` | Quaternion / SO(3) algebra |
| `ahrs/suite.py` | Comparable filters + `DynamicsGate` |
| `events/segmental.py` | Physics-anchored phase detection |
| `traj/hybrid.py` | Default trajectory (varying centre + constraints) |
| `traj/lever_arm.py` | Rigid-rotation baseline |
| `reference/` | Ideal kinematic bands + MultiSense elite manifest helpers |
| `export/` | Versioned `SwingFeatureVector` / Core ML contract |
| `synth/` | Analytic / multibody truth generators |
| `bench/` | Zero-trust evaluation |

## Headline numbers

| Metric | ideal | consumer | harsh |
|--------|------:|---------:|------:|
| Orientation, single swing (deg) | 1.15 | 3.76 | 11.59 |
| Orientation, 24 s session (deg) | - | 6.05 | 6.46 |
| Wrist position (cm) | 2.00 | 4.01 | 13.97 |
| Impact timing (ms) | 5.0 | 6.3 | 5.4 |

## Honesty

Single-wrist P0 reports proxy metrics with stated uncertainty. Absolute clubface
angle, true club path and full-body kinematic sequence are not observable from
one wrist node and are deliberately not claimed. The lever-arm trajectory numbers
are an upper bound: the synthetic swing satisfies the rigid-rotation assumption
exactly, and the solver reports its own residual so the assumption can be checked
on real data.
