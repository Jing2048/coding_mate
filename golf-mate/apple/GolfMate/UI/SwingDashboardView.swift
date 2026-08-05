import SwiftUI

/// Production swing home: Watch capture → preview → analysis → result.
struct SwingDashboardView: View {
    @ObservedObject private var receiver = PhoneCaptureReceiver.shared
    @ObservedObject private var analysis = AnalysisClient.shared
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    private enum Status: Equatable {
        case waiting
        case preview
        case captured
        case analyzing
        case analyzed
        case error
    }

    private var status: Status {
        if analysis.isAnalyzing { return .analyzing }
        if
            analysis.lastError != nil,
            analysis.lastAttemptedURL == receiver.latestCaptureURL
        {
            return .error
        }
        if
            analysis.lastResult != nil,
            analysis.lastAnalyzedURL == receiver.latestCaptureURL
        {
            return .analyzed
        }
        if receiver.latestCaptureURL != nil { return .captured }
        if analysis.lastResult != nil { return .analyzed }
        if let preview = receiver.latestPreview, !preview.points.isEmpty {
            return .preview
        }
        return .waiting
    }

    var body: some View {
        ScrollView {
            VStack(spacing: GolfTheme.sectionSpacing) {
                statusHero

                if shouldShowPreview,
                   let preview = receiver.latestPreview,
                   !preview.points.isEmpty
                {
                    TrajectoryPathView(
                        points: preview.points,
                        title: analysis.lastResult == nil ? "领先腕预览轨迹" : "预览轨迹（分析中保留）",
                        confidence: preview.confidence,
                        provisional: true,
                        validity: nil,
                        impactIndex: nil,
                        phaseIndices: [],
                        disclaimer: "Watch 端即时预览，分析完成前持续可见。"
                    )
                }

                if status != .waiting {
                    progressCard
                }

                if let result = analysis.lastResult {
                    lastResultCard(result)
                }

                if case .error = status {
                    errorCard
                }

            }
            .padding(20)
        }
        .background(Color(.systemBackground))
        .navigationTitle("Golf-ai-Jing")
        .navigationBarTitleDisplayMode(.large)
        .onChange(of: receiver.captureRevision) { _, _ in
            analyzeLatest(force: true)
        }
        .task {
            analyzeLatest(force: false)
        }
    }

    // MARK: - Status

    private var statusHero: some View {
        VStack(spacing: 14) {
            statusIcon
                .font(.system(size: 44, weight: .light))
                .foregroundStyle(statusColor)
                .accessibilityHidden(true)

            Text(statusTitle)
                .font(.title2.weight(.semibold))
                .multilineTextAlignment(.center)

            Text(statusSubtitle)
                .font(.callout)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)

        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 8)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(statusTitle)。\(statusSubtitle)")
    }

    @ViewBuilder
    private var statusIcon: some View {
        let name = statusSymbol
        if !reduceMotion, status == .waiting || status == .analyzing {
            Image(systemName: name)
                .symbolEffect(.pulse, isActive: true)
        } else {
            Image(systemName: name)
        }
    }

    private var statusSymbol: String {
        switch status {
        case .waiting: return "applewatch.radiowaves.left.and.right"
        case .preview: return "waveform.path.ecg"
        case .captured: return "tray.and.arrow.down"
        case .analyzing: return "waveform.path.ecg"
        case .analyzed: return "checkmark.seal"
        case .error: return "exclamationmark.triangle"
        }
    }

    private var statusColor: Color {
        switch status {
        case .waiting: return .secondary
        case .preview: return GolfTheme.live
        case .captured: return GolfTheme.live
        case .analyzing: return GolfTheme.live
        case .analyzed: return GolfTheme.verified
        case .error: return GolfTheme.destructive
        }
    }

    private var statusTitle: String {
        switch status {
        case .waiting: return "等待 Apple Watch"
        case .preview: return "已收到预览轨迹"
        case .captured: return "采集已到达"
        case .analyzing: return "正在分析"
        case .analyzed: return "分析完成"
        case .error: return "分析未完成"
        }
    }

    private var statusSubtitle: String {
        switch status {
        case .waiting:
            return "在 Watch 上完成一杆采集后，预览与结果会显示在这里。"
        case .preview:
            return "即时轨迹已到达。完整采集文件到达后将自动开始分析。"
        case .captured:
            return "原始采集已收到，准备开始分析。"
        case .analyzing:
            return "正在处理本杆数据。预览轨迹保持可见，上一杆有效结果不会被清除。"
        case .analyzed:
            return "可查看质量摘要、关注指标与手腕轨迹。"
        case .error:
            if analysis.lastResult != nil {
                return "本杆分析出错，仍保留上一杆有效结果。可重试或检查设置中的服务连接。"
            }
            return "分析出错。请重试，或到设置中检查分析服务。"
        }
    }

    // MARK: - Progress / error / result

    private var progressCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            GolfSectionHeader(
                title: "进度",
                subtitle: connectionLine
            )

            if analysis.isAnalyzing {
                ProgressView()
                    .progressViewStyle(.linear)
                    .tint(GolfTheme.live)
                    .accessibilityLabel("分析进行中")
            }

            HStack(spacing: 12) {
                if let url = receiver.latestCaptureURL {
                    Button {
                        Task { await analysis.analyze(captureFile: url) }
                    } label: {
                        Label(
                            analysis.isAnalyzing ? "分析中…" : "重新分析",
                            systemImage: "arrow.clockwise"
                        )
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(GolfTheme.live)
                    .disabled(analysis.isAnalyzing)
                }

                if status == .error {
                    Button("清除错误") {
                        analysis.clearError()
                    }
                    .buttonStyle(.bordered)
                }
            }
        }
        .golfSurface()
    }

    private var errorCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            Label("分析错误", systemImage: "exclamationmark.triangle.fill")
                .font(.headline)
                .foregroundStyle(GolfTheme.destructive)
            Text(analysis.lastError ?? "未知错误")
                .font(.footnote)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            if let url = receiver.latestCaptureURL {
                Button {
                    analysis.clearError()
                    Task { await analysis.analyze(captureFile: url) }
                } label: {
                    Label("重试本杆", systemImage: "arrow.clockwise")
                }
                .buttonStyle(.borderedProminent)
                .tint(GolfTheme.destructive)
                .disabled(analysis.isAnalyzing)
            }
            Text("如仍无法完成，请在「设置」中检查分析连接。")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .golfSurface()
        .accessibilityElement(children: .contain)
    }

    private func lastResultCard(_ result: SwingAnalysisResult) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            GolfSectionHeader(
                title: status == .error ? "上一杆有效结果" : "本杆结果",
                subtitle: resultSummary(result)
            )
            NavigationLink {
                SwingAnalysisView(result: result)
            } label: {
                Label("查看挥杆分析", systemImage: "chart.line.uptrend.xyaxis")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            .tint(GolfTheme.verified)
        }
        .golfSurface()
    }

    // MARK: - Helpers

    private var shouldShowPreview: Bool {
        guard let preview = receiver.latestPreview, !preview.points.isEmpty else {
            return false
        }
        // Keep preview visible through capture/analysis; hide once we have final
        // trajectory on success (still show if analyzing or error without replacing).
        if analysis.isAnalyzing { return true }
        if status == .error { return true }
        if
            let result = analysis.lastResult,
            analysis.lastAnalyzedURL == receiver.latestCaptureURL,
            !result.finalTrajectoryPoints.isEmpty
        {
            return false
        }
        return true
    }

    private var connectionLine: String {
        switch receiver.connectionState {
        case .activating: return "正在连接 Watch…"
        case .paired: return "Watch 已配对"
        case .notPaired: return "未检测到已配对的 Watch"
        case .unsupported: return "此设备不支持 Watch 连接"
        case let .failed(message): return message
        }
    }

    private func resultSummary(_ result: SwingAnalysisResult) -> String {
        if let tempo = result.commercialReport?.truth.first(where: { $0.name == "tempo_s" }),
           tempo.isAvailable,
           let value = tempo.value
        {
            let quality = tempo.validity == "degraded" ? " · 质量受限" : ""
            return String(format: "站位至击球 %.2f s%@", value, quality)
        }
        if let tempo = result.features?.tempo_s {
            return String(format: "挥杆时长 %.2f s", tempo)
        }
        return result.ok ? "质量摘要与指标已就绪" : "结果含警告"
    }

    private func analyzeLatest(force: Bool) {
        guard let url = receiver.latestCaptureURL else { return }
        if !force, analysis.lastAttemptedURL == url {
            return
        }
        Task { await analysis.analyze(captureFile: url) }
    }
}

#if DEBUG
#Preview {
    NavigationStack {
        SwingDashboardView()
    }
}
#endif
