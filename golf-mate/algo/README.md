# Golf Mate Algorithm Core (P0)

Hardware-agnostic golf swing analysis from a single wrist / glove-card 6-axis IMU.

## Scope

| Tier | Status | Content |
|------|--------|---------|
| **P0** | Implemented | Gated AHRS, phases, trajectory, wrist features, proxy diagnostics, analytic UT |
| **P1** | Reserved | Wrist→full-body mapping, MultiSenseGolf regression, Ferraris calib |
| **P2** | Reserved | Motion tokens / signatures, forward-dynamics teacher |

Research notes: [`../docs/research/`](../docs/research/).

## Install & test

```bash
cd golf-mate/algo
pip install -e ".[dev]"
pytest -q
```

## Math conventions

- Quaternion `[w, x, y, z]`, float64
- Gyro `rad/s`, accel `m/s^2`, gravity world `[0, 0, -9.80665]`
- Gyro integration: right-invariant body rates `q ← q ⊗ quat(ωΔt)`
- Static specific force: `a ≈ -Rᵀ g_world`

## Pipeline

```text
ImuPacket → rest bias → GolfGatedAHRS → phases
        → gravity remove + ZUPT trajectory → swing plane
        → wrist features → diagnostics → SwingReport
```

```python
from golfmate_algo.synth.analytic import planar_circular_swing
from golfmate_algo.pipeline import analyze_swing

syn = planar_circular_swing()
report = analyze_swing(syn.packet)
print(report.features.rhythm, [f.code for f in report.findings])
```

## Honesty

Single-wrist P0 reports **proxy** metrics only. Absolute clubface / full kinematic sequence require P1+ sensing or learned mapping.
