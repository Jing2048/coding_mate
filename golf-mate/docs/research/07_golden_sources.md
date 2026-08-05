# Golden source catalog (Golf Mate)

| Rank | Source | Commercial eval | Honesty |
|-----:|--------|:---------------:|---------|
| 0 | **Watch device-gold** (`data/watch_gold`) | **required for commercial_ready** | Real Watch MEMS — catalog empty in-repo; never substitute synth |
| 1 | MultiSenseGolf | algo CI / distribution | External human motion distribution; NOT wrist MEMS noise/mount |
| 2 | CMU Subject 64 golf mocap | algo CI | Real human golf kinematics; IMU is synthetic from mocap (like MultiSense) |
| 3 | cross_multibody robust regimes | algo CI | Citeable cross-generator; still synthetic — not tour MEMS |
| 4 | SciRep 2024 Kim & Park protocol | no / pending | Best published single-wrist MEMS protocol; raw not public — CI uses in-house optical-aligned synth twin at 200 Hz |
| 5 | WIT-KinNet 2026 | no / pending | Highest product-fit when released; chase author share |

## 1. MultiSenseGolf

- License: CC0 1.0
- Signals: PN 21-bone mocap-derived wrist IMU (not raw MEMS)
- GT: Joint kinematics + annotated impact + launch monitor
- Scale: 24 subjects / 1557 swings; local Sub07 + elite Sub13 (Sub13–24 in manifest)
- Rate: Irregular PN timestamps → fixed-grid resample in adapter
- Integration: bench/datasets/multisense.py + strata (elite / high club-speed); scripts/fetch_multisense.py --elite
- URL: https://doi.org/10.7910/DVN/LCCLLW
- Honesty: External human motion distribution; NOT wrist MEMS noise/mount

## 2. CMU Subject 64 golf mocap

- License: Free for research & commercial products (do not resell mocap)
- Signals: Synth wrist IMU via ASF/AMC FK → body ω + specific force
- GT: Optical mocap joint orientations @ 120 Hz
- Scale: ~30 swing/putt trials, one subject (2003)
- Rate: 120 Hz native
- Integration: bench/datasets/cmu64.py
- URL: http://mocap.cs.cmu.edu/search.php?subjectnumber=64
- Honesty: Real human golf kinematics; IMU is synthetic from mocap (like MultiSense)

## 3. cross_multibody robust regimes

- License: In-house MIT synth
- Signals: Independent 4-link multibody + MEMS error model
- GT: Analytic segment quats / positions / event indices
- Scale: pro sway/lift, casting club-mount, fs∈{50,100}, clip, lefty
- Rate: Configurable (default 200 Hz; fs-stress lower)
- Integration: bench/harness.build_cases_robust_golden
- URL: in-repo
- Honesty: Citeable cross-generator; still synthetic — not tour MEMS

## 4. SciRep 2024 Kim & Park protocol

- License: Paper open; raw data on request
- Signals: Bosch wrist MEMS ±16g/2000dps @ 200 Hz vs optical
- GT: Optical markers on IMU / arm / club
- Scale: 20 RH golfers; 389 usable swings; in-house 200 Hz protocol twin until raw lands
- Rate: 200 Hz
- Integration: bench/golden/scirep_budgets.py + bench/datasets/optical_aligned.py (protocol twin)
- URL: https://doi.org/10.1038/s41598-024-59949-w
- Honesty: Best published single-wrist MEMS protocol; raw not public — CI uses in-house optical-aligned synth twin at 200 Hz

## 5. WIT-KinNet 2026

- License: Unknown until release
- Signals: Huawei Watch lead-wrist 9-axis @ 100 Hz
- GT: OMC 120 Hz full-body joints
- Scale: 36 golfers × clubs × amplitudes
- Rate: acc/gyro 100 Hz
- Integration: bench/datasets/wit_kinnet.py (contract + auto-ready loader)
- URL: https://arxiv.org/abs/2606.22876
- Honesty: Highest product-fit when released; chase author share


---

## Integration notes (Golf Mate)

### What we added to the zero-trust suite

1. **robust_golden synth tracks** — `pro_regime` / `casting_pathology` / `fs_stress` / `clip_stress` / `lefty_mirror` with hard budgets in `gates.py`.
2. **MultiSense elite stratum** — Sub13–24 via `multisense_elite_manifest.json`; local extracts: Sub13 + Sub19 (KPGA). Fetch: `scripts/fetch_multisense.py --elite`.
3. **MultiSense high club-speed stratum** (`club_speed ≥ 20 m/s`).
4. **CMU Subject 64** adapter (`bench/datasets/cmu64.py`) — commercial-friendly mocap → synth wrist IMU.
5. **WIT-KinNet contract** — `bench/datasets/wit_kinnet.py` auto-ready when watch+OMC dropped under `data/wit_kinnet/`.
6. **SciRep 2024 budgets** + **in-house 200 Hz optical-aligned twin** (`optical_aligned.py`) as CI-stable MEMS+optical guarantee until author shares land.
7. Dataverse file-ID map: `data/reference/multisense_dataverse_file_ids.json`.

### Still missing (next ROI)

- Full elite cohort pull (remaining Sub16–18,20–24) when storage/time allows.
- Real wrist MEMS golden (WIT-KinNet author share or SciRep raw on request).
- Do **not** put AMASS/WHAM/GolfDB-derived weights into commercial core without fresh licenses.

### Reproduce

```bash
cd golf-mate/algo && source .venv/bin/activate
python scripts/fetch_multisense.py --subject Sub13 --max-swings 20
python scripts/fetch_multisense.py --subject Sub19 --max-swings 15
python scripts/fetch_cmu64.py
python -c "from golfmate_algo.bench.datasets import optical_aligned as oa; oa.materialize()"
python -c "from golfmate_algo.bench.datasets import wit_kinnet as w; w.write_contract_readme()"
python -m golfmate_algo.bench.evaluate --mode full
pytest -q tests/test_robust_golden.py tests/test_zero_trust.py
```
