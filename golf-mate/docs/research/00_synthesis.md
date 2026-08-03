# 综合结论：Golf Mate 算法选型与能力分层

> 本文件是 `01_academia` / `02_industry` / `03_opensource` 的决策收敛。实现以本文为准。

---

## 1. 市场与技术空白

| 层 | 谁强 | 空白 |
|----|------|------|
| 下场击球追踪 / 策略 | Arccos、Garmin、Shot Scope | 非我们主战场 |
| 球 / 杆交付真相 | TrackMan 等 LM | 贵、不测身体手腕 |
| 身体 3D（练习场） | Sportsbox | 下场不便 |
| 腕角深度训练 | HackMotion | 偏训练向、贵 |
| 手套卡形态 | 历史 Zepp（已死） | **下场轻便腕部教练空位** |

**定位一句话：** 下场可用的腕部（Watch / 自研磁吸手套卡）生物力学教练层 —— 连接「感觉」与「可解释改进」，并预留与 LM 对齐。

---

## 2. 技术选型决策（已定）

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 主传感器几何 | 单节点腕部 6 轴 | 对齐 2025 单腕研究 + 手套卡产品形态 |
| 磁强计 | 默认关闭 | 近钢杆软铁；VQF 6D |
| AHRS | VQF 6D + 高尔夫加速度门控 | 高动态下经典 AHRS 失效（SciRep） |
| 初值 | Address 准静态定姿 | 免 T-pose 可落地 |
| 轨迹 | 去重力积分 + 事件 ZUPT + swing-plane | SciRep ~17 cm 级可复现 |
| 相位 | Address / Top / Impact / Finish | P0 最小充分集；语义对齐 GolfDB |
| 全身网络 | P1 预留 | 需合成大数据 + 真实微调 |
| 签名 / 前向力矩 | P2 预留 | 差异化，非本轮验收 |
| 开源依赖 | VQF + numpy/scipy；禁 GPL/NC 入核心 | 许可与可控性 |
| 验证 | 解析真值 + 合成挥杆 UT | 无硬件可证伪/证真 |

---

## 3. 能力分层规格

### P0（本轮必交付，可严格 UT）

- 硬件无关 `ImuPacket` / `SensorFrame`
- **`devices.normalize_packet`**：安装外参 + 左右手/腕侧 → canonical lead-right 解剖系
- Watch / 手套卡 **规格契约**（无 Swift；假数据工厂供 UT）
- GolfGatedAHRS（门控 + 姿态序列）
- 相位事件检测
- 腕轨迹重建（hybrid / ZUPT + plane）
- 特征：tempo、rhythm、peak ω、平面角、closure 代理、手速代理
- 可解释诊断规则 + **理想运动学参考带**（分位数代理，非唯一正确姿势）
- **`export.SwingFeatureVector`**（Core ML 可导出契约，本轮无 `.mlmodel`）
- `SwingReport` 稳定 schema
- pytest 全绿

### P1（接口预留）

- 单腕 → 全身运动学映射（WIT-KinNet / Lauer 路线）
- MultiSenseGolf 回归闸门（含 **elite 高水平子集** 评测轨）
- imucal Ferraris 离线标定流水线
- Watch / 手套卡 **真机 adapter 实现**（Swift / BLE）
- Core ML 模型训练与转换（消费同一 feature contract）

### Canonical Frame（多设备解耦）

客户端只填设备安装系 IMU，并如实设置 `handedness` / `wrist` / `mount_extrinsic`。`normalize_packet` 负责外参、左右镜像与幂等 `is_canonical` 标记；其后算法一律在右打领先腕解剖系下运行。

### P2（接口预留）

- 离散运动 token 签名 + 可解释反馈
- 前向动力学「物理老师」信号
- 与 LM Face/Path 联合校准

---

## 4. 诚实边界（写进产品与报告）

**可以声称：**

- 腕姿态、节奏、冲击时刻、平面与路径代理、相对 Address 的闭合趋势
- 基于规则的改进提示，并标注为代理/不确定度

**不可声称（单腕 P0）：**

- 绝对杆面角 / 真实 Club Path（无杆头观测）
- 厘米级全身关节角
- 「唯一正确挥杆」模板

---

## 5. 不可仅靠仿真关闭的风险

- 软组织伪影与表带/手套松动
- 真实磁畸变与温度偏置
- 击球冲击饱和与非线性
- 个性化解剖与左右手
- 合成 → 真实域差（全身网络）

这些必须在后续用小规模真实校准集做闸门；P0 用解析/合成证明 **算法正确性**，不假装 **测量完备性**。

---

## 6. 本轮工程验收命令

```bash
cd golf-mate/algo
pip install -e ".[dev]"
pytest -q
```

通过即完成本轮算法核心验证闭环。
