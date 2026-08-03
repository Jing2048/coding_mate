import SwiftUI

struct SwingAnalysisView: View {
    let result: SwingAnalysisResult

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                fidelityBanner
                metricGrid
                phaseRow
                if let findings = result.findings, !findings.isEmpty {
                    findingsBlock(findings)
                }
            }
            .padding(20)
        }
        .navigationTitle("完整算法结果")
        .navigationBarTitleDisplayMode(.inline)
    }

    private var fidelityBanner: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("FULL PYTHON PIPELINE")
                .font(.caption.weight(.bold))
                .tracking(1.2)
                .foregroundStyle(.cyan)
            Text(rateLine)
                .font(.footnote)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(14)
        .background(
            LinearGradient(
                colors: [
                    Color(red: 0.02, green: 0.14, blue: 0.18),
                    Color.black.opacity(0.2),
                ],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            ),
            in: RoundedRectangle(cornerRadius: 16, style: .continuous)
        )
    }

    private var rateLine: String {
        let rates = result.sourceRatesHz
        let hint = result.highRateImpactHintS.map { String(format: "impact hint %.1f ms", $0 * 1000) }
            ?? "impact hint n/a"
        let method = result.meta?.impact_method ?? "—"
        if let rates {
            return String(
                format: "%.0f Hz ACC · %.0f Hz Motion · %@ · %@",
                rates.accelerometer,
                rates.deviceMotion,
                hint,
                method
            )
        }
        return hint
    }

    private var metricGrid: some View {
        let features = result.features
        return LazyVGrid(
            columns: [GridItem(.flexible()), GridItem(.flexible())],
            spacing: 12
        ) {
            metric("Tempo", value: features?.tempo_s, unit: "s", digits: 2)
            metric("Rhythm", value: features?.rhythm, unit: "×", digits: 2)
            metric("Peak ω", value: features?.peak_omega_rad_s, unit: "rad/s", digits: 1)
            metric("Hand speed", value: features?.hand_speed_peak_m_s, unit: "m/s", digits: 1)
            metric("Plane", value: features?.plane_angle_deg, unit: "°", digits: 1)
            metric("Downswing", value: features?.downswing_s, unit: "s", digits: 2)
        }
    }

    private func metric(
        _ title: String,
        value: Double?,
        unit: String,
        digits: Int
    ) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title.uppercased())
                .font(.caption2.weight(.semibold))
                .foregroundStyle(.secondary)
            HStack(alignment: .firstTextBaseline, spacing: 4) {
                Text(value.map { String(format: "%.\(digits)f", $0) } ?? "—")
                    .font(.title3.monospacedDigit().weight(.semibold))
                Text(unit)
                    .font(.caption.weight(.medium))
                    .foregroundStyle(.secondary)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(12)
        .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
    }

    private var phaseRow: some View {
        let phases = result.phases
        return VStack(alignment: .leading, spacing: 8) {
            Text("PHASES")
                .font(.caption.weight(.bold))
                .foregroundStyle(.secondary)
            HStack {
                phaseChip("ADD", phases?.address)
                phaseChip("TOP", phases?.top)
                phaseChip("IMP", phases?.impact)
                phaseChip("FIN", phases?.finish)
            }
        }
    }

    private func phaseChip(_ label: String, _ index: Int?) -> some View {
        VStack(spacing: 2) {
            Text(label)
                .font(.caption2.weight(.bold))
                .foregroundStyle(.cyan)
            Text(index.map(String.init) ?? "—")
                .font(.footnote.monospacedDigit())
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 8)
        .background(Color.cyan.opacity(0.08), in: RoundedRectangle(cornerRadius: 12))
    }

    private func findingsBlock(_ findings: [SwingAnalysisResult.Finding]) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("FINDINGS")
                .font(.caption.weight(.bold))
                .foregroundStyle(.secondary)
            ForEach(findings) { finding in
                VStack(alignment: .leading, spacing: 2) {
                    Text(finding.code)
                        .font(.caption.weight(.bold))
                        .foregroundStyle(finding.severity == "critical" ? .red : .primary)
                    Text(finding.message)
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(10)
                .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 12))
            }
        }
    }
}
