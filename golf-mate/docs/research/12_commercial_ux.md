# 商用交互与视觉系统：Quiet Instrument

> 目标：把实验室验证壳升级为可长期使用的高尔夫训练产品。设计不依赖“AI 感”、
> 霓虹渐变或指标墙，而依赖明确任务、可信数据层级和下一杆可执行反馈。

## 1. 研究基线

### Apple 官方

- [HIG Workouts](https://developer.apple.com/design/human-interface-guidelines/workouts)
- [watchOS 10 intuitive UI](https://developer.apple.com/documentation/watchos-apps/creating-an-intuitive-and-effective-ui-in-watchos-10)
- [Always On](https://developer.apple.com/documentation/watchos-apps/designing-your-app-for-the-always-on-state)
- [HIG Accessibility](https://developer.apple.com/design/human-interface-guidelines/accessibility)
- [HIG Typography](https://developer.apple.com/design/human-interface-guidelines/typography)
- [HIG Color](https://developer.apple.com/design/human-interface-guidelines/color)
- [Swift Charts](https://developer.apple.com/documentation/charts)

关键约束：

1. Watch 运动中只承担一个任务；信息必须一眼读完。
2. Always On 降至 1 Hz，隐藏小数秒，停止装饰动画。
3. 状态不能只靠颜色；所有图形有文本与 VoiceOver 等价表达。
4. iPhone 顶层导航用 tab，临时配置才用 sheet / settings。

### 高尔夫产品

| 产品 | 借鉴 | 不复制 |
|------|------|--------|
| HackMotion | baseline → drill → retest；每杆一个反馈 | 双传感腕角能力不能伪装成 Watch 实测 |
| Golfshot Swing ID | Watch 原生、个人目标、High-rate 分层 | KPI 堆叠与 GPS 球场能力不是本轮主线 |
| Garmin Tempo Training | 练习 / 下场信息预算分离 | 3:1 不是所有人的唯一标准 |
| TrackMan TPS | 参数定义、教练工作流、少而完整 | Face/Path/AoA 不能由单腕替代 |
| Sportsbox 3D | 玩家层 / 教练层分离、目标卡 | 不做假 3D 人体 |
| Arccos | 数据纠错与情境化决策 | 不进入 Strokes Gained 主战场 |

参考：

- https://golfshot.com/swing-id-swing-analysis-app
- https://www8.garmin.com/manuals/webhelp/GUID-0F89E6A5-EC1C-4382-964E-27DC4B5FC932/EN-US/GUID-8A23CE99-3C6C-4E7C-8FFE-A9C472436549.html
- https://www.trackman.com/blog/golf/club-data-definitions
- https://www.sportsbox.ai/
- https://www.arccosgolf.com/blogs/community/new-in-play-experience-is-here

## 2. 产品原则

### 2.1 结论优先，证据随后

iPhone 阅读顺序固定：

1. 质量与可信度；
2. 个人练习结论（存在个人先验时）；
3. 三个关注指标；
4. 最终手腕轨迹；
5. 阶段时间轴；
6. 其余可引用指标；
7. 折叠的代理 / 推断；
8. 最多三条行动要点。

### 2.2 数据类型是界面语法

| 类型 | UI |
|------|----|
| measured | 实测 badge，主文字 |
| derived | 计算 badge，主文字 |
| proxy | 代理 badge，橙色语义 |
| inferred | 推断 badge，独立折叠区 |
| degraded | 保留数值 + “质量受限” |
| abstain | 不绘图、不显示假数字；给出原因 |
| provisional | Watch 预览，分析完成后被 final 替换 |

`kind` 与 `validity` 必须分别显示：推断指标即使质量正常，仍然是推断。

### 2.3 视觉：Quiet Instrument

- 使用系统背景、系统字体、SF Symbols 与单一语义强调色；
- 无渐变、无 glow、无玻璃 KPI 墙、无 all-caps 工程标签；
- tabular number 只用于数值；
- 红色只表示错误 / 停止；绿色表示已验证；橙色表示代理或质量受限；
- 腕部路径使用单色线与击球标记，不模拟球飞或杆头 3D ribbon。

## 3. 信息架构

```text
iPhone
├── 挥杆
│   ├── 等待 Watch
│   ├── 预览到达
│   ├── 采集到达 / 分析中
│   ├── 错误（保留上一杆有效结果）
│   └── 挥杆分析详情
└── 设置
    ├── 分析连接
    ├── 原始采集导出
    └── 开发命令（DEBUG only）

Watch
└── 就位 → 准备采集 → 采集中 → 正在保存 → 已保存 / 出错
```

本轮没有账号、云历史、社交、排行榜或 AI chat；不造尚未存在的产品能力。

## 4. 核心交互

### Watch

- 顶部固定显示真实采样模式：高速 800/200 或兼容 100 Hz；
- 中部只显示状态、时间与低墨水腕部轨迹；
- 底部一个主操作；
- Ready 明确写“腕部轨迹预览；完整分析将在 iPhone 更新”；
- 预览质量用文字（清晰 / 一般 / 偏弱），不显示无法解释的 PATH 百分比。

### iPhone

- 预览在采集和分析阶段持续可见；
- 分析失败不清空上一杆有效结果；
- 主界面不出现 Python、`analyze_swing` 或 CLI；
- 服务与原始文件放入设置；
- 轨迹质量弃权时完全不绘制；
- 阶段显示秒，不显示样本 index；
- 推断区默认折叠，并写明“非实测层”。

## 5. 可访问性与本地化

- iPhone 使用 Dynamic Type text styles 和 `ViewThatFits`；
- Watch 使用系统 text styles，Always On 为整数秒；
- Canvas 提供完整 VoiceOver summary；
- Reduce Motion 停止循环轨迹动画；
- 图标 + 文案表达状态，颜色仅作辅助；
- `Localizable.xcstrings` 以简体中文为 source language，核心交互提供英文翻译骨架。

## 6. 验收

- 用户不需要理解实现即可完成 Watch 采集 → iPhone 分析；
- 首页无开发控件或工程术语；
- inferred / proxy 不与 measured 同权展示；
- abstain 不展示数字或漂亮错误轨迹；
- AX Dynamic Type 下指标行可纵向重排；
- VoiceOver 能读出轨迹类型、点数、置信度与边界说明；
- Watch Reduce Motion / Always On 无装饰动画与小数秒。
