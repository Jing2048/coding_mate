# 真机验证协议与声明矩阵 / 发布清单 / Domain gap

配套实现：

- 数据合同：`golf-mate/algo/data/watch_gold/`
- 校验：`golfmate_algo.bench.datasets.watch_gold`
- 闸门：`golfmate_algo.bench.commercial_release_gate`（`commercial-release-gate-v2`）
- CLI：`golf-mate/algo/scripts/commercial_release_gate.py`

## 1. Device validation protocol（摘要）

完整步骤见 `algo/data/watch_gold/PROTOCOL.md`。

最小商用证据集（fail-closed）：

| 条件 | 阈值 |
|------|------|
| 有效挥杆 | ≥ 30 |
| 受试者（伪名） | ≥ 2 |
| Series 8+ `high_rate` | ≥ 1 |
| Series 5 `compat` | ≥ 1 |
| 左右手 | 都有，**或** `documented_limitations` 明示单侧缺失 |
| 表带松紧 | ≥ 2 种 `strap_fit` |
| 杆类 | iron 族 + wood |
| 每杆 | `impact_timestamp_s` + `impact_timestamp_source` |
| **独立 Impact 对齐** | `slow_mo`\|`optical`\|`launch_monitor` ≥ max(3, 10%) |
| **光学腕路径** | optical + path labels/`artifact_id` ≥ 3 |
| **Tempo 参考** | `metronome`\|`slow_mo` ≥ 3 |
| 证据类 | 仅 `real_device`；合成 fixture **不能**解锁 `commercial_ready` |
| 采样率 | 清单声明 vs 解码实测：10% 或 floor（motion 5 Hz / accel 20 Hz） |

**诚实说明：** 上述 claim 参考闸是**最小结构证据**（独立 provenance + labels），**不是** Impact / 路径 / tempo 的精度验收。`collision_accel` / `kinematic` 仅是设备派生 provenance，**不算**独立金标准。仅有 metronome **不能**解锁 Impact/路径商用证据。

隐私：伪名、无姓名/人脸/精确 GPS；`consent.obtained` + `license` 必填；参考 `artifact_id` 为不透明 id（仓库不强制放外部文件）。

## 2. Claims matrix

| 主张 / 指标 | 类别 | 何时可对外 |
|-------------|------|------------|
| Tempo / backswing / downswing / rhythm | **measured/derived** | 真值层质量门 ok **且** tempo 参考闸结构通过 |
| Peak ω、冲击时序（collision） | **measured/derived** | high-rate collision 或已标注 kinematic；**对外冲击精度**还需独立 Impact 对齐闸 |
| 腕路径长度 / 平面角稳定性 | **derived** | 轨迹未 `abstain` **且** optical path 参考闸结构通过 |
| Casting / closure 代理 | **proxy** | 可观测条件满足，否则弃权 |
| 腕 FE/RU、杆面、X-factor、sequence | **inferred** | 校准带内且 confidence≥τ，否则弃权 |
| 「替代 TrackMan / HackMotion」 | **non-claim** | 永不作为卖点 |
| 「商用生物力学就绪」 | **non-claim until gate** | 仅当 device-gold `commercial_ready`（含三项 claim 参考闸） |
| 合成 cross_multibody 精度数字 | **算法 CI 证据** | 可写进研究/工程报告，**不可**冒充真机 |
| 仅 metronome 的「已验证冲击/路径」 | **non-claim** | metronome 不构成 Impact/path 独立金标准 |

类别定义与 `CommercialSwingReport v2` / `quality.uncertainty` 一致：`measured` · `derived` · `proxy` · `inferred`；另加产品层 **non-claim**。

## 3. Commercial release checklist

- [ ] `CommercialSwingReport v2` 契约测试绿；无高阶 `is_proxy=False` 误标
- [ ] 算法合成闸（zero-trust / beyond-consumer）按工程标准通过
- [ ] `data/watch_gold/manifest.json` 非空且每条 `evidence_class=real_device`
- [ ] 每条含 `impact_timestamp_s`；独立 Impact / optical path / tempo 三闸均过
- [ ] 声明采样率与解码实测一致（tolerance）
- [ ] `python scripts/commercial_release_gate.py --require-ready` → exit 0
- [ ] Domain gap 已覆盖或写入 `documented_limitations`
- [ ] 对外文案过 claims matrix（无 non-claim 泄漏；不把结构闸说成精度过门）
- [ ] 无 Swift/产品壳冒充已完成真机商业化（本轮明确非目标）

## 4. Domain gap register

| Gap | 风险 | 门禁 / 文档 |
|-----|------|-------------|
| Strap fit（松 / 紧） | 软组织抖动、姿态漂移、伪 casting | 要求 ≥2 种 `strap_fit` |
| Left-handed | 镜像与外参错误被当动作问题 | 左右都有或 `left_hand_not_represented` |
| Clubs（iron vs wood） | 冲击频谱 / 平面 / tempo 分布偏移 | iron 族 + wood |
| Terrain / lie | 地址倾斜与平面角偏差 | 采集协议要求记录；仅 flat 时限制「地形泛化」声明 |
| Saturation / clip | 硬铁冲击削波 → 冲击时序与手速失真 | 协议要求硬击样本；质量门应 `degraded`/`abstain` |
| Metronome-only refs | 误把 tempo 参考当成 Impact/path 金标准 | claim 闸显式拆分；metronome-only → 结构失败 |

## 5. JSON 机器可读入口

```bash
cd golf-mate/algo
python scripts/commercial_release_gate.py --json
# 仓库空目录预期: commercial_ready=false
```
