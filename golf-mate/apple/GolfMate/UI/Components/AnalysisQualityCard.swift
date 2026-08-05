import SwiftUI

struct AnalysisQualityCard: View {
    let result: SwingAnalysisResult

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            GolfSectionHeader(
                title: "质量与可信度",
                subtitle: qualitySubtitle
            )

            ViewThatFits(in: .horizontal) {
                HStack(alignment: .top, spacing: 16) {
                    trustSummary
                    Spacer(minLength: 8)
                    confidenceBlock
                }
                VStack(alignment: .leading, spacing: 12) {
                    trustSummary
                    confidenceBlock
                }
            }

            if let reasons = truthReasons, !reasons.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(reasons.prefix(3), id: \.self) { reason in
                        Label(MetricCopy.reason(reason), systemImage: "info.circle")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
            }
        }
        .golfSurface()
        .accessibilityElement(children: .combine)
        .accessibilityLabel(accessibilitySummary)
    }

    private var trustSummary: some View {
        VStack(alignment: .leading, spacing: 8) {
            qualityBadge
            Text(overallCaption)
                .font(.footnote)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private var confidenceBlock: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("综合置信")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)
            Text(confidenceText)
                .font(.title2.monospacedDigit().weight(.semibold))
                .foregroundStyle(confidenceColor)
            Text(validityText)
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .accessibilityElement(children: .combine)
    }

    private var validityRaw: String {
        result.meta?.truth_quality?.overall_validity
            ?? result.trajectoryQuality?.validity
            ?? (result.ok ? "ok" : "degraded")
    }

    private var qualityBadge: some View {
        let title: String
        let symbol: String
        let color: Color
        switch validityRaw {
        case "ok":
            title = "质量正常"
            symbol = "checkmark.circle.fill"
            color = GolfTheme.verified
        case "abstain":
            title = "关键层弃权"
            symbol = "minus.circle"
            color = .secondary
        default:
            title = "质量受限"
            symbol = "exclamationmark.triangle.fill"
            color = GolfTheme.warning
        }
        return Label(title, systemImage: symbol)
            .font(.caption.weight(.semibold))
            .foregroundStyle(color)
            .padding(.horizontal, 8)
            .padding(.vertical, 5)
            .background(color.opacity(0.12), in: Capsule())
    }

    private var overallCaption: String {
        switch validityRaw {
        case "ok":
            return "可引用层指标质量正常"
        case "abstain":
            return "关键指标已弃权，未给出数字"
        default:
            return "部分指标质量受限，请结合说明阅读"
        }
    }

    private var confidenceText: String {
        let value = result.meta?.truth_quality?.overall_confidence
            ?? result.trajectoryConfidence
            ?? result.trajectoryQuality?.confidence
        guard let value else { return "—" }
        return "\(Int((value * 100).rounded()))%"
    }

    private var confidenceColor: Color {
        switch validityRaw {
        case "ok": return .primary
        case "abstain": return .secondary
        default: return GolfTheme.warning
        }
    }

    private var validityText: String {
        switch validityRaw {
        case "ok": return "有效性：正常"
        case "degraded": return "有效性：受限"
        case "abstain": return "有效性：弃权"
        default: return "有效性：未知"
        }
    }

    private var qualitySubtitle: String? {
        if let mode = result.captureMode {
            let label = mode == "compat" ? "兼容采集" : "高速采集"
            return label
        }
        return nil
    }

    private var truthReasons: [String]? {
        result.meta?.truth_quality?.reasons ?? result.trajectoryQuality?.reasons
    }

    private var accessibilitySummary: String {
        "\(overallCaption)，\(confidenceText)，\(validityText)"
    }

}

#if DEBUG
#Preview {
    AnalysisQualityCard(
        result: SwingAnalysisResult(
            schemaVersion: "1",
            ok: true,
            captureMode: "high_rate",
            sourceRatesHz: nil,
            highRateImpactHintS: nil,
            phases: nil,
            features: nil,
            findings: nil,
            finalTrajectory: nil,
            trajectoryConfidence: 0.82,
            trajectoryQuality: .init(
                confidence: 0.82,
                validity: "ok",
                reasons: nil,
                pointCount: 64,
                source: "full"
            ),
            commercialReport: nil,
            meta: .init(
                impact_mode: nil,
                impact_method: nil,
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
    .padding()
}
#endif
