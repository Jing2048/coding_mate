# Golf Mate Algorithm Core (P0)

Hardware-agnostic golf swing analysis from a single wrist / glove-card 6-axis IMU,
validated by head-to-head benchmarking against classical baselines rather than by
inspection.

Results and reasoning: [`../docs/research/04_benchmark.md`](../docs/research/04_benchmark.md).

## Install and test

```bash
cd golf-mate/algo
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -q                                # 56 tests
python -m golfmate_algo.bench.harness    # full benchmark table
```

## Conventions

- Quaternion `[w, x, y, z]`, float64, body to world
- Gyro `rad/s`, accel `m/s^2`, world gravity `[0, 0, -9.80665]`
- At rest `a_meas = -R^T g_world`
- Integration `q <- q (x) quat(w dt)` (right-invariant body rates)

## Pipeline

```text
ImuPacket
  -> address init (robust quiet-window gravity alignment)
  -> GatedAdaptive AHRS (dynamics-gated tilt correction + rest bias)
  -> phase detection (high-pass impact, signed-rate zero crossing at top)
  -> lever-arm trajectory (drift-free) | dead-reckon + ZUPT (baseline)
  -> wrist features -> proxy diagnostics
  -> SwingReport
```

```python
from golfmate_algo.synth.analytic import planar_circular_swing
from golfmate_algo.pipeline import analyze_swing

syn = planar_circular_swing()
report = analyze_swing(syn.packet)
print(report.features.rhythm, [f.code for f in report.findings])
```

## Modules

| Path | Role |
|------|------|
| `math/so3.py` | Quaternion / SO(3) algebra, 6D rotation representation |
| `ahrs/suite.py` | Six comparable filters plus the `DynamicsGate` |
| `ahrs/init.py` | Address orientation, rest detection, gyro bias |
| `events/segmental.py` | Physics-anchored phase detection |
| `traj/lever_arm.py` | Rigid-rotation trajectory, truncated-SVD observability |
| `traj/constrained.py` | Joint bias / tilt least squares with event constraints |
| `traj/dead_reckon.py` | Classical integrate + ZUPT baseline |
| `synth/analytic.py` | Closed-form swing truth (Gaussian rate basis) |
| `synth/imu_model.py` | Full sensor error model |
| `synth/session.py` | Multi-swing session for drift benchmarking |
| `synth/multibody.py` | Multi-segment chain with kinematic sequence |
| `bench/harness.py` | Monte-Carlo benchmark |

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
