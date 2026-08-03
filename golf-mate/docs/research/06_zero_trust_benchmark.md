# Golf Mate 零信任 Benchmark 报告

> protocol `golfmate-zt-v1` · mode `dev` · `2026-08-03T14:45:02.924545+00:00` · 61.5s · gates **PASS**

## 可信度分层（必读）

| 轨道 | 含义 | 可否对外产品精度引用 |
|------|------|-------------------|
| isomorphic_analytic | 与杠杆解同构的解析平面 | **否**（上界） |
| cross_multibody | 独立多刚体生成器 | **可**（准确仿真） |
| violation_stress | 故意破坏刚性假设 | 测诚实度，非精度 |
| external_multisense | MultiSenseGolf 真人运动 | **可**（零信任运动分布） |

### 闸门备注
- cross_multibody position MAE 12.02 cm (budget 17, consumer_wrist)
- cross_multibody impact MAE 5.00 ms (budget 20)
- cross_multibody orientation MAE 2.19° (budget 8)
- session gated 6.81° vs gyro_only 55.95°
- violation residual 19.74 vs clean 9.40; invalid rate 0.125 vs 0.0
- external_multisense scored
- multisense (mocap-derived IMU) kinematic-impact MAE 1000.4 ms (no collision shock); orientation 7.0°, position 93.5 cm
- external_multisense_elite scored n=10 subjects=['Sub13', 'Sub16', 'Sub17', 'Sub18', 'Sub19', 'Sub20', 'Sub21', 'Sub22', 'Sub23', 'Sub24'] (eval gate only, not in-product posture library)
- elite orientation 10.0°, position 58.697382268691214
- multisense high-speed stratum n=10 (club_speed ≥ 20.0 m/s)
- external_cmu64 scored n=5
- wit_kinnet: unavailable — Dataset not publicly released; contact authors. When available, drop synced watch IMU + OMC under /workspace/golf-mate/algo/data/wit_kinnet per contract wit-kinnet-contract-v1.
- optical_aligned (SciRep-protocol twin) n=4 @ 200.0 Hz
- optical_aligned ori=11.383321090183356 impact=106.25 pos=169.03880636937217 (SciRep ref pos 17.0 cm)
- pro_regime: ori=17.20133860788447, impact=3.0, pos=12.423505356882185 (budgets 40.0/40.0/35.0)
- casting_pathology: ori=2.5887712821849203, impact=10.0, pos=30.244790771053037 (budgets 40.0/50.0/120.0)
- fs_stress: ori=3.034853066929563, impact=115.0, pos=10.818807658681417 (budgets 20.0/150.0/40.0)
- lefty_mirror: ori=7.364852413688194, impact=10.0, pos=10.084090253960373 (budgets 15.0/300.0/35.0)
- clip_stress orientation 5.980443032934304

## 1. 准确仿真头条（cross_multibody / E2E）

| 条件 | 姿态 ° | Impact ms | 位置 cm | fallback |
|------|-------:|----------:|--------:|---------:|
| consumer | 4.38 [2.09, 8.72] | 6.25 [3.75, 8.14] | 18.64 [10.86, 26.54] | 0.25 [0.00, 0.50] |

## 2. 姿态对抗（cross_multibody，按挥杆均值 °）

| 算法 | ideal | consumer | harsh |
|------|------:|---------:|------:|
| complementary | — | 11.86 [10.90, 12.97] | — |
| ekf | — | 5.25 [4.40, 6.07] | — |
| gated_adaptive | — | 2.13 [1.95, 2.31] | — |
| gyro_only | — | 2.02 [1.86, 2.23] | — |
| gyro_only+restbias | — | 1.95 [1.81, 2.10] | — |
| madgwick | — | 3.53 [3.32, 3.77] | — |
| mahony | — | 9.63 [8.85, 10.35] | — |

## 3. 会话漂移（analytic session，~24 s）

| 算法 | consumer | harsh |
|------|---------:|------:|
| complementary | 10.03 [9.59, 10.46] | 20.27 [17.25, 23.29] |
| ekf | 8.64 [4.28, 13.01] | 8.95 [7.46, 10.45] |
| gated_adaptive | 6.81 [6.76, 6.86] | 7.17 [7.03, 7.30] |
| gyro_only | 55.95 [25.37, 86.54] | 66.34 [61.35, 71.33] |
| gyro_only+restbias | 58.87 [6.22, 111.52] | 58.83 [6.06, 111.60] |
| madgwick | 8.02 [7.03, 9.01] | 16.93 [16.59, 17.28] |
| mahony | 8.47 [8.21, 8.73] | 14.09 [11.96, 16.23] |

## 4. 事件检测（cross_multibody，ms）

| 事件 | ideal | consumer | harsh |
|------|------:|---------:|------:|
| address | — | 122.50 [111.25, 134.38] | — |
| top | — | 3.12 [1.88, 4.39] | — |
| impact | — | 6.25 [3.75, 8.12] | — |
| finish | — | 161.25 [74.98, 251.28] | — |

## 5. 轨迹与打假

| 方法 / 指标 | ideal | consumer | harsh |
|-------------|------:|---------:|------:|
| dead_reckon_zupt cm | — | 75.92 [10.77, 164.79] | — |
| hybrid cm | — | 16.71 [10.25, 23.50] | — |
| lever_arm cm | — | 35.39 [20.96, 55.79] | — |
| residual clean | — | 9.40 [4.64, 14.53] | — |
| residual violate | — | 19.74 [17.67, 21.80] | — |
| invalid rate violate | — | 0.12 [0.00, 0.38] | — |

## 6. 同构上界（不可单独引用为产品精度）

| 条件 | 姿态 ° | Impact ms | 位置 cm |
|------|-------:|----------:|--------:|
| consumer | 20.00 [8.05, 36.11] | 6.25 [5.00, 7.50] | 7.47 [4.42, 11.16] |
| consumer_wrist | 25.54 [10.08, 42.48] | 6.67 [5.00, 8.33] | 8.73 [4.64, 13.36] |

## 7. 外部零信任（MultiSenseGolf）

状态：**ok** · n=10 · doi:`10.7910/DVN/LCCLLW` · Input IMU is derived from mocap joint kinematics (PN 21-bone), not a raw wrist MEMS stream. Adapter converts Y-up→Z-up, derives body gyro from quaternion log (rad/s), and resamples irregular timestamps. Motion distribution is external; sensor noise is not.

| 指标 | mean [CI] |
|------|----------:|
| 姿态 ° | 7.03 [5.71, 8.60] |
| Impact ms | 1000.43 [825.24, 1109.21] |
| 位置 cm | 93.54 [84.84, 103.67] |

## 7b. MultiSenseGolf 高水平子集（评测闸，非产品示范库）

状态：**ok** · n=10 · subjects=['Sub13', 'Sub16', 'Sub17', 'Sub18', 'Sub19', 'Sub20', 'Sub21', 'Sub22', 'Sub23', 'Sub24'] · Input IMU is derived from mocap joint kinematics (PN 21-bone), not a raw wrist MEMS stream. Adapter converts Y-up→Z-up, derives body gyro from quaternion log (rad/s), and resamples irregular timestamps. Motion distribution is external; sensor noise is not. Elite subset is an eval gate only — not an in-product posture library.

| 指标 | mean [CI] |
|------|----------:|
| 姿态 ° | 10.05 [6.66, 15.55] |
| Impact ms | 897.17 [883.94, 912.12] |
| 位置 cm | 58.70 [51.78, 65.22] |

## 7c. MultiSense 高球速分层（club_speed ≥ 20 m/s）

状态：**ok** · n=10 · Input IMU is derived from mocap joint kinematics (PN 21-bone), not a raw wrist MEMS stream. Adapter converts Y-up→Z-up, derives body gyro from quaternion log (rad/s), and resamples irregular timestamps. Motion distribution is external; sensor noise is not. Club-speed stratum ≥ 20.0 m/s.

| 指标 | mean [CI] |
|------|----------:|
| 姿态 ° | 9.73 [6.63, 15.28] |
| Impact ms | 997.09 [951.82, 1055.46] |
| 位置 cm | 83.98 [71.48, 97.29] |
| Club speed m/s | 25.75 [23.78, 27.40] |

## 7d. CMU Subject 64（商用友好 mocap → synth IMU）

状态：**ok** · n=5 · CMU Subject 64 golf mocap → synth wrist IMU via ASF/AMC FK. Commercial-friendly license (do not resell mocap). Impact is kinematic (no ball). Not raw MEMS. Gate uses gyro-only orientation (SciRep-style) because mocap-diff accel is too noisy for tilt fusion.

| 指标 | mean [CI] |
|------|----------:|
| 姿态 ° | 77.47 [28.94, 126.01] |
| Impact ms | 320.00 [5.00, 898.33] |
| 位置 cm | 108.32 [97.53, 119.92] |

## 7e. Robust golden synth tracks

| Track | ori ° | impact ms | pos cm |
|-------|------:|----------:|-------:|
| pro_regime | 17.20 [1.26, 33.14] | 3.00 [3.00, 3.00] | 12.42 [9.71, 15.14] |
| casting_pathology | 2.59 [2.55, 2.63] | 10.00 [10.00, 10.00] | 30.24 [29.70, 30.79] |
| fs_stress | 3.03 [2.83, 3.18] | 115.00 [110.00, 120.00] | 10.82 [9.73, 11.91] |
| clip_stress | 5.98 [2.54, 9.42] | 10.00 [10.00, 10.00] | 9.18 [9.06, 9.29] |
| lefty_mirror | 7.36 [2.31, 12.42] | 10.00 [10.00, 10.00] | 10.08 [9.56, 10.61] |

## 7f. WIT-KinNet（最高产品契合；合约就绪检测）

状态：**unavailable** — Dataset not publicly released; contact authors. When available, drop synced watch IMU + OMC under /workspace/golf-mate/algo/data/wit_kinnet per contract wit-kinnet-contract-v1. · https://arxiv.org/abs/2606.22876
Drop contract: `wit-kinnet-contract-v1` under `data/wit_kinnet/`.

## 7g. In-house SciRep-protocol optical-aligned twin (200 Hz)

状态：**ok** · n=4 · fs=200.0 Hz · Synthetic protocol twin — optical GT from multibody markers; not Kim&Park raw MEMS and not tour Watch captures.

| 指标 | mean [CI] | SciRep/product ref |
|------|----------:|-------------------:|
| 姿态 ° | 11.38 [9.12, 14.01] | soft 12.0 / product 8.0 |
| Impact ms | 106.25 [57.50, 155.00] | product 20.0 |
| 位置 cm | 169.04 [87.98, 323.23] | SciRep 17.0 / product 17.0 |

## 9. 复现

```bash
cd golf-mate/algo && source .venv/bin/activate
python scripts/fetch_multisense.py --subject Sub13 --max-swings 20
python scripts/fetch_multisense.py --elite --elite-priority Sub13,Sub19,Sub23 --max-swings 15
python scripts/fetch_cmu64.py
python -c "from golfmate_algo.bench.datasets import optical_aligned as oa; oa.materialize()"
python -c "from golfmate_algo.bench.datasets import wit_kinnet as w; w.write_contract_readme()"
python -m golfmate_algo.bench.evaluate --mode full
pytest -q
```

Golden catalog: `docs/research/07_golden_sources.md`.
