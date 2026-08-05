import SwiftUI

struct FindingRow: View {
    let finding: SwingAnalysisResult.Finding

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            ViewThatFits(in: .horizontal) {
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Text(MetricCopy.findingTitle(for: finding.code))
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(severityColor)
                        .fixedSize(horizontal: false, vertical: true)
                    Spacer(minLength: 8)
                    badgeStack
                }
                VStack(alignment: .leading, spacing: 6) {
                    Text(MetricCopy.findingTitle(for: finding.code))
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(severityColor)
                        .fixedSize(horizontal: false, vertical: true)
                    badgeStack
                }
            }

            Text(MetricCopy.findingBody(for: finding.code, fallback: finding.message))
                .font(.footnote)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(12)
        .background(
            GolfTheme.quietSurface,
            in: RoundedRectangle(
                cornerRadius: GolfTheme.compactCornerRadius,
                style: .continuous
            )
        )
        .accessibilityElement(children: .combine)
        .accessibilityLabel(accessibilitySummary)
    }

    private var badgeStack: some View {
        HStack(spacing: 6) {
            TrustBadge(level: finding.trustLevel, compact: true)
            severityChip
        }
    }

    private var severityChip: some View {
        let label: String
        switch finding.severity {
        case "critical": label = "需关注"
        case "warn", "warning": label = "提示"
        case "info": label = "信息"
        default: label = finding.severity
        }
        return Text(label)
            .font(.caption2.weight(.semibold))
            .foregroundStyle(severityColor)
            .padding(.horizontal, 6)
            .padding(.vertical, 3)
            .background(severityColor.opacity(0.12), in: Capsule())
            .accessibilityLabel("严重程度：\(label)")
    }

    private var severityColor: Color {
        switch finding.severity {
        case "critical": return GolfTheme.destructive
        case "warn", "warning": return GolfTheme.warning
        default: return .primary
        }
    }

    private var accessibilitySummary: String {
        let title = MetricCopy.findingTitle(for: finding.code)
        let body = MetricCopy.findingBody(for: finding.code, fallback: finding.message)
        return "\(title)，\(finding.trustLevel.title)，\(body)"
    }
}

#if DEBUG
#Preview {
    FindingRow(
        finding: .init(
            code: "casting_proxy",
            severity: "warning",
            message: "过渡段释放偏早，可能影响杆头速度传递。",
            is_proxy: true,
            kind: "proxy"
        )
    )
    .padding()
}
#endif
