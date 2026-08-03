# Golf Mate — 产品需求

> 状态：`in_progress` · 算法 P0 已验证；Apple Watch E2E 见
> [`PRD_APPLE_WATCH.md`](PRD_APPLE_WATCH.md)

## 产品一句话

下场可用的腕部（Apple Watch / 自研磁吸手套卡）生物力学 AI 助手：采集挥杆 IMU → 轨迹与发力序列分析 → 可解释改进建议。

## 本轮目标（算法 P0）

- [x] 行业 / 学术 / 开源调研归档 → [`docs/research/`](research/)
- [x] 硬件无关算法包 [`algo/`](../algo/)
- [x] 解析真值 + 合成挥杆严格 UT（`pytest` 全绿）
- [ ] P1：单腕→全身映射 + MultiSenseGolf 回归
- [ ] P2：运动签名 / 前向动力学
- [x] Apple Watch E2E 验证版（800/200 Hz 双流 + iPhone 文件传输）
- [ ] 自研传感器固件

## P0 交付能力

| 模块 | 说明 |
|------|------|
| GolfGatedAHRS | VQF 6D + 高动态加速度门控 |
| Phase | Address / Top / Impact / Finish |
| Trajectory | 去重力积分 + 事件 ZUPT + swing plane |
| Features | tempo / rhythm / peak ω / plane / closure 代理 |
| Diagnostics | 可解释代理规则（含 casting 等），禁止伪称绝对 Face |

## 非目标（本轮）

- 不做真实硬件联调
- 不把 PCR 推断的杆面/腕角伪称为光学或 MEMS 金标实测（高阶量以 `INFERRED` 输出）

## 验收

```bash
cd golf-mate/algo && pip install -e ".[dev]" && pytest -q
```

## 传感器路线（后续）

- Apple Watch：`CMBatchedSensorManager`（800 Hz accel / 200 Hz device motion）
- 自研磁吸手套卡：6 轴高 ODR、无线充电、与 Watch 共享 `SensorFrame` 契约
