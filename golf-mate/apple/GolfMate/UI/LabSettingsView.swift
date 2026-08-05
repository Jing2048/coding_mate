import SwiftUI

/// Lab / developer settings: server URL, health ping, CLI hint, raw capture export.
/// Kept off the main swing screen so product copy stays non-implementation.
struct LabSettingsView: View {
    @ObservedObject private var receiver = PhoneCaptureReceiver.shared
    @ObservedObject private var analysis = AnalysisClient.shared

    var body: some View {
        List {
            Section {
                VStack(alignment: .leading, spacing: 10) {
                    HStack {
                        Text("分析服务")
                            .font(.headline)
                        Spacer()
                        Image(systemName: analysis.serverHealthy
                              ? "checkmark.circle.fill"
                              : "exclamationmark.circle")
                            .foregroundStyle(
                                analysis.serverHealthy
                                    ? GolfTheme.verified
                                    : GolfTheme.warning
                            )
                            .accessibilityHidden(true)
                        Text(analysis.serverHealthy ? "已连接" : "未连接")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(.secondary)
                    }
                    .accessibilityElement(children: .combine)
                    .accessibilityLabel(
                        analysis.serverHealthy ? "分析服务已连接" : "分析服务未连接"
                    )

                    TextField(
                        "http://127.0.0.1:8765",
                        text: $analysis.serverURLString
                    )
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .keyboardType(.URL)
                    .font(.body.monospaced())
                    .accessibilityLabel("分析服务地址")

                    Button {
                        analysis.persistServerURL()
                        Task { await analysis.ping() }
                    } label: {
                        if analysis.isCheckingServer {
                            Label("检测中…", systemImage: "antenna.radiowaves.left.and.right")
                        } else {
                            Label("检测连接", systemImage: "antenna.radiowaves.left.and.right")
                        }
                    }
                    .disabled(analysis.isCheckingServer)
                }
                .padding(.vertical, 4)
            } header: {
                Text("分析连接")
            } footer: {
                Text("分析在已配置的服务上完成；连接异常不会删除上一杆有效结果。")
            }

#if DEBUG
            Section("命令行") {
                Text("在 Mac 上启动本地分析服务后，将上方地址改为该 Mac 的局域网 IP。")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                Text("watch_lab_server · 端口 8765")
                    .font(.caption.monospaced())
                    .foregroundStyle(.secondary)
                    .textSelection(.enabled)
                    .accessibilityLabel("本地分析服务，默认端口 8765")
            }
#endif

            Section("原始采集") {
                if let error = receiver.errorMessage {
                    Text(error)
                        .font(.footnote)
                        .foregroundStyle(GolfTheme.destructive)
                }
                Text(captureDetail)
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                if let url = receiver.latestCaptureURL {
                    ShareLink(item: url) {
                        Label("导出原始采集文件", systemImage: "square.and.arrow.up")
                    }
                    if !analysis.isAnalyzing {
                        Button {
                            Task { await analysis.analyze(captureFile: url) }
                        } label: {
                            Label("重新分析最近采集", systemImage: "arrow.clockwise")
                        }
                    }
                } else {
                    Text("尚未收到 Watch 采集文件。")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
            }

            Section("关于") {
                LabeledContent("应用", value: "Golf-ai-Jing")
                LabeledContent("分析边界", value: "腕部生物力学")
            }
        }
        .navigationTitle("设置")
        .task {
            await analysis.ping()
        }
    }

    private var captureDetail: String {
        if let sessionID = receiver.latestSessionID {
            let accel = Int((receiver.latestAccelerometerHz ?? 0).rounded())
            let motion = Int((receiver.latestDeviceMotionHz ?? 0).rounded())
            let mode = receiver.latestCaptureMode == "compat" ? "兼容" : "高速"
            if accel > 0 && motion > 0 {
                return "Session \(sessionID.prefix(8)) · \(mode) · \(accel) Hz ACC · \(motion) Hz Motion"
            }
            return "Session \(sessionID.prefix(8)) · 双流已到达"
        }
        return "等待 Watch 传输采集文件。"
    }
}

#if DEBUG
#Preview {
    NavigationStack {
        LabSettingsView()
    }
}
#endif
