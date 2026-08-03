import SwiftUI

struct TransferStatusView: View {
    @StateObject private var receiver = PhoneCaptureReceiver.shared
    @StateObject private var analysis = AnalysisClient.shared

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 20) {
                    header
                    serverCard
                    captureCard
                    if let result = analysis.lastResult {
                        NavigationLink {
                            SwingAnalysisView(result: result)
                        } label: {
                            Label("查看完整算法结果", systemImage: "waveform.path.ecg")
                                .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.borderedProminent)
                        .tint(.cyan)
                    }
                    if let error = analysis.lastError {
                        Text(error)
                            .font(.footnote)
                            .foregroundStyle(.red)
                            .multilineTextAlignment(.center)
                    }
                }
                .padding(24)
            }
            .navigationTitle("Golf Mate Lab")
            .task {
                await analysis.ping()
            }
            .onChange(of: receiver.latestCaptureURL) { _, url in
                guard let url else { return }
                Task { await analysis.analyze(captureFile: url) }
            }
        }
    }

    private var header: some View {
        VStack(spacing: 10) {
            Image(systemName: "applewatch.radiowaves.left.and.right")
                .font(.system(size: 48, weight: .light))
                .foregroundStyle(.cyan)
                .symbolEffect(
                    .pulse,
                    isActive: receiver.latestCaptureURL == nil && !analysis.isAnalyzing
                )
            Text(title)
                .font(.title2.bold())
            Text(subtitle)
                .font(.callout)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }
    }

    private var serverCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("算法服务")
                    .font(.headline)
                Spacer()
                Circle()
                    .fill(analysis.serverHealthy ? Color.mint : Color.orange)
                    .frame(width: 8, height: 8)
                Text(analysis.serverHealthy ? "Full Python" : "未连接")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
            }
            TextField(
                "http://<mac-ip>:8765",
                text: $analysis.serverURLString
            )
            .textInputAutocapitalization(.never)
            .autocorrectionDisabled()
            .keyboardType(.URL)
            .padding(10)
            .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 12))

            HStack {
                Button("检测连接") {
                    analysis.persistServerURL()
                    Task { await analysis.ping() }
                }
                .buttonStyle(.bordered)
                if let url = receiver.latestCaptureURL {
                    Button(analysis.isAnalyzing ? "分析中…" : "重新分析") {
                        Task { await analysis.analyze(captureFile: url) }
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(.cyan)
                    .disabled(analysis.isAnalyzing)
                }
            }
            Text("在 Mac 上运行：python scripts/watch_lab_server.py --host 0.0.0.0")
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
        .padding(14)
        .background(Color.primary.opacity(0.04), in: RoundedRectangle(cornerRadius: 16))
    }

    private var captureCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("原始采集")
                .font(.headline)
            Text(captureDetail)
                .font(.footnote)
                .foregroundStyle(.secondary)
            if let url = receiver.latestCaptureURL {
                ShareLink(item: url) {
                    Label("导出 capture JSON", systemImage: "square.and.arrow.up")
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(14)
        .background(Color.primary.opacity(0.04), in: RoundedRectangle(cornerRadius: 16))
    }

    private var title: String {
        if analysis.isAnalyzing { return "完整算法分析中" }
        if analysis.lastResult != nil { return "分析完成" }
        if receiver.latestCaptureURL != nil { return "采集已到达" }
        return "等待 Watch"
    }

    private var subtitle: String {
        if analysis.isAnalyzing {
            return "正在用完整 Python 管道处理 800/200 Hz 双流…"
        }
        if analysis.lastResult != nil {
            return "结果来自 analyze_swing，不是 Watch 端缩水版。"
        }
        return "Watch 负责全速采集；iPhone 把原始数据交给完整算法。"
    }

    private var captureDetail: String {
        if let error = receiver.errorMessage { return error }
        if let sessionID = receiver.latestSessionID {
            return "Session \(sessionID.prefix(8)) · 800 Hz ACC · 200 Hz Motion"
        }
        return "尚未收到 Watch transferFile。"
    }
}
