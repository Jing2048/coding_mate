# Apple Watch E2E 验证版 PRD

> 状态：`in_progress` · 目标：真实 Watch 全速采集 → iPhone 原始文件 → Python 全算法回放

## 核心承诺

1. **采集不打折**：Series 8 / Ultra 或更新机型使用 `CMBatchedSensorManager`：
   - 原生 800 Hz accelerometer 完整保留；
   - 原生 200 Hz Device Motion 完整保留；
   - 不在 Watch 上提前裁切、压缩或只上传摘要。
2. **算法不打折**：不移植一套缩水 Swift 算法。iPhone 收到原始双流后，POST 到 Mac
   上的 `watch_lab_server.py`，跑现有 Python `analyze_swing` 全链路；800 Hz 碰撞时间
   作为高精度 hint，AHRS/轨迹仍跑 200 Hz。iPhone 直接展示完整分析结果。
3. **表达不越界**：Watch 动态轨迹是采集状态的 motion field，不冒充已测三维轨迹；
   clubface / X-factor 等继续标为 `INFERRED`。

## 用户故事

用户打开 Watch 的 Swing 页面，看到硬件能力（800 ACC / 200 MOTION），点击「开始挥杆」：

1. App 请求 HealthKit 与 Motion 权限；
2. 启动 Golf workout，解锁高频批量传感器；
3. Watch 内存环形缓存保留原始双流；
4. 用户完成后点击「完成」，Watch 原子写入 `golfmate-watch-capture-v1` JSON；
5. 使用 `WCSession.transferFile` 可靠发送到 iPhone；
6. iPhone 自动把原始 JSON POST 到 Mac lab server（完整 Python 管道）；
7. iPhone 展示 tempo / rhythm / phases / findings 等完整算法结果。

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
- [x] Python loader 保留 800 Hz sidecar，200 Hz 对齐满足 `ImuPacket`；
- [x] 800 Hz impact hint 驱动完整 pipeline；
- [x] 合成 E2E 测试覆盖采样率、单位、impact 精度、坏输入；
- [ ] macOS + Xcode 真机编译（Linux Cloud 无 Apple SDK）；
- [ ] Series 8+ 真机 10 杆采集：丢样率、批延迟、温升、功耗；
- [ ] 将真机 JSON 纳入 optical-aligned 回归。

## 非目标

- Watch 屏幕内实时显示未经完整分析的“杆面角/腕角”；
- 为了离线端上运行而用简化滤波器替换 Python 算法；
- 在 1 秒 batch 延迟下宣称亚秒级实时撞击触觉反馈。
