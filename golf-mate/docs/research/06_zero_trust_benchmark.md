# Golf Mate 零信任 Benchmark 报告

> protocol `golfmate-zt-v1` · mode `full` · `2026-08-03T08:39:52.119088+00:00` · 293.3s · gates **PASS**

## 可信度分层（必读）

| 轨道 | 含义 | 可否对外产品精度引用 |
|------|------|-------------------|
| isomorphic_analytic | 与杠杆解同构的解析平面 | **否**（上界） |
| cross_multibody | 独立多刚体生成器 | **可**（准确仿真） |
| violation_stress | 故意破坏刚性假设 | 测诚实度，非精度 |
| external_multisense | MultiSenseGolf 真人运动 | **可**（零信任运动分布） |

### 闸门备注
- cross_multibody impact MAE 5.62 ms (budget 40)
- session gated 5.87° vs gyro_only 51.69°
- violation residual 18.11 vs clean 5.16; invalid rate 0.0 vs 0.0
- external_multisense scored
- multisense (mocap-derived IMU) impact MAE 1144.1 ms — not hard-gated (no collision shock in stream); orientation 45.1°, position 46.1 cm

## 1. 准确仿真头条（cross_multibody / E2E）

| 条件 | 姿态 ° | Impact ms | 位置 cm | fallback |
|------|-------:|----------:|--------:|---------:|
| ideal | 8.81 [6.28, 11.49] | 4.84 [4.06, 5.62] | 26.89 [25.10, 28.89] | 0.00 [0.00, 0.00] |
| consumer | 2.54 [1.93, 3.66] | 5.62 [4.84, 6.41] | 23.72 [22.43, 25.16] | 0.00 [0.00, 0.00] |
| harsh | 10.57 [7.97, 13.54] | 8.28 [6.72, 10.00] | 15.16 [14.03, 16.36] | 0.00 [0.00, 0.00] |

## 2. 姿态对抗（cross_multibody，按挥杆均值 °）

| 算法 | ideal | consumer | harsh |
|------|------:|---------:|------:|
| complementary | 16.00 [14.04, 17.86] | 12.38 [11.63, 13.33] | 15.33 [13.87, 17.01] |
| ekf | 3.65 [3.32, 3.99] | 4.93 [4.49, 5.41] | 7.85 [7.09, 8.66] |
| gated_adaptive | 8.81 [6.38, 11.33] | 2.54 [1.94, 3.68] | 10.57 [7.92, 13.50] |
| gyro_only | 27.58 [18.84, 36.23] | 4.00 [2.12, 7.64] | 20.05 [13.25, 27.67] |
| gyro_only+restbias | 27.60 [18.91, 36.79] | 3.69 [1.82, 7.40] | 19.77 [12.54, 27.64] |
| madgwick | 24.65 [17.48, 32.04] | 5.09 [3.43, 8.30] | 18.12 [12.57, 24.54] |
| mahony | 12.08 [10.72, 13.47] | 9.47 [8.88, 10.13] | 12.46 [11.43, 13.57] |

## 3. 会话漂移（analytic session，~24 s）

| 算法 | consumer | harsh |
|------|---------:|------:|
| complementary | 17.88 [12.31, 24.87] | 43.61 [25.97, 64.51] |
| ekf | 9.68 [5.86, 14.62] | 11.07 [6.59, 17.09] |
| gated_adaptive | 5.87 [5.52, 6.20] | 6.41 [5.52, 7.46] |
| gyro_only | 51.69 [31.72, 72.62] | 76.55 [57.76, 92.71] |
| gyro_only+restbias | 47.66 [17.67, 82.82] | 62.09 [29.88, 95.20] |
| madgwick | 14.52 [9.58, 20.60] | 41.54 [22.51, 63.42] |
| mahony | 14.15 [10.21, 19.03] | 36.83 [19.55, 58.99] |

## 4. 事件检测（cross_multibody，ms）

| 事件 | ideal | consumer | harsh |
|------|------:|---------:|------:|
| address | 123.75 [117.66, 129.69] | 121.09 [115.47, 126.56] | 111.56 [106.25, 116.88] |
| top | 5.00 [5.00, 5.00] | 17.34 [10.00, 24.77] | 27.34 [15.70, 39.61] |
| impact | 4.84 [4.06, 5.62] | 5.62 [4.84, 6.41] | 8.28 [6.88, 10.00] |
| finish | 305.00 [292.02, 316.56] | 309.69 [296.72, 321.09] | 321.09 [308.44, 332.34] |

## 5. 轨迹与打假

| 方法 / 指标 | ideal | consumer | harsh |
|-------------|------:|---------:|------:|
| dead_reckon_zupt cm | 57.23 [40.10, 73.90] | 15.54 [10.74, 23.55] | 60.63 [46.27, 75.88] |
| lever_arm cm | 26.88 [25.06, 28.80] | 23.72 [22.33, 25.24] | 15.18 [14.01, 16.44] |
| residual clean | 4.98 [4.73, 5.23] | 5.16 [4.89, 5.42] | 6.25 [5.96, 6.52] |
| residual violate | 18.36 [18.02, 18.72] | 18.11 [17.83, 18.38] | 13.45 [13.16, 13.71] |
| invalid rate violate | 0.00 [0.00, 0.00] | 0.00 [0.00, 0.00] | 0.00 [0.00, 0.00] |

## 6. 同构上界（不可单独引用为产品精度）

| 条件 | 姿态 ° | Impact ms | 位置 cm |
|------|-------:|----------:|--------:|
| consumer | 5.71 [3.42, 8.92] | 6.09 [5.47, 6.80] | 4.94 [3.82, 6.82] |
| harsh | 18.88 [12.79, 25.63] | 5.62 [5.16, 6.25] | 16.77 [14.21, 19.83] |
| ideal | 1.14 [1.10, 1.19] | 5.00 [5.00, 5.00] | 1.63 [1.52, 1.74] |

## 7. 外部零信任（MultiSenseGolf）

状态：**ok** · n=30 · doi:`10.7910/DVN/LCCLLW` · Input IMU is derived from mocap joint kinematics (PN 21-bone), not a raw wrist MEMS stream. Motion distribution is external; sensor noise is not.

| 指标 | mean [CI] |
|------|----------:|
| 姿态 ° | 45.06 [40.79, 48.94] |
| Impact ms | 1144.14 [981.99, 1319.34] |
| 位置 cm | 46.07 [42.72, 49.27] |

## 8. 退化曲线（会话，gated vs gyro_only）

| scale | gated ° | gyro_only ° |
|------:|--------:|------------:|
| 0.0 | 4.59 | 21.49 |
| 0.5 | 4.55 | 28.50 |
| 1.0 | 4.69 | 51.49 |
| 1.5 | 4.90 | 80.80 |
| 2.0 | 5.11 | 100.85 |
| 3.0 | 5.58 | 107.68 |

## 9. 复现

```bash
cd golf-mate/algo && source .venv/bin/activate
python scripts/fetch_multisense.py --max-swings 30
python scripts/seal_holdout.py
python -m golfmate_algo.bench.evaluate --mode full
pytest -q
```
