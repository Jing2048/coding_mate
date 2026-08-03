# 算法对抗验证结果：与行业/文献最佳实践对标

> **零信任准确 benchmark（主报告）**：[06_zero_trust_benchmark.md](./06_zero_trust_benchmark.md) · [`benchmark_zero_trust.json`](./benchmark_zero_trust.json)  
> 同构仿真上界（不可单独引用为产品精度）：[05_benchmark_report.md](./05_benchmark_report.md)  
> 复现：`python -m golfmate_algo.bench.evaluate --mode full`  
> 回归：`pytest tests/test_adversarial.py tests/test_zero_trust.py tests/test_evaluate.py`

**引用规则：** 对外精度数字只用 `cross_multibody` / `external_multisense`；`isomorphic_analytic` 仅作上界。

## 准确仿真头条（cross_multibody E2E，consumer）

| 指标 | mean [95% CI] |
|------|---------------|
| 姿态 | **2.54°** [1.93, 3.66] |
| Impact | **5.62 ms** [4.84, 6.41] |
| 腕部位置 | **23.7 cm** [22.4, 25.2]（诚实异构；同构上界约 5 cm） |
| 会话姿态 (~24s) | **5.87°** vs gyro-only ~52° |

MultiSenseGolf（mocap-derived IMU，n=30）：姿态 ~45°、位置 ~46 cm；Impact 因无真实击球冲击不可硬闸。详见 06。

---

## 附录：同构评测方法（历史 / 上界）

| 要素 | 做法 |
|------|------|
| 真值 | 解析速度剖面（高斯基）驱动的倾斜平面圆周挥杆，角度/角速度/角加速度**全闭式**，加速度与位置二阶一致 |
| 传感器 | 完整误差模型：ARW/VRW、常值零偏 + 随机游走、标度因子、非正交、失准、g 敏感、**饱和**、量化、安装谐振、抖动、丢包 |
| 等级 | `ideal` / `consumer`（BMI270·ICM-42688 级）/ `harsh`（松散手套卡、陀螺 1000°/s 截止、丢包） |
| 场景 | 单杆（4 变体 × 倾角 × seeds）**与** 多杆会话（8 杆 / ~24 s） |
| 公平性 | 6 轴无法观测航向，故按**全局最优 yaw 投影**对齐后再比误差；E2E 位置同样做 yaw 对齐 |
| 统计 | **按挥杆均值**聚合 + **百分位 bootstrap 95% CI**（避免把时序样本当独立样本） |
| 消融 | 门控项（α / ω / rest）与轨迹方法（杠杆解 / ZUPT / 姿态 oracle） |
| 退化 | 消费级误差幅度 ×{0, 0.5, 1, 1.5, 2, 3} |

---

## 2. 端到端头条（`analyze_swing`）

| 条件 | 姿态 ° | Impact ms | 位置 cm | 失败 |
|------|-------:|----------:|--------:|-----:|
| **ideal** | **1.14** [1.10, 1.19] | 5.00 | **1.63** | 0 |
| **consumer** | **5.71** [3.44, 8.92] | **6.09** [5.47, 6.88] | **4.94** [3.81, 6.79] | 0 |
| **harsh** | 18.88 [12.80, 25.85] | 5.62 | 16.77 | 0 |

---

## 3. 姿态估计：7 种方法对抗（按挥杆均值 °）

### 3.1 单次挥杆（全时段）

| 算法 | ideal | consumer | harsh |
|------|------:|---------:|------:|
| **gated_adaptive（本项目）** | 1.14 | **5.71** | 18.88 |
| gyro_only | **0.62** | 9.17 | 27.69 |
| gyro_only + rest-bias | 1.18 | 9.57 | 28.04 |
| Madgwick | 3.24 | 9.31 | 25.67 |
| Mahony | 13.02 | 15.41 | 23.29 |
| EKF | 17.49 | 16.44 | 16.13 |
| Complementary | 18.17 | 20.04 | 26.09 |

### 3.2 多杆会话（~24 s）

| 算法 | consumer | harsh |
|------|---------:|------:|
| **gated_adaptive** | **5.87** [5.54, 6.20] | **6.41** |
| EKF | 9.68 | 11.07 |
| Mahony | 14.15 | 36.83 |
| Madgwick | 14.52 | 41.54 |
| Complementary | 17.88 | 43.61 |
| gyro_only + rest-bias | 47.66 | 62.09 |
| gyro_only | 51.69 | 76.55 |

### 3.3 结论

1. **单杆里纯积分仍极强**（ideal 0.62°），但 consumer 噪声下 **gated 以 5.71° 反超 gyro_only 的 9.17°**（CI 重叠边缘，种子方差大）。
2. **会话尺度上纯积分崩溃**（~52°），gated 稳定在 **5.9°** 且 CI 极窄 —— 这是产品选型依据。
3. 退化曲线：会话上 scale 0→3 时 gated 仅 4.5°→5.7°，gyro_only 14°→96°。

---

## 4. 动力学门控消融

| 变体 | 单杆 consumer ° | 会话 consumer ° |
|------|----------------:|----------------:|
| full_gate+rest（产品） | 5.71 | **5.87** |
| always_open | **24.70**（下杆 47.8） | 10.09 |
| gyro_only | 9.59 | **60.20** |

**全程信加速度是灾难**；会话上必须有门控。短窗内 `a_only`/`no_alpha`/`full_gate` 的 CI 重叠——角加速度项的价值由对抗 UT（顶点门关闭）与长窗稳健性共同锁定，而非单杆 mean 差值。

---

## 5. 轨迹重建

| 方法 | ideal | consumer | harsh |
|------|------:|---------:|------:|
| **lever_arm** | **1.90** | **5.07** | **16.47** |
| dead_reckon + ZUPT | 4.68 | 17.43 | 52.16 |
| lever_arm + oracle R | 1.76 | 1.76 | 1.76 |

消费级下杠杆解约 **3.4×** 优于二次积分。oracle 姿态隔离后只剩 1.76 cm —— 说明 consumer 的 ~5 cm 主要来自姿态误差传导，而非杠杆模型本身。

> **诚实声明**：合成挥杆满足刚性旋转假设。文献（Sci. Rep. 2024）真人单腕全相位约 **17 cm**。残差 `residual_rms_m_s2` 超阈时管线回退 ZUPT。

---

## 6. 事件检测

| 事件 | ideal | consumer | harsh |
|------|------:|---------:|------:|
| Address | 0.0 | 8.9 | 30.5 |
| Top | 0.0 | 7.8 | 28.9 |
| **Impact** | 5.0 | **6.1** | **5.6** |
| Finish | 0.0 | 10.0 | 47.2 |

单位 ms。对标 Kim & Park (Sensors 2020) 单 IMU 事件 MAE **5–92 ms**；本方法 consumer 全部 ≤ 10 ms 且**无需训练**。

---

## 7. 对抗与退化测试

`tests/test_adversarial.py` + `tests/test_evaluate.py` 覆盖生成器自洽、门控、姿态/轨迹/事件预算、NaN/丢包退化，以及评测套件冒烟。

---

## 8. 与行业实践的定位

| 能力 | 行业参考 | 本项目 P0 |
|------|----------|-----------|
| 冲击时刻 | Golfshot Swing ID | 高通瞬态，consumer **6.1 ms** @200 Hz |
| 相位/节奏 | Blast、Garmin TruSwing | Address/Top/Impact/Finish，≤10 ms |
| 腕角语言 | HackMotion | 相对 address 的代理量，**不伪称绝对杆面角** |
| 全身序列 | Sportsbox、Xsens | 单节点不可观测，显式降级为腕部代理 |
| 轨迹 | Sci. Rep. 2024 ~17 cm | 刚性杠杆解，合成上界 ~5 cm；真实需实测闸门 |

---

## 9. 尚未由仿真关闭的风险

1. 软组织/手套滑动的真实统计  
2. 真实击球冲击的非线性与传感器恢复时间  
3. 旋转中心平移导致的刚性假设失效程度  
4. 个体解剖差异与左右手  
5. 真实磁畸变（P0 默认不用磁强计）

P0 证明的是**算法正确性与相对优劣**，不是**测量完备性**。
