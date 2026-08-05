# 商用算法 / 产品痛点综合（生物力学主轴）

> 状态：研究结论 · 对应 plan `commercial-biomech-core` · 本轮**无 UI 产品壳**

## 1. 一句话

用户买的是「下场可解释、可重复、敢定价的腕部生物力学」，不是「又能跑一轮合成 demo」。

## 2. 算法痛点（当前）

| 痛点 | 表现 | 商用后果 |
|------|------|----------|
| 可引用层与广告层混淆 | 合成 `cross_multibody` 过门 ≠ Watch MEMS 真值 | 一旦用 cm / Face 角对外承诺即翻车 |
| 高阶推断欠校准 | 腕屈伸 / 杆面 / X-factor 易被 UI 当实测 | 教练与严肃业余者立刻不信任 |
| 无个人基线 | 相对 Tour 平均而非相对本人 | 练习闭环「下一杆纠偏」站不住 |
| 无弃权 | 质量差仍吐数字 | 坏杆被当成「算法说你 casting」 |
| 无真机金标准 | 仓库仅有合成 / mocap 衍生 IMU | **不得宣称商用生物力学就绪** |
| 参考证据混用 | 仅 metronome 或设备 `collision_accel` 冒充独立 Impact/path 金标 | claim 闸拆分；结构证据 ≠ 精度过门 |

已落地的缓解（算法侧，非产品壳）：

- `CommercialSwingReport v2`：`measured|derived|proxy|inferred` + `validity` + 弃权
- 个人先验 / practice-loop / strategy **特征契约**（无 Watch 触觉 UI）
- 本目录配套的 **device-gold 合同 + 商用发布闸**（空目录 = 未就绪）

## 3. 产品痛点（边界诚实）

| 用户期待 | 诚实边界 |
|----------|----------|
| 替代 TrackMan Face/Path | **非目标**；LM 仅作可选对照参考 |
| 替代 HackMotion 腕角金标 | 腕 FE/RU 为 `INFERRED`，需校准/弃权 |
| Series 5 与 Series 8 同精度 | 双轨：compat vs high_rate；门禁要求两层都有证据 |
| 「装上就能卖」 | 无 ≥30 杆跨 ≥2 人真机集 + 分层覆盖 → **commercial_ready=false** |

## 4. 与算法合成闸的关系

```
algorithm synthetic gates  ≠  device evidence gate
(cross_multibody / optical twin)   (watch_gold real_device)
```

合成闸证明 CI 可回归；真机闸证明 Watch MEMS 证据充分。**禁止**把合成通过写成商用就绪。

## 5. 下一步（非本轮 UI）

1. 按 `algo/data/watch_gold/PROTOCOL.md` 采集真机最小集
2. 填 `manifest.json`（伪名、哈希、参考标签、同意书）
3. `python scripts/commercial_release_gate.py --require-ready`
4. 仅在 `commercial_ready=true` 后对外使用「商用生物力学」表述
