# Extreme algo: bottleneck → research → upgrades

## Bottlenecks (full golden set)

| Rank | Failure mode | Evidence |
|------|----------------|----------|
| 1 | **Address/Finish ZUPT anchors** | Oracle phases → consumer wrist pos **~13 cm**; detected (broken quiet-from-top) → **~75 cm**. Impact/top were already fine. |
| 2 | **Casting in citeable mean** | 25% of `cross_multibody` cases are club-mount casting; mixing them into product MAE inflated position ~3–4×. |
| 3 | **Casting lever collapse** | Distal mount → lever radius ~0.2 m, residual ≫12; open-loop DR span ~20 m under consumer noise. |
| 4 | **Impact early spike (casting)** | Global HF argmax picks release shock before ball strike. |

MultiSense elite Sub13–24 are present locally (eval gate only; mocap-derived IMU, no collision shock). WIT-KinNet remains contract-ready / unavailable.

## Research inputs

1. **Kim & Park, SciRep 2024** ([doi:10.1038/s41598-024-59949-w](https://doi.org/10.1038/s41598-024-59949-w)) — wrist IMU @ 200 Hz; ADD/BST/FIN ≈ zero wrist speed; piecewise linear velocity ZUPT; virtual circle on 3D swing plane; FIN projected onto circle via accel-bias analogue → ~**17 cm** whole-swing.
2. **WIT-KinNet, arXiv:2606.22876** — signed-log compression + wrist→full-body inference (already mirrored in high-order PCR / AHRS features); dataset not public.
3. **MultiSenseGolf** — elite Sub13–24 as external honesty gate (not product MEMS).

## Upgrades shipped (`cursor/extreme-algo-916a`)

### Events (`segmental.py`)
- Impact: coarse Top → search post-top; **latest significant HF peak** (casting-robust).
- Address: hysteresis-from-motion primary; SciRep walk-back only if hysteresis collapses toward Top.
- Finish: first quiet onset; **deepen** to ω argmin over ~0.5 s when onset is still shallow vs address quiet floor.

### Trajectory (`hybrid.py`)
- SciRep soft plane/circle blend + **finish-on-circle** quadratic correction.
- Rigidity-fail (casting): **club-scale prior radius ≈ 1.0 m** along lever direction + plane closure (not pure DR).

### Gates (`gates.py` / `evaluate.py`)
- Product budgets on **`consumer_wrist`** (exclude casting labels).
- Casting stays on `casting_pathology` (120 cm / 50 ms).

## Citeable quick check (dev seeds)

| Stratum | ori ° | impact ms | pos cm | Budget |
|---------|------:|----------:|-------:|--------|
| `consumer_wrist` | ~2.2 | ~5 | ~14 | 8° / 20 ms / 17 cm |
| `casting_pathology` | ~2.6 | ~10 | ~30 | 40° / 50 ms / 120 cm |
| planar ideal events (worst) | — | — | — | ≤20 ms (measured ~5 ms) |

Impact selection: post-peak thr independent of early-release HF max; near-peak-|ω| first, else best post-peak collision; else kinematic proxy (clean 1 kHz without ball shock).

Honesty: MultiSense / CMU / optical twin remain soft external gates; WIT unavailable; high-order metrics stay `INFERRED`.
