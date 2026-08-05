import SwiftUI

struct PhaseTimelineView: View {
    let phases: SwingAnalysisResult.PhaseIndices?
    let sampleRateHz: Double?

    private var markers: [(label: String, seconds: Double?)] {
        [
            ("站位", seconds(for: phases?.address)),
            ("顶点", seconds(for: phases?.top)),
            ("击球", seconds(for: phases?.impact)),
            ("收杆", seconds(for: phases?.finish)),
        ]
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            GolfSectionHeader(
                title: "阶段时间轴",
                subtitle: "以秒为单位，相对挥杆起点"
            )

            ViewThatFits(in: .horizontal) {
                HStack(spacing: 0) {
                    ForEach(Array(markers.enumerated()), id: \.offset) { index, marker in
                        phaseCell(marker)
                        if index < markers.count - 1 {
                            connector
                        }
                    }
                }
                VStack(alignment: .leading, spacing: 10) {
                    ForEach(Array(markers.enumerated()), id: \.offset) { _, marker in
                        HStack {
                            Text(marker.label)
                                .font(.subheadline.weight(.medium))
                            Spacer()
                            Text(format(marker.seconds))
                                .font(.body.monospacedDigit().weight(.semibold))
                        }
                    }
                }
            }
        }
        .golfSurface()
        .accessibilityElement(children: .combine)
        .accessibilityLabel(accessibilitySummary)
    }

    private func phaseCell(_ marker: (label: String, seconds: Double?)) -> some View {
        VStack(spacing: 6) {
            Circle()
                .fill(marker.seconds == nil ? Color.secondary.opacity(0.35) : GolfTheme.live)
                .frame(width: 10, height: 10)
                .accessibilityHidden(true)
            Text(marker.label)
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)
            Text(format(marker.seconds))
                .font(.subheadline.monospacedDigit().weight(.semibold))
        }
        .frame(maxWidth: .infinity)
    }

    private var connector: some View {
        Rectangle()
            .fill(Color.secondary.opacity(0.25))
            .frame(height: 2)
            .frame(maxWidth: 28)
            .padding(.bottom, 28)
            .accessibilityHidden(true)
    }

    private func seconds(for index: Int?) -> Double? {
        guard
            let index,
            let address = phases?.address,
            let fs = sampleRateHz,
            fs > 0
        else { return nil }
        return Double(index - address) / fs
    }

    private func format(_ seconds: Double?) -> String {
        guard let seconds else { return "—" }
        return String(format: "%.2f s", seconds)
    }

    private var accessibilitySummary: String {
        markers
            .map { "\($0.label) \(format($0.seconds))" }
            .joined(separator: "，")
    }
}

#if DEBUG
#Preview {
    PhaseTimelineView(
        phases: .init(address: 10, top: 80, impact: 110, finish: 160),
        sampleRateHz: 100
    )
    .padding()
}
#endif
