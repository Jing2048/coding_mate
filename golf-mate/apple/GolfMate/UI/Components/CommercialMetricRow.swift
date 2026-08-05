import SwiftUI

struct CommercialMetricRow: View {
    let metric: SwingAnalysisResult.CommercialMetric
    var emphasize = false

    var body: some View {
        ViewThatFits(in: .horizontal) {
            HStack(alignment: .firstTextBaseline, spacing: 12) {
                titleBlock
                Spacer(minLength: 8)
                valueBlock
            }
            VStack(alignment: .leading, spacing: 8) {
                titleBlock
                valueBlock
            }
        }
        .padding(.vertical, 6)
        .accessibilityElement(children: .combine)
        .accessibilityLabel(accessibilitySummary)
    }

    private var titleBlock: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(MetricCopy.title(for: metric.name))
                .font(emphasize ? .body.weight(.semibold) : .subheadline.weight(.medium))
                .foregroundStyle(.primary)
                .fixedSize(horizontal: false, vertical: true)
            HStack(spacing: 6) {
                TrustBadge(level: metric.trustLevel, compact: true)
                validityChip
            }
        }
    }

    @ViewBuilder
    private var valueBlock: some View {
        let units = MetricCopy.displayUnits(for: metric.name, raw: metric.units)
        if metric.isAvailable {
            Text(
                MetricCopy.formatValue(
                    metric.value,
                    units: units,
                    digits: MetricCopy.digits(for: units)
                )
            )
            .font(.title3.monospacedDigit().weight(.semibold))
            .foregroundStyle(.primary)
            .accessibilityAddTraits(.isStaticText)
        } else {
            VStack(alignment: .trailing, spacing: 2) {
                Text("未输出")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(.secondary)
                if let reason = metric.reasons?.first, !reason.isEmpty {
                    Text(MetricCopy.reason(reason))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.trailing)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
    }

    private var validityChip: some View {
        let label: String
        let color: Color
        switch metric.validity {
        case "ok":
            label = "有效"
            color = GolfTheme.verified
        case "degraded":
            label = "质量受限"
            color = GolfTheme.warning
        case "abstain":
            label = "弃权"
            color = .secondary
        default:
            label = metric.validity
            color = .secondary
        }
        return Text(label)
            .font(.caption2.weight(.semibold))
            .foregroundStyle(color)
            .padding(.horizontal, 6)
            .padding(.vertical, 3)
            .background(color.opacity(0.12), in: Capsule())
            .accessibilityLabel("有效性：\(label)")
    }

    private var accessibilitySummary: String {
        let title = MetricCopy.title(for: metric.name)
        if metric.isAvailable {
            let units = MetricCopy.displayUnits(for: metric.name, raw: metric.units)
            let value = MetricCopy.formatValue(
                metric.value,
                units: units,
                digits: MetricCopy.digits(for: units)
            )
            return "\(title)，\(metric.trustLevel.title)，\(value)"
        }
        let reason = metric.reasons?.first.map(MetricCopy.reason) ?? "质量不足"
        return "\(title)，未输出，原因：\(reason)"
    }
}

#if DEBUG
#Preview {
    List {
        CommercialMetricRow(
            metric: .init(
                name: "tempo_s",
                value: 1.24,
                units: "s",
                kind: "derived",
                validity: "ok",
                confidence: 0.9,
                residual: nil,
                reasons: nil
            ),
            emphasize: true
        )
        CommercialMetricRow(
            metric: .init(
                name: "clubface_impact_deg",
                value: nil,
                units: "°",
                kind: "inferred",
                validity: "abstain",
                confidence: 0.2,
                residual: nil,
                reasons: ["low_confidence"]
            )
        )
    }
}
#endif
