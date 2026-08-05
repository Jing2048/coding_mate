# Golf Mate — 产品需求

> 状态：`in_progress` · 算法商用生物力学核心契约已落地；**真机 device-gold 目录为空，
> `commercial_ready=false`**（不得宣称商用生物力学就绪）。Apple Watch E2E 见
> [`PRD_APPLE_WATCH.md`](PRD_APPLE_WATCH.md)

## 产品一句话

下场可用的腕部（Apple Watch / 自研磁吸手套卡）生物力学 AI 助手：采集挥杆 IMU → 轨迹与发力序列分析 → 可解释改进建议。

## 本轮目标（商用生物力学核心 · 无产品壳）

- [x] 行业 / 学术 / 开源调研归档 → [`docs/research/`](research/)
- [x] 硬件无关算法包 [`algo/`](../algo/)
- [x] 解析真值 + 合成挥杆严格 UT（`pytest` 全绿）
- [x] `CommercialSwingReport v2` + measured/proxy/inferred/abstain 契约
- [x] 个人生物力学先验 + practice-loop / strategy **特征契约**（无 UI）
- [x] 真机 Watch 金标准 **合同 / 校验 / 商用发布闸**（空目录，fail-closed；claim 参考闸拆分 Impact/path/tempo）
- [ ] 真机 ≥30 杆跨 ≥2 人采集并过 `commercial_release_gate`（含独立 Impact + optical path + tempo）
- [ ] P1：单腕→全身映射 + MultiSenseGolf 回归（进行中的数据轨）
- [ ] P2：运动签名 / 前向动力学
- [x] Apple Watch E2E 验证版（800/200 Hz 双流 + iPhone 文件传输）
- [ ] 自研传感器固件
- [ ] 教练门户 / 订阅 / 下场产品壳（**明确非本轮**）

## 核心交付能力

| 模块 | 说明 | 状态 |
|------|------|------|
| GolfGatedAHRS | VQF 6D + 高动态加速度门控 + 不确定度 | 已有 |
| Phase | Address / Top / Impact / Finish（collision\|kinematic\|abstain） | 已有 |
| Trajectory | hybrid + 质量门；不过门则 abstain | 已有 |
| Features | tempo / rhythm / peak ω / plane（P0 可引用层） | 已有 |
| Diagnostics / Infer | 高阶为 `INFERRED`，校准弃权；禁伪称 Face 金标 | 已有 |
| CommercialSwingReport v2 | 真值 / 推断 / 个人 / practice / strategy 分栏 | 已有 |
| PersonalBiomechPrior | 相对个人基线 signed error + cue 契约 | 已有 |
| Device-gold + release gate | `data/watch_gold` 合同；空 catalog → 未就绪；metronome≠Impact/path 金标 | **合同已有，证据未到** |

## 非目标（本轮）

- 不做教练门户 / 订阅 / GPS SG 完整产品壳
- 不把 PCR / 推断杆面腕角伪称为光学或 MEMS 金标实测
- 不把算法合成闸（`cross_multibody` 等）改写成商用真机就绪
- 不在仓库写入伪造真机 capture 或将 `manifest.ready=true`

## 商用发布闸（诚实）

```bash
cd golf-mate/algo && python scripts/commercial_release_gate.py --json
# 预期（当前空目录）: commercial_ready=false
```

细则与声明矩阵：[`research/11_device_validation_protocol.md`](research/11_device_validation_protocol.md)、
痛点综合：[`research/10_commercial_pain_points.md`](research/10_commercial_pain_points.md)。

## 验收

```bash
cd golf-mate/algo && pip install -e ".[dev]" && pytest -q
# 聚焦真机闸:
pytest -q tests/test_watch_gold_commercial_gate.py
```

## 传感器路线（后续）

- Apple Watch：`CMBatchedSensorManager`（800 Hz accel / 200 Hz device motion）+ Series 5 compat
- 自研磁吸手套卡：6 轴高 ODR、无线充电、与 Watch 共享 `SensorFrame` 契约
