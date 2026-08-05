import SwiftUI

struct TrajectoryPathView: View {
    let points: [TrajectoryPoint]
    var title: String = "手腕轨迹"
    var confidence: Float = 0
    var provisional: Bool = false
    var validity: String? = nil
    var impactIndex: Int? = nil
    var phaseIndices: [Int] = []
    var disclaimer: String? = nil

    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    private var trust: TrustLevel {
        if provisional { return .provisional }
        return .derived
    }

    private var strokeColor: Color {
        provisional ? GolfTheme.live : Color.primary
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            ViewThatFits(in: .horizontal) {
                HStack(alignment: .firstTextBaseline) {
                    Text(title)
                        .font(.headline)
                    Spacer(minLength: 8)
                    TrustBadge(level: trust, compact: true)
                    if validity == "degraded" {
                        TrustBadge(level: .degraded, compact: true)
                    }
                }
                VStack(alignment: .leading, spacing: 6) {
                    Text(title)
                        .font(.headline)
                    TrustBadge(level: trust, compact: true)
                    if validity == "degraded" {
                        TrustBadge(level: .degraded, compact: true)
                    }
                }
            }

            legendRow

            ZStack {
                RoundedRectangle(
                    cornerRadius: GolfTheme.cornerRadius,
                    style: .continuous
                )
                .fill(Color(.secondarySystemBackground))

                if points.count >= 2 {
                    Canvas { context, size in
                        let rendered = project(points, size: size)
                        guard let first = rendered.first else { return }

                        var path = Path()
                        path.move(to: first)
                        for point in rendered.dropFirst() {
                            path.addLine(to: point)
                        }
                        context.stroke(
                            path,
                            with: .color(strokeColor.opacity(0.9)),
                            style: StrokeStyle(
                                lineWidth: 3,
                                lineCap: .round,
                                lineJoin: .round
                            )
                        )

                        for index in phaseIndices where index >= 0 && index < rendered.count {
                            let point = rendered[index]
                            let rect = CGRect(x: point.x - 3.5, y: point.y - 3.5, width: 7, height: 7)
                            context.fill(
                                Path(ellipseIn: rect),
                                with: .color(Color.secondary.opacity(0.85))
                            )
                        }

                        if let impactIndex,
                           impactIndex >= 0,
                           impactIndex < rendered.count
                        {
                            let point = rendered[impactIndex]
                            let outer = CGRect(
                                x: point.x - 6,
                                y: point.y - 6,
                                width: 12,
                                height: 12
                            )
                            context.stroke(
                                Path(ellipseIn: outer),
                                with: .color(GolfTheme.warning),
                                lineWidth: 2
                            )
                            let inner = CGRect(
                                x: point.x - 2.5,
                                y: point.y - 2.5,
                                width: 5,
                                height: 5
                            )
                            context.fill(
                                Path(ellipseIn: inner),
                                with: .color(GolfTheme.warning)
                            )
                        }
                    }
                    .accessibilityHidden(true)
                } else {
                    Text("暂无轨迹点")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
            }
            .frame(height: 200)

            Text(disclaimerText)
                .font(.caption)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)

            if !reduceMotion, provisional {
                Label("实时预览，分析完成后会替换为精修轨迹", systemImage: "waveform.path")
                    .font(.caption2)
                    .foregroundStyle(GolfTheme.live)
            }
        }
        .padding(16)
        .background(
            Color(.secondarySystemBackground).opacity(0.55),
            in: RoundedRectangle(
                cornerRadius: GolfTheme.cornerRadius,
                style: .continuous
            )
        )
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(accessibilitySummary)
        .accessibilityHint("二维投影仅供参考，不是三维空间真实路径")
    }

    private var legendRow: some View {
        ViewThatFits(in: .horizontal) {
            HStack(spacing: 14) {
                legendItem(color: strokeColor, title: "腕部路径")
                if impactIndex != nil {
                    legendItem(color: GolfTheme.warning, title: "击球")
                }
                if !phaseIndices.isEmpty {
                    legendItem(color: .secondary, title: "阶段")
                }
                Spacer(minLength: 0)
                Text("置信 \(Int((confidence * 100).rounded()))%")
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(.secondary)
            }
            VStack(alignment: .leading, spacing: 6) {
                legendItem(color: strokeColor, title: "腕部路径")
                if impactIndex != nil {
                    legendItem(color: GolfTheme.warning, title: "击球标记")
                }
                Text("置信 \(Int((confidence * 100).rounded()))%")
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(.secondary)
            }
        }
    }

    private func legendItem(color: Color, title: String) -> some View {
        HStack(spacing: 6) {
            Capsule()
                .fill(color)
                .frame(width: 14, height: 3)
            Text(title)
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .accessibilityElement(children: .combine)
    }

    private var disclaimerText: String {
        disclaimer
            ?? "图示为手腕路径的二维投影，用于理解挥杆形状；颜色不单独表示质量。"
    }

    private var accessibilitySummary: String {
        let kind = provisional ? "预览" : "精修"
        let impact = impactIndex == nil ? "" : "，含击球标记"
        return "\(kind)手腕轨迹，\(points.count) 个点，置信度 \(Int((confidence * 100).rounded()))%，\(trust.title)\(impact)。\(disclaimerText)"
    }

    private func project(_ points: [TrajectoryPoint], size: CGSize) -> [CGPoint] {
        guard points.count >= 2 else { return [] }
        let xs = points.map(\.x)
        let zs = points.map(\.z)
        guard
            let minX = xs.min(),
            let maxX = xs.max(),
            let minZ = zs.min(),
            let maxZ = zs.max()
        else { return [] }
        let spanX = max(maxX - minX, 0.05)
        let spanZ = max(maxZ - minZ, 0.05)
        let inset: CGFloat = 18
        return points.map {
            CGPoint(
                x: inset + CGFloat(($0.x - minX) / spanX) * (size.width - 2 * inset),
                y: size.height - inset
                    - CGFloat(($0.z - minZ) / spanZ) * (size.height - 2 * inset)
            )
        }
    }
}

#if DEBUG
#Preview {
    TrajectoryPathView(
        points: [
            .init(x: 0, y: 0, z: 0),
            .init(x: 0.1, y: 0.05, z: 0.2),
            .init(x: 0.2, y: 0.1, z: 0.15),
            .init(x: 0.25, y: 0.05, z: 0.0),
        ],
        title: "最终手腕轨迹",
        confidence: 0.84,
        provisional: false,
        validity: "ok",
        impactIndex: 2,
        phaseIndices: [0, 1, 2, 3]
    )
    .padding()
}
#endif
