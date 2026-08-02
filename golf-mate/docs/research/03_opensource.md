# 开源与工程栈简报：IMU 挥杆算法可复用地基

> 原则：许可安全（优先 MIT/Apache/BSD/CC0）；高尔夫专用库几乎不存在，需自研核心。

---

## 1. AHRS / 传感器融合

| 项目 | URL | 许可 | 复用点 | 成熟度 |
|------|-----|------|--------|--------|
| **VQF** | https://github.com/dlaidig/vqf | MIT | 6D/9D；gyro bias；磁干扰抑制；高尔夫优先 6D | 高 |
| **imufusion (Fusion)** | https://github.com/xioTechnologies/Fusion | MIT | 修订版 Madgwick；嵌入式友好 | 很高 |
| **ahrs** | https://github.com/Mayitzin/ahrs | MIT | Madgwick/Mahony/EKF 等基线对照 | 高 |
| **qmt** | https://github.com/dlaidig/qmt | MIT | VQF 生态配套工具 | 中高 |

**选型：** 生产默认 **VQF 6D**；保留 Madgwick 作 A/B。

文档：https://vqf.readthedocs.io/

---

## 2. IMU 预处理

| 项目 | URL | 许可 | 用途 |
|------|-----|------|------|
| **imucal** | https://github.com/mad-lab-fau/imucal | MIT | Ferraris 六面标定 |
| **allan-variance** | https://github.com/varunagrawal/allan_variance | BSD-3 | ARW/VRW/bias 噪声模型 |
| **scipy.signal** | — | BSD | 滤波；去重力自研 |

**选型：** 离线标定用 imucal（P1）；在线 bias 交给 VQF / 静止段估计；线性加速度自写。

---

## 3. 人体运动 / 可迁移库

| 项目 | URL | 许可 | 说明 |
|------|-----|------|------|
| OpenSense / opensim-core | https://github.com/opensim-org/opensim-core | Apache-2.0 | IMU→IK；P0 过重，P1+ |
| gaitmap | https://github.com/mad-lab-fau/gaitmap | MIT（核心） | 事件检测模式可借鉴 |
| tpcp | https://github.com/mad-lab-fau/tpcp | MIT | 可复现流水线 |

---

## 4. 高尔夫专用开源

| 项目 | URL | 许可 | 用法 |
|------|-----|------|------|
| GolfDB / SwingNet | https://github.com/wmcnally/golfdb | **CC BY-NC 4.0** | **仅借 8 事件语义**；权重勿进商用核心 |
| CaddieSet | https://github.com/damilab/CaddieSet | MIT | 关节特征 + 球飞，无 IMU |
| GolfPose | https://github.com/MingHanLee/GolfPose | 研究授权 | 视频姿态 |
| PinPointStudio | https://github.com/PinPoint-Golf/PinPointStudio | **GPL-2.0** | UX 参考，勿链核心 |
| SwingScan | https://github.com/ckirby04/SwingScan | MIT（权重 NC） | 视频相位参考 |
| SKS-Transformer | https://github.com/cw-feng/SKS-Transformer | 见仓库 | 腰 IMU 错误分类小样本 |

**结论：** 算法包 **自研 IMU 核心**；GolfDB 只复用事件 taxonomy。

---

## 5. Pose / Mesh → 合成 IMU

| 项目 | URL | 许可 | 注意 |
|------|-----|------|------|
| TransPose | https://github.com/Xinyu-Yi/TransPose | **GPL-3.0** | 公式可对照；勿链代码 |
| PIP | https://github.com/Xinyu-Yi/PIP | GPL-3.0 | 同上 |
| DIP | https://dip.is.tuebingen.mpg.de/ | 研究用途 | 范式源头 |
| WHAM | https://github.com/yohanshin/WHAM | MIT | 视频→世界系运动 |
| SMPL-X | https://github.com/vchoutas/smplx | Max Planck 协议 | mesh |
| AMASS | https://amass.is.tue.mpg.de/ | 各子集不同 | 大规模预训练 |
| Pose2Sim | https://github.com/perfanalytics/pose2sim | BSD-3 | 多机位→OpenSim |

**选型：** 自写 MIT 许可合成模块（解析刚体 + 有限差分）；对照 TransPose 公式。

---

## 6. 时序 ML

| 项目 | 许可 | 用途 |
|------|------|------|
| tsai | Apache-2.0 | InceptionTime 等相位分割（有标注后） |
| sktime | BSD-3 | 经典时序 ML、易 mock |

**P0：** 规则事件引擎；有金标准后再上 tsai。

---

## 7. 生物力学 / 多刚体

| 项目 | 许可 | 用途 |
|------|------|------|
| MuJoCo | Apache-2.0 | 可选多连杆仿真 |
| PyBullet | Zlib 系 | 备选 |
| OpenSim | Apache-2.0 | 后期全身 |

**P0：** 自研解析旋转 + 平面圆周合成挥杆即可。

---

## 8. 数据集许可速查

| 数据集 | 许可 | 价值 |
|--------|------|------|
| **MultiSenseGolf** | **CC0-1.0** | 首选金标准（后续回归） |
| GolfDB | CC BY-NC | 事件定义 / 非商用研究 |
| CaddieSet | MIT | 结果关联 |
| AMASS / DIP | 申请 / 子集许可 | 合成预训练 |

doi MultiSenseGolf: https://doi.org/10.7910/DVN/LCCLLW

---

## 9. Golf Mate 推荐依赖栈（P0）

```text
必选
  numpy, scipy
  vqf                 # 主 AHRS（6D）；缺失时走互补滤波回退
  pytest, hypothesis

可选对照
  ahrs 或 imufusion   # Madgwick 基线

明确后置 / 禁入核心
  opensim-core（重）
  TransPose / PIP（GPL-3）
  GolfDB 权重（NC）
  PinPointStudio（GPL-2）
```

### 建议包结构（与实现一致）

```text
golf-mate/algo/
  golfmate_algo/
    types.py
    math/so3.py
    calib/static.py
    ahrs/gated_vqf.py
    signal/resample.py
    events/phase.py
    traj/dead_reckon.py
    traj/swing_plane.py
    features/wrist.py
    biomechanics/sequence.py
    coach/diagnostics.py
    synth/analytic.py
  tests/
```

### 单测策略

- 解析真值：常值角速度 → 姿态误差 < 阈值
- 静止段：线性加速度 ≈ 0
- 合成挥杆：事件顺序与 tempo 比值
- Hypothesis：四元数归一化、旋转复合
- MultiSenseGolf：后续可选 CI，不阻塞 P0

---

## 10. 一句话选型

以 **VQF + 自研门控/相位/轨迹/诊断 + 解析合成 UT** 为地基；开源只借方法与标签协议，不把许可风险依赖链进核心。
