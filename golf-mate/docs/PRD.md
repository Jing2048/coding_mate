# Golf Mate — 产品需求

> 状态：`in_progress` · 本轮核心 = **算法 P0 验证**（非 App）

## 产品一句话

下场可用的腕部（Apple Watch / 自研磁吸手套卡）生物力学 AI 助手：采集挥杆 IMU → 轨迹与发力序列分析 → 可解释改进建议。

## 本轮目标（算法 P0）

- [x] 行业 / 学术 / 开源调研归档 → [`docs/research/`](research/)
- [x] 硬件无关算法包 [`algo/`](../algo/)
- [x] 解析真值 + 合成挥杆严格 UT（`pytest` 全绿）
- [ ] P1：单腕→全身映射 + MultiSenseGolf 回归
- [ ] P2：运动签名 / 前向动力学
- [ ] App / Watch / 自研传感器固件（后续轮次）

## P0 交付能力

| 模块 | 说明 |
|------|------|
| GolfGatedAHRS | VQF 6D + 高动态加速度门控 |
| Phase | Address / Top / Impact / Finish |
| Trajectory | 去重力积分 + 事件 ZUPT + swing plane |
| Features | tempo / rhythm / peak ω / plane / closure 代理 |
| Diagnostics | 可解释代理规则（含 casting 等），禁止伪称绝对 Face |

## 非目标（本轮）

- 不做 App UI / iOS / Watch 工程
- 不做真实硬件联调
- 不声称厘米级全身角或绝对杆面角

## 验收

```bash
cd golf-mate/algo && pip install -e ".[dev]" && pytest -q
```

## 传感器路线（后续）

- Apple Watch：`CMBatchedSensorManager`（800 Hz accel / 200 Hz device motion）
- 自研磁吸手套卡：6 轴高 ODR、无线充电、与 Watch 共享 `SensorFrame` 契约
