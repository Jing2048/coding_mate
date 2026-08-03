# Golf Mate 零信任 Benchmark 报告

> protocol `golfmate-zt-v1` · mode `full` · `2026-08-03T11:57:02.044492+00:00` · 324.7s · gates **PASS**

## 可信度分层（必读）

| 轨道 | 含义 | 可否对外产品精度引用 |
|------|------|-------------------|
| isomorphic_analytic | 与杠杆解同构的解析平面 | **否**（上界） |
| cross_multibody | 独立多刚体生成器 | **可**（准确仿真） |
| violation_stress | 故意破坏刚性假设 | 测诚实度，非精度 |
| external_multisense | MultiSenseGolf 真人运动 | **可**（零信任运动分布） |

### 闸门备注
- cross_multibody impact MAE 5.62 ms (budget 20)
- cross_multibody position MAE 16.60 cm (budget 17)
- cross_multibody orientation MAE 4.01° (budget 8)
- session gated 6.60° vs gyro_only 52.64°
- violation residual 18.10 vs clean 5.15; invalid rate 0.0 vs 0.0
- external_multisense scored
- multisense (mocap-derived IMU) kinematic-impact MAE 1030.3 ms (no collision shock); orientation 10.5°, position 76.5 cm
- external_multisense_elite unavailable: elite subjects not extracted locally; manifest lists none

## 1. 准确仿真头条（cross_multibody / E2E）

| 条件 | 姿态 ° | Impact ms | 位置 cm | fallback |
|------|-------:|----------:|--------:|---------:|
| ideal | 5.19 [3.01, 7.79] | 4.84 [4.06, 5.62] | 13.18 [12.09, 14.36] | 0.00 [0.00, 0.00] |
| consumer | 4.01 [2.51, 5.96] | 5.47 [4.53, 6.41] | 16.60 [14.86, 18.43] | 0.00 [0.00, 0.00] |
| harsh | 11.10 [8.75, 13.83] | 14.53 [7.50, 27.03] | 40.06 [36.83, 43.32] | 0.00 [0.00, 0.00] |

## 2. 姿态对抗（cross_multibody，按挥杆均值 °）

| 算法 | ideal | consumer | harsh |
|------|------:|---------:|------:|
| complementary | 16.14 [14.24, 18.10] | 12.38 [11.60, 13.24] | 15.39 [13.98, 16.95] |
| ekf | 3.62 [3.30, 3.97] | 4.92 [4.45, 5.42] | 7.82 [7.03, 8.61] |
| gated_adaptive | 9.03 [6.48, 11.43] | 2.68 [2.11, 3.75] | 10.77 [8.25, 13.69] |
| gyro_only | 28.05 [19.71, 36.16] | 4.01 [2.17, 7.56] | 20.22 [13.16, 27.55] |
| gyro_only+restbias | 28.08 [19.64, 36.63] | 3.76 [1.92, 7.33] | 20.04 [12.82, 27.98] |
| madgwick | 25.11 [17.95, 32.10] | 5.04 [3.42, 8.10] | 18.16 [12.41, 24.43] |
| mahony | 12.18 [10.75, 13.62] | 9.48 [8.90, 10.16] | 12.50 [11.45, 13.51] |

## 3. 会话漂移（analytic session，~24 s）

| 算法 | consumer | harsh |
|------|---------:|------:|
| complementary | 17.89 [12.31, 24.93] | 43.64 [25.99, 64.58] |
| ekf | 9.65 [5.85, 14.59] | 11.01 [6.62, 16.99] |
| gated_adaptive | 6.60 [6.29, 6.89] | 6.92 [6.01, 7.86] |
| gyro_only | 52.64 [32.12, 74.42] | 77.32 [58.38, 94.50] |
| gyro_only+restbias | 49.12 [16.45, 85.16] | 64.24 [30.99, 96.82] |
| madgwick | 14.59 [9.67, 20.83] | 41.79 [22.71, 64.40] |
| mahony | 14.18 [10.32, 19.12] | 37.02 [19.63, 59.49] |

## 4. 事件检测（cross_multibody，ms）

| 事件 | ideal | consumer | harsh |
|------|------:|---------:|------:|
| address | 123.75 [117.66, 130.00] | 121.09 [115.47, 126.72] | 111.56 [106.25, 117.03] |
| top | 5.00 [5.00, 5.00] | 17.34 [9.84, 24.84] | 27.34 [15.31, 39.53] |
| impact | 4.84 [4.06, 5.62] | 5.62 [4.69, 6.56] | 8.28 [6.72, 10.00] |
| finish | 305.00 [292.19, 316.88] | 309.69 [296.88, 321.41] | 321.09 [308.90, 332.50] |

## 5. 轨迹与打假

| 方法 / 指标 | ideal | consumer | harsh |
|-------------|------:|---------:|------:|
| dead_reckon_zupt cm | 58.20 [41.73, 74.50] | 15.70 [11.07, 23.53] | 61.62 [47.96, 76.88] |
| hybrid cm | 12.79 [11.74, 13.98] | 13.12 [11.60, 15.00] | 26.32 [24.00, 28.82] |
| lever_arm cm | 26.90 [25.14, 28.82] | 23.75 [22.38, 25.26] | 15.21 [14.10, 16.48] |
| residual clean | 4.98 [4.72, 5.23] | 5.15 [4.89, 5.42] | 6.25 [5.97, 6.52] |
| residual violate | 18.35 [18.01, 18.71] | 18.10 [17.82, 18.38] | 13.44 [13.15, 13.71] |
| invalid rate violate | 0.00 [0.00, 0.00] | 0.00 [0.00, 0.00] | 0.00 [0.00, 0.00] |

## 6. 同构上界（不可单独引用为产品精度）

| 条件 | 姿态 ° | Impact ms | 位置 cm |
|------|-------:|----------:|--------:|
| consumer | 21.93 [14.43, 29.95] | 6.09 [5.47, 6.88] | 11.79 [9.36, 14.33] |
| harsh | 32.84 [23.68, 42.92] | 6.09 [5.47, 6.88] | 32.66 [26.13, 40.34] |
| ideal | 13.96 [8.06, 21.20] | 5.00 [5.00, 5.00] | 7.90 [5.40, 10.59] |

## 7. 外部零信任（MultiSenseGolf）

状态：**ok** · n=30 · doi:`10.7910/DVN/LCCLLW` · Input IMU is derived from mocap joint kinematics (PN 21-bone), not a raw wrist MEMS stream. Adapter converts Y-up→Z-up, derives body gyro from quaternion log (rad/s), and resamples irregular timestamps. Motion distribution is external; sensor noise is not.

| 指标 | mean [CI] |
|------|----------:|
| 姿态 ° | 10.51 [6.10, 18.43] |
| Impact ms | 1030.28 [923.92, 1124.50] |
| 位置 cm | 76.49 [58.98, 99.27] |

## 7b. MultiSenseGolf 高水平子集（评测闸，非产品示范库）

状态：**unavailable** — elite subjects not extracted locally; manifest lists none

## 8. 退化曲线（会话，gated vs gyro_only）

| scale | gated ° | gyro_only ° |
|------:|--------:|------------:|
| 0.0 | 5.53 | 22.92 |
| 0.5 | 5.45 | 29.67 |
| 1.0 | 5.54 | 52.90 |
| 1.5 | 5.70 | 82.76 |
| 2.0 | 5.87 | 102.77 |
| 3.0 | 6.23 | 109.39 |

## 9. 复现

```bash
cd golf-mate/algo && source .venv/bin/activate
python scripts/fetch_multisense.py --max-swings 30
python scripts/seal_holdout.py
python -m golfmate_algo.bench.evaluate --mode full
pytest -q
```
