# 行业实践简报：挥杆教练 / 可穿戴 / Launch Monitor

> 范围：挥杆力学与教练反馈（非纯击球追踪）。采样率等以公开资料为准。

---

## 1. 竞争格局

| 象限 | 代表 | 核心价值 |
|------|------|----------|
| 手腕 / 手套 IMU 教练 | HackMotion；历史 Zepp；Golfshot Watch | 腕角 / 节奏 / 闭合率，实时反馈 |
| 握把端 IMU | Blast Golf、Garmin TruSwing（已停产） | 杆速 / 节奏 / 路径估计 |
| 手机单目 3D 身体 | Sportsbox 3D Golf | 躯干 / 骨盆运动学 |
| 击球 + 策略 AI | Arccos | Strokes Gained，非力学教练 |
| 雷达 / 光电 LM | TrackMan、FlightScope、Rapsodo | 球 / 杆交付（AoA、Path、Face） |
| 实验室多节点 IMU | Noraxon、Xsens、诺亦腾 mySwing | 全身 kinematic sequence |
| 中国市场 | 诺亦腾 mySwing；GOLFJOY 等模拟器 | B2B 教学馆为主 |

**价值链：** 身体运动学 → 手腕/手部 → 杆身/杆头交付 → 球飞结果 → 下场策略。多数消费级只占一层。

---

## 2. 产品技术拆解

### 2.1 Golfshot Swing ID（Apple Watch）

- **传感器：** Watch accel + gyro；Series 8+ / Ultra
- **采样：** `CMBatchedSensorManager`：accel **800 Hz**，device motion **200 Hz**（需 HealthKit Workout）
- **指标：** Tempo、Rhythm（≈3:1）、Hand Speed、Transition、Wrist Path、Backswing Arc、Wrist Rotation、Closure Rate、Impact Plane
- **算法：** Apple AHRS/DeviceMotion + 冲击事件检测 + 几何/时序特征
- **强 / 弱：** 下场零额外硬件；表带参考系 ≠ 握把；Closure/杆面为间接估计；批延迟约 1s，难做挥杆中触觉

### 2.2 HackMotion

- **传感器：** 双 6 轴；lead/trail 腕；宣称 **800 FPS**
- **指标：** Flexion/Extension（bow/cup）、Radial/Ulnar（hinge）、Rotation；Address/Top/Impact 关键帧；Tour 对照；触觉 biofeedback
- **算法：** 双 IMU 相对姿态 / AHRS；事件分割；模式库
- **强 / 弱：** 教练真正使用的腕角语言；不测躯干/球飞；贴合漂移毁标定

### 2.3 Blast Motion / Blast Golf

- 握把 butt 端 6 轴 BLE
- Tempo、Hand/Clubhead Speed、Attack Angle、Swing Plane；推杆面角敏感
- 杆头速为估计；需换杆安装

### 2.4 Sportsbox 3D Golf

- 手机单相机 → 2D 关键点 → 专有 2D→3D lift
- Chest/Pelvis turn/bend/side bend、sway/lift、kinematic sequence
- 身体力学主战场；依赖机位/光照；手腕精细自由度不足

### 2.5 Arccos

- 击球检测 + GPS + Strokes Gained + AI Strategy
- **非** Tempo/腕角/AoA 教练产品
- Air：口袋 IMU 无杆传感器

### 2.6 Launch Monitors（TrackMan / FlightScope / Rapsodo）

- Club Speed、AoA、Path、Face、Face-to-Path、Dynamic Loft、Smash
- Ball Speed、Launch、Spin、Carry
- **教练用法：** 把 IMU/视频的「感觉」校准到 Face/Path/AoA
- **不测** 身体 / 手腕

### 2.7 实验室：Noraxon / Xsens / 诺亦腾

- Noraxon：内部 1600 Hz，输出姿态最高 400 Hz；典型 4 点骨盆/脊柱/上臂/手
- Xsens Link 240 Hz；Awinda 全身常 60–120 Hz
- 诺亦腾 mySwing：17 节点 + 杆上传感器；B2B

### 2.8 历史 Zepp

- **手套卡扣** IMU；Club/Hand speed、Plane、Tempo
- 被 Garmin 收购后停服
- 形态上最接近「手套磁吸卡」消费品空白

### 2.9 Motus（棒球）可迁移点

- 前臂袖套 1000 Hz；±24 g / ±4000 °/s
- 教训：高 ODR + 高量程；力矩为模型估计；贴合漂移致命
- 高尔夫应对标：事件检测、角速度峰值、负荷管理

---

## 3. Apple `CMBatchedSensorManager`

| 项 | 说明 |
|----|------|
| 平台 | watchOS 10+；Series 8 / Ultra+ |
| 速率 | Accel 800 Hz；Device Motion 200 Hz；约 1 批/秒 |
| 约束 | HealthKit 活跃 Workout；Motion 隐私说明 |
| 高尔夫用法 | 800 Hz 找冲击；200 Hz 找起点/平面/旋转 |
| 局限 | 批延迟 → 触觉宜端侧；表带框 ≠ 手套框 |

WWDC23 Session 10179：https://developer.apple.com/videos/play/wwdc2023/10179/

---

## 4. 自研手套卡 / 磁吸传感器：硬件 → 算法约束

### 常用芯片

| 芯片 | 类型 | 高尔夫取向 |
|------|------|-----------|
| BMI270 | 6 轴 | 续航友好；主机做 AHRS |
| ICM-42688-P | 6 轴高性能 | 冲击 / 闭合率首选 |
| BNO085 | 9 轴 + 片上融合 | 需验证高动态 fusion 是否拖尾 |

**采样建议：** 腕部 **400–1000 Hz**；全身时序 100–240 Hz 即可。

### 产品形态约束 → 算法

| 约束 | 算法含义 |
|------|----------|
| 安装框不固定 | Address 零位标定；报「相对 Address」角 |
| 手套滑动 / 软组织 | 冲击后短窗不可信；gyro 主导短时 |
| 近钢杆软铁 | 默认 6 轴；mag 仅慢校正或不启用 |
| BLE 延迟 | 实时 haptic 宜 on-device；手机做复盘 |
| 电池 | FIFO 批传、运动唤醒、非挥杆降 ODR |
| 单节点可观测量 | 腕 3DOF、角速度、手速代理、tempo、closure 代理；**不能**直接出 X-factor / 真实 Face |

**无线充电 / 磁吸卡：** 不影响算法核心，但需会话级 `mount_extrinsic` 与温度偏置跟踪接口。

---

## 5. White-space（产品空白）

1. Zepp 留下的手套安装形态空位
2. Watch 便捷 vs HackMotion 深度之间的中档下场可用方案
3. 与 LM 的「腕角/闭合 ↔ Face/Path」桥接校准流程
4. 中文教练工作流 + 本地化 drill + 触觉
5. **勿碰红海：** 纯 GPS 击球追踪、纯球飞、纯手机身体 3D

---

## 6. 教练真实使用的指标词汇

### 身体 / 序列
- Kinematic sequence（盆→胸→臂→杆峰值角速度次序）
- X-factor / X-factor stretch
- Chest/Pelvis turn, bend, side bend；sway, lift, thrust
- P-system：P1 Address … P4 Top … P6/P7 Impact … Finish

### 手腕（HackMotion 口语）
- Cup / Bow = extension / flexion
- Hinge = radial–ulnar；casting = 过早 ulnar
- Release / flip；shaft lean
- Rotation / 前臂滚动

### 手表 / 手套路径
- Tempo / Rhythm（常 3:1）
- Hand speed、Transition、Wrist path（In-Out / Out-In）
- Closure rate、Impact plane

### 杆交付（LM）
- Club path、AoA、Face、Face-to-path、Dynamic loft、Smash

**教练工作流一句：** 身体用序列与 X-factor → 手腕用 cup/bow/hinge → LM 验证 face/path/AoA → 下场看是否转化为分数。

---

## 7. 对 Golf Mate 的含义

- 产品定位：下场可用的 **腕部生物力学教练层**（非 Arccos，非 TrackMan）。
- 算法诚实：单节点输出代理指标 + 不确定度；与 LM 对齐是后续产品故事。
- 硬件路线：Watch 与自研手套卡共享同一 `SensorFrame` / `ImuPacket` 契约。
