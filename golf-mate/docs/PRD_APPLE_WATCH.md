# Apple Watch E2E 验证版 PRD

> 状态：`in_progress` · 目标：真实 Watch 采集 → iPhone 原始文件 → Python 全算法回放

## 核心承诺

1. **采集尽量不打折，并兼容旧表**：
   - **高精度**（Series 8 / Ultra+）：`CMBatchedSensorManager` 原生 ~800 Hz accel + ~200 Hz Device Motion，完整保留；
   - **兼容**（Series 5 等）：`CMMotionManager` ~100 Hz 双流，同一 v2 契约；不在 Watch 上提前裁切或只上传摘要；
   - UI / metadata 明确标注 `high_rate` vs `compat`，不把兼容采样率冒充 800 Hz。
2. **算法不打折**：不移植一套缩水 Swift 算法。iPhone 收到原始双流后，POST 到 Mac
   上的 `watch_lab_server.py`，跑现有 Python `analyze_swing` 全链路；仅在 dense accel
   （≥400 Hz）时使用高精度 impact hint，AHRS/轨迹跑 Device Motion 网格。iPhone 直接展示完整分析结果。
3. **端上闭环**：100 Hz live rail 在 Watch 上生成 64 点领先腕预览轨迹与高置信
   transition-rush 单次触觉；停杆后目标 P95 <1 秒，不依赖手机或网络。
4. **表达不越界**：Watch 轨迹标记为 `PROVISIONAL`，不冒充已测杆头三维真值；
   clubface / X-factor 等继续标为 `INFERRED`。

## 用户故事

用户打开 Watch 的 Swing 页面，看到硬件能力（800/200 或兼容 ~100/100），点击「开始挥杆」：

1. App 请求 HealthKit 与 Motion 权限；
2. 启动 Golf workout（高频路径仍依赖 workout 解锁批量传感器）；
3. 100 Hz live rail 运行端模型，Watch 实时绘制 provisional 领先腕轨迹；
4. 高置信 transition rush 每杆最多触觉一次；
5. Watch 原子写入 CRC 保护的 `golfmate-watch-capture-v2`，并在 iPhone ACK 前保留；
6. Preview 走 `sendMessageData`（不可达时排队），原始文件走 `transferFile`；
7. iPhone 立即显示预览，同时 POST v2 到 Mac lab server；
8. 完整 Python 结果返回后，以 FINAL 轨迹及高阶分析覆盖预览。

## UI 方向：Precision Kinetics

调研依据：

- Apple HIG Workout：运动中“大字号、高对比、一眼可读”，控制应容易点击；
- watchOS 10+：用全屏状态渐变、材质层次和 Digital Crown 友好的单一任务页面；
- Apple WWDC23 Core Motion：800 Hz 专门用于短时冲击，200 Hz 用于沿重力旋转；
- 开源 `pavelshadrin/tennis-motion`：验证了 Workout + 双 async batch stream + WatchConnectivity。

设计语言：

- **专业**：深墨蓝/黑背景，cyan/mint 表示可信实时采集，红色只用于停止/错误；
- **现代**：圆角胶囊、材质 rate badge、数字等宽计时；
- **动态优雅**：Canvas motion field、光点沿挥杆弧线运行、低强度轴线；
- **克制**：一个主动作；采集中只显示 LIVE IMU / elapsed / 完成；
- **无障碍**：Reduce Motion 时停止动画；Always On 降到 1 Hz。

## 验收

- [x] 双流 JSON 契约与可靠文件传输；
- [x] Watch Swing 单页状态：idle / preparing / recording / processing / ready / error；
- [x] Python loader 保留 dense accel sidecar，Device Motion 对齐满足 `ImuPacket`；
- [x] 800 Hz impact hint 驱动完整 pipeline；
- [x] Series 5 兼容路径：~100 Hz 双流可跑完整 pipeline，且不伪造 high-rate impact hint；
- [x] 合成 E2E 测试覆盖采样率、单位、impact 精度、compat、坏输入；
- [x] `PreviewPacketV1` / `PackedCaptureV2`、CRC、v1 兼容与 Python round-trip；
- [x] `edge-trajectory-v1` teacher/student、Core ML package 与 Watch 有界融合；
- [x] Preview→Final iPhone 状态与 64 点轨迹展示；
- [x] 原始文件 ACK 前持久化保留；
- [ ] macOS + Xcode 真机编译（Linux Cloud 无 Apple SDK）；
- [ ] Series 8+ 真机 10 杆采集：丢样率、批延迟、温升、功耗；
- [ ] Series 5 真机兼容路径冒烟：可采集、可传输、可分析；
- [ ] 端模型推理 P95 <20 ms、触觉 enqueue P95 <50 ms、停杆预览 P95 <1 s；
- [ ] Series 8+ live + batched 并行资源竞争、掉样、温升与功耗门；
- [ ] 将真机 JSON 纳入 optical-aligned 回归。

## 非目标

- Watch 屏幕内实时显示未经完整分析的“杆面角/腕角”；
- 为了离线端上运行而用简化滤波器替换 Python 算法；
- 用 1 秒 batch rail 承担实时触觉（实时闭环只消费 100 Hz live rail）；
- 宣称兼容模式与 800 Hz 模式同等 Impact 时间精度。
