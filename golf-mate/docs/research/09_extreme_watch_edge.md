# 极致 Watch 端模型与双轨链路

## 决策

Apple Watch 的高采样率与低延迟是两种不同的系统能力：

- `CMBatchedSensorManager`：800 Hz accel / 200 Hz Device Motion，约每秒批量
  交付，承担 Impact、完整算法精修，并从 Device Motion **抽稀**出约 100 Hz
  端上轨迹 / 触觉（不得再并行打开 `CMMotionManager` Device Motion）；
- `CMMotionManager`：仅用于 Series 5 / 高采样失败后的 100 Hz compat 回退。

因此采用双轨，而不是把 800 Hz 原始流强行实时传到 iPhone：

1. **Preview rail**：Watch 本地计算（batched 抽稀或 compat），`PreviewPacketV1` 尽快发送；
2. **Fidelity rail**：`PackedCaptureV2` 原子落盘，`transferFile` + ACK；
3. **Final rail**：Python `analyze_swing` 返回 64 点精修轨迹、高阶指标与质量门。

## 开源与行业依据

| 参考 | 借鉴 | 不照搬 |
|------|------|--------|
| `pavelshadrin/tennis-motion` | Workout + `CMBatchedSensorManager` 双流 | 不用消息流承载全部原始样本 |
| Apple WWDC23 Core Motion | 800 Hz Impact、200 Hz rotation、批量交付边界 | 不承诺批量 API 的挥杆中低延迟 |
| `MotionCollector` | 控制消息、可靠文件、ACK 生命周期 | 不用 JSON 作为生产原始格式 |
| `WatchHAR` / FormFit | 小模型端上推理与 Core ML 导出 | 不把未经验证的分类器当几何真值 |
| VQF / Fusion | 6D 姿态和嵌入式基线 | 完整高动态融合仍留在 final rail |
| `kinetic_codec` | delta-time、紧凑时序编码 | 不引入其代码或改变传感器有效精度 |

行业反馈分层：

- 挥杆中触觉 enqueue：P95 `<50 ms`；
- Watch 停杆轨迹/KPI：P95 `<1 s`；
- iPhone 预览：P95 `<2 s`；
- 高阶分析：异步，不阻塞下一杆。

## 已实现协议

### `PreviewPacketV1`

- `GMPV` magic、版本、session UUID、capture mode；
- 64 个 address-relative `Float32` XYZ 点；
- confidence、quality、transition-rush、推理 P95；
- CRC-32；
- `sendMessageData`，不可达时 `transferUserInfo` 排队。

### `PackedCaptureV2`

- `GMPC` magic、版本化固定 header；
- base timestamp + `uint32` 微秒 delta；
- `Float32` accel/gyro/gravity/userAccel/quaternion 平面数组；
- 可附带 64 点 preview；
- CRC-32；Watch 持久化到 iPhone ACK 后才删除；
- Python v1 JSON / v2 binary 进入同一个 `WatchCapture`。

## 端模型

`edge-trajectory-v1` 以完整 Python pipeline 为 teacher，固定输入 100 Hz
gyro + accel，输出：

- Address / Top / Impact / Finish 归一化事件；
- 64 点领先腕轨迹；
- confidence；
- transition-rush。

当前 Core ML student 是确定性 128 维 tanh random-feature + ridge 输出的非线性
蒸馏模型，模型很小，已生成
`edge_trajectory_v1.mlpackage`。Watch 将 student 作为有界修正（最大 30% blend），
因果姿态几何仍提供稳定底座；未完成 optical-aligned 真机门之前，UI 必须显示
`PROVISIONAL`，完整 Python 结果始终覆盖端上预览。

固定独立 synthetic seed 的 shipped-artifact 门为：领先腕轨迹 teacher RMSE
mean ≤10 cm / P95 ≤17 cm，相位平均绝对时间误差 P95 ≤40 ms。该门只证明蒸馏
没有明显失真，不能替代真实 Watch + optical release gate。

触觉仅针对单腕可观测的高置信 transition rush，练习采集中每杆最多一次；不宣称
单 Watch 能直接测出 HackMotion 双节点级腕屈伸。

## 风险与真机硬门

1. Series 8+ **不得**同时打开 `CMMotionManager` 与 `CMBatchedSensorManager`
   Device Motion。真机上双开会让 batched 轨立刻失败（表现为一点「开始采集」就
   「出错」）。Preview / 触觉改从 batched Device Motion 抽稀到约 100 Hz；若高采
   样启动仍失败且几乎无样本，自动回退到 100 Hz compat，不得直接中断整杆。
2. Series 5 只运行 100 Hz rail（单路 Device Motion，加速度由
   gravity+userAcceleration 合成；HK workout 用 indoor 且失败不阻断采集），
   Impact 精度不得标成 high-rate。
3. 模型发布门必须包含独立生成器、真实 Watch、optical-aligned 数据，不能只看训练
   合成集。
4. Packed v2 相对 Double JSON 的量化误差必须低于传感器噪声且不改变现有算法预算。
5. 未 ACK capture 零删除，重复 transfer 必须按 session 幂等。
