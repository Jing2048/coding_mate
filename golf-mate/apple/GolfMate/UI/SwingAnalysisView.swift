import SwiftUI

struct SwingAnalysisView: View {
    let result: SwingAnalysisResult

    @State private var showInferred = false

    private var report: SwingAnalysisResult.CommercialReport? {
        result.commercialReport
    }

    private var focusMetrics: [SwingAnalysisResult.CommercialMetric] {
        let truth = report?.truth ?? []
        let available = truth.filter(\.isAvailable)
        let preferred = ["tempo_s", "rhythm", "hand_speed_peak_m_s", "downswing_s"]
        let selected = preferred.compactMap { name in
            available.first { $0.name == name }
        }
        if !selected.isEmpty { return Array(selected.prefix(3)) }
        return Array(available.prefix(3))
    }

    private var remainingTruth: [SwingAnalysisResult.CommercialMetric] {
        let focusIDs = Set(focusMetrics.map(\.id))
        return (report?.truth ?? []).filter { !focusIDs.contains($0.id) }
    }

    private var inferredMetrics: [SwingAnalysisResult.CommercialMetric] {
        (report?.inference ?? []).filter(\.isAvailable)
    }

    private var abstainedInferenceCount: Int {
        (report?.inference ?? []).filter { !$0.isAvailable }.count
    }

    private var findings: [SwingAnalysisResult.Finding] {
        result.displayFindings
    }

    private var finalTrajectoryValidity: String? {
        report?.truth.first(where: { $0.name == "trajectory_radius_m" })?.validity
            ?? result.meta?.feature_quality?["path"]?.validity
            ?? result.trajectoryQuality?.validity
    }

    private var canShowFinalTrajectory: Bool {
        !result.finalTrajectoryPoints.isEmpty && finalTrajectoryValidity != "abstain"
    }

    private var impactIndex: Int? {
        // Final trajectory is typically resampled; mark midpoint-ish using phase ratio if possible.
        guard
            let phases = result.phases,
            let points = result.finalTrajectory,
            !points.isEmpty,
            phases.finish > phases.address
        else { return nil }
        let ratio = Double(phases.impact - phases.address)
            / Double(phases.finish - phases.address)
        let index = Int((ratio * Double(points.count - 1)).rounded())
        return min(max(index, 0), points.count - 1)
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: GolfTheme.sectionSpacing) {
                AnalysisQualityCard(result: result)

                if report?.practice_loop?.implemented == true {
                    practiceVerdict
                }

                if !focusMetrics.isEmpty {
                    focusSection
                } else if let features = result.features {
                    legacyFocusSection(features)
                }

                if canShowFinalTrajectory {
                    TrajectoryPathView(
                        points: result.finalTrajectoryPoints,
                        title: "最终手腕轨迹",
                        confidence: Float(
                            result.trajectoryConfidence
                                ?? result.trajectoryQuality?.confidence
                                ?? 0
                        ),
                        provisional: false,
                        validity: finalTrajectoryValidity,
                        impactIndex: impactIndex,
                        phaseIndices: [],
                        disclaimer: "精修轨迹来自完整分析；投影仅表达腕部路径形状。"
                    )
                } else if finalTrajectoryValidity == "abstain" {
                    trajectoryAbstainCard
                }

                PhaseTimelineView(
                    phases: result.phases,
                    sampleRateHz: result.sourceRatesHz?.deviceMotion
                        ?? result.meta?.fs_hz
                )

                if !remainingTruth.isEmpty {
                    truthSection
                }

                if !inferredMetrics.isEmpty || abstainedInferenceCount > 0 {
                    inferredSection
                }

                if !findings.isEmpty {
                    findingsSection
                }
            }
            .padding(20)
        }
        .background(Color(.systemBackground))
        .navigationTitle("挥杆分析")
        .navigationBarTitleDisplayMode(.inline)
    }

    private var trajectoryAbstainCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("手腕轨迹")
                    .font(.headline)
                Spacer()
                TrustBadge(level: .abstain, compact: true)
            }
            Text("本杆轨迹质量未通过门限，因此不显示路径图。")
                .font(.footnote)
                .foregroundStyle(.secondary)
            if let reason = result.meta?.feature_quality?["path"]?.reasons?.first {
                Label(MetricCopy.reason(reason), systemImage: "info.circle")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .golfSurface()
        .accessibilityElement(children: .combine)
    }

    private var practiceVerdict: some View {
        let practice = report?.practice_loop
        let inWindow = practice?.in_window
        return VStack(alignment: .leading, spacing: 10) {
            HStack {
                Label(
                    inWindow == true ? "进入个人窗口" : "下一杆关注",
                    systemImage: inWindow == true
                        ? "checkmark.circle.fill"
                        : "scope"
                )
                .font(.headline)
                .foregroundStyle(
                    inWindow == true ? GolfTheme.verified : GolfTheme.warning
                )
                Spacer()
                if let focus = practice?.focus_kpi {
                    Text(MetricCopy.title(for: focus))
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.secondary)
                }
            }
            Text(MetricCopy.cue(practice?.suggested_cue))
                .font(.title3.weight(.semibold))
            Text("判断基于个人基线与本杆有效指标，不使用通用“标准挥杆”作为唯一答案。")
                .font(.footnote)
                .foregroundStyle(.secondary)
        }
        .golfSurface()
        .accessibilityElement(children: .combine)
    }

    private var focusSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            GolfSectionHeader(
                title: "关注指标",
                subtitle: practiceFocusSubtitle
            )
            VStack(spacing: 4) {
                ForEach(focusMetrics) { metric in
                    CommercialMetricRow(metric: metric, emphasize: true)
                    if metric.id != focusMetrics.last?.id {
                        Divider()
                    }
                }
            }
            .golfSurface()
        }
    }

    private func legacyFocusSection(_ features: SwingAnalysisResult.FeatureBundle) -> some View {
        let rows: [(String, Double?, String)] = [
            ("挥杆时长", features.tempo_s, "s"),
            ("节奏比", features.rhythm, "×"),
            ("手腕峰值速度", features.hand_speed_peak_m_s, "m/s"),
        ]
        return VStack(alignment: .leading, spacing: 12) {
            GolfSectionHeader(title: "关注指标", subtitle: "来自基础特征")
            VStack(alignment: .leading, spacing: 10) {
                ForEach(Array(rows.enumerated()), id: \.offset) { _, row in
                    HStack {
                        Text(row.0)
                            .font(.subheadline.weight(.medium))
                        Spacer()
                        Text(MetricCopy.formatValue(row.1, units: row.2))
                            .font(.body.monospacedDigit().weight(.semibold))
                    }
                    .accessibilityElement(children: .combine)
                }
            }
            .golfSurface()
        }
    }

    private var truthSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            GolfSectionHeader(
                title: "可引用指标",
                subtitle: "实测或计算层，含有效性标记"
            )
            VStack(spacing: 4) {
                ForEach(remainingTruth) { metric in
                    CommercialMetricRow(metric: metric)
                    if metric.id != remainingTruth.last?.id {
                        Divider()
                    }
                }
            }
            .golfSurface()
        }
    }

    private var inferredSection: some View {
        DisclosureGroup(isExpanded: $showInferred) {
            VStack(alignment: .leading, spacing: 8) {
                if inferredMetrics.isEmpty {
                    Text("本杆高阶指标均未通过质量门，因此不显示推断数值。")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                } else {
                    ForEach(inferredMetrics) { metric in
                        CommercialMetricRow(metric: metric)
                        if metric.id != inferredMetrics.last?.id {
                            Divider()
                        }
                    }
                }
                if abstainedInferenceCount > 0 {
                    Text("\(abstainedInferenceCount) 项推断因质量不足未输出")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            .padding(.top, 8)
        } label: {
            VStack(alignment: .leading, spacing: 4) {
                Text("推断与代理指标")
                    .font(.headline)
                Text("非实测层；仅显示通过各自校准门的指标")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(16)
        .background(
            GolfTheme.quietSurface,
            in: RoundedRectangle(
                cornerRadius: GolfTheme.cornerRadius,
                style: .continuous
            )
        )
        .accessibilityHint("展开查看推断与代理指标")
    }

    private var findingsSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            GolfSectionHeader(
                title: "要点",
                subtitle: "最多三条，含代理 / 推断标记"
            )
            VStack(spacing: 10) {
                ForEach(findings) { finding in
                    FindingRow(finding: finding)
                }
            }
        }
    }

    private var practiceFocusSubtitle: String? {
        if let kpi = report?.practice_loop?.focus_kpi, !kpi.isEmpty {
            return "练习焦点：\(MetricCopy.title(for: kpi))"
        }
        return "本杆优先阅读的核心数字"
    }
}

#if DEBUG
#Preview {
    NavigationStack {
        SwingAnalysisView(
            result: SwingAnalysisResult(
                schemaVersion: "1",
                ok: true,
                captureMode: "high_rate",
                sourceRatesHz: .init(accelerometer: 200, deviceMotion: 100),
                highRateImpactHintS: 0.012,
                phases: .init(address: 10, top: 80, impact: 110, finish: 160),
                features: .init(
                    tempo_s: 1.2,
                    backswing_s: 0.9,
                    downswing_s: 0.3,
                    rhythm: 3.0,
                    peak_omega_rad_s: 12,
                    peak_omega_to_impact_s: 0.04,
                    hand_speed_peak_m_s: 8.5,
                    plane_angle_deg: 48,
                    closure_rate_rad_s: nil
                ),
                findings: [
                    .init(
                        code: "casting_proxy",
                        severity: "warning",
                        message: "过渡段释放偏早。",
                        is_proxy: true,
                        kind: "proxy"
                    ),
                ],
                finalTrajectory: [[0, 0, 0], [0.1, 0, 0.2], [0.2, 0, 0.05]],
                trajectoryConfidence: 0.8,
                trajectoryQuality: .init(
                    confidence: 0.8,
                    validity: "ok",
                    reasons: nil,
                    pointCount: 3,
                    source: "full"
                ),
                commercialReport: .init(
                    version: "commercial-swing-report-v2",
                    truth: [
                        .init(
                            name: "tempo_s",
                            value: 1.2,
                            units: "s",
                            kind: "derived",
                            validity: "ok",
                            confidence: 0.9,
                            residual: nil,
                            reasons: nil
                        ),
                        .init(
                            name: "rhythm",
                            value: 3.0,
                            units: "×",
                            kind: "derived",
                            validity: "ok",
                            confidence: 0.85,
                            residual: nil,
                            reasons: nil
                        ),
                        .init(
                            name: "hand_speed_peak_m_s",
                            value: 8.5,
                            units: "m/s",
                            kind: "derived",
                            validity: "ok",
                            confidence: 0.8,
                            residual: nil,
                            reasons: nil
                        ),
                    ],
                    inference: [
                        .init(
                            name: "clubface_impact_deg",
                            value: nil,
                            units: "°",
                            kind: "inferred",
                            validity: "abstain",
                            confidence: 0.2,
                            residual: nil,
                            reasons: ["low_confidence"]
                        ),
                    ],
                    findings: nil,
                    personal_baseline: nil,
                    practice_loop: nil,
                    strategy: nil
                ),
                meta: .init(
                    impact_mode: nil,
                    impact_method: "accel",
                    impact_confidence: 0.8,
                    impact_provenance: nil,
                    fs_hz: 100,
                    truth_quality: .init(
                        overall_validity: "ok",
                        overall_confidence: 0.82,
                        impact_provenance: nil,
                        reasons: nil,
                        layers: nil
                    ),
                    feature_quality: nil
                ),
                error: nil
            )
        )
    }
}
#endif
