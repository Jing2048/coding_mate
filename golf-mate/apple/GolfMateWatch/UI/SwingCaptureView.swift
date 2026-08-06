import SwiftUI

struct SwingCaptureView: View {
    @StateObject private var capture = WorkoutCaptureManager()

    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.isLuminanceReduced) private var isLuminanceReduced

    var body: some View {
        VStack(spacing: 6) {
            rateModeBadge
            ZStack {
                SwingMotionField(
                    active: capture.isRecording,
                    points: capture.edgePreview.points
                )
                statusBlock
            }
            .frame(maxHeight: .infinity)
            actionBlock
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
        .containerBackground(for: .navigation) {
            Color.clear
        }
        .toolbar(.hidden, for: .navigationBar)
        .onAppear { capture.preparePermissions() }
    }

    // MARK: - Rate trust signal (icon + text, not color alone)

    private var rateModeBadge: some View {
        Label(rateModeTitle, systemImage: rateModeIcon)
            .font(.caption2.weight(.semibold))
            .foregroundStyle(
                isLuminanceReduced
                    ? Color.secondary
                    : (capture.isCompatMode ? GolfTheme.warning : GolfTheme.live)
            )
            .symbolRenderingMode(.hierarchical)
            .lineLimit(1)
            .minimumScaleFactor(0.85)
            .frame(maxWidth: .infinity, alignment: .leading)
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(rateModeAccessibilityLabel)
    }

    private var rateModeTitle: String {
        if capture.isCompatMode {
            return "兼容 \(capture.displayAccelerometerHz)Hz"
        }
        return "高速 \(capture.displayAccelerometerHz)/\(capture.displayDeviceMotionHz)"
    }

    private var rateModeIcon: String {
        capture.isCompatMode ? "speedometer" : "bolt.horizontal.fill"
    }

    private var rateModeAccessibilityLabel: String {
        if capture.isCompatMode {
            return "兼容采集模式，约 \(capture.displayAccelerometerHz) 赫兹"
        }
        return "高速采集模式，加速度 \(capture.displayAccelerometerHz) 赫兹，姿态 \(capture.displayDeviceMotionHz) 赫兹"
    }

    // MARK: - Status

    private var statusBlock: some View {
        VStack(spacing: 4) {
            Text(statusTitle)
                .font(.title3.weight(.semibold))
                .foregroundStyle(statusForeground)
                .contentTransition(reduceMotion ? .identity : .opacity)
                .lineLimit(1)
                .minimumScaleFactor(0.75)

            if capture.isRecording {
                recordingElapsed
                    .privacySensitive()
            } else {
                ViewThatFits(in: .vertical) {
                    statusDetailStack
                    Text(statusPrimaryDetail)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                        .lineLimit(2)
                }
            }
        }
        .padding(.horizontal, 8)
        .accessibilityElement(children: .combine)
        .accessibilityLabel(statusAccessibilityLabel)
        .accessibilityHint(statusAccessibilityHint)
    }

    @ViewBuilder
    private var statusDetailStack: some View {
        VStack(spacing: 3) {
            Text(statusPrimaryDetail)
                .font(.caption)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .lineLimit(2)
            if let secondary = statusSecondaryDetail {
                Text(secondary)
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
                    .multilineTextAlignment(.center)
                    .lineLimit(2)
            }
            if
                case .ready = capture.state,
                !capture.edgePreview.points.isEmpty,
                !isLuminanceReduced
            {
                TrustBadge(level: .provisional, compact: true)
            }
        }
        .frame(maxWidth: 140)
    }

    @ViewBuilder
    private var recordingElapsed: some View {
        let interval = isLuminanceReduced ? 1.0 : 0.2
        TimelineView(.periodic(from: .now, by: interval)) { context in
            Text(elapsedText(at: context.date))
                .font(.title2.monospacedDigit())
                .fontWeight(.medium)
                .foregroundStyle(.primary)
                .contentTransition(reduceMotion ? .identity : .numericText())
                .accessibilityLabel("已采集 \(elapsedAccessibility(at: context.date))")
        }
    }

    // MARK: - Action (one dominant control)

    @ViewBuilder
    private var actionBlock: some View {
        switch capture.state {
        case .idle:
            primaryButton(
                title: "开始采集",
                systemImage: "record.circle",
                hint: "开始记录腕部挥杆运动"
            ) {
                capture.start()
            }
        case .recording:
            primaryButton(
                title: "完成",
                systemImage: "stop.circle.fill",
                hint: "结束采集并保存到 iPhone",
                destructive: true
            ) {
                capture.stop()
            }
        case .ready:
            primaryButton(
                title: "再来一杆",
                systemImage: "arrow.clockwise",
                hint: "清空本次结果，准备下一次采集"
            ) {
                capture.reset()
            }
        case .failed:
            primaryButton(
                title: "重试",
                systemImage: "arrow.clockwise",
                hint: "返回就位并重新开始"
            ) {
                capture.reset()
            }
        case .unsupported:
            Label("此设备无法采集", systemImage: "exclamationmark.triangle")
                .font(.caption)
                .foregroundStyle(GolfTheme.warning)
                .symbolRenderingMode(.hierarchical)
                .padding(.bottom, 4)
                .accessibilityLabel("此设备无法采集运动数据")
        case .preparing, .processing:
            ProgressView()
                .controlSize(.small)
                .padding(.bottom, 6)
                .accessibilityLabel(
                    capture.state == .preparing ? "正在准备采集" : "正在保存"
                )
        }
    }

    private func primaryButton(
        title: String,
        systemImage: String,
        hint: String,
        destructive: Bool = false,
        action: @escaping () -> Void
    ) -> some View {
        Button(action: action) {
            Label(title, systemImage: systemImage)
                .font(.headline)
                .frame(maxWidth: .infinity)
                .lineLimit(1)
                .minimumScaleFactor(0.85)
        }
        .buttonStyle(.borderedProminent)
        .tint(destructive ? GolfTheme.destructive : GolfTheme.live)
        .clipShape(
            RoundedRectangle(
                cornerRadius: GolfTheme.compactCornerRadius,
                style: .continuous
            )
        )
        .accessibilityLabel(title)
        .accessibilityHint(hint)
        .padding(.bottom, 2)
    }

    // MARK: - Copy

    private var statusTitle: String {
        switch capture.state {
        case .idle: "就位"
        case .preparing: "准备采集"
        case .recording: "采集中"
        case .processing: "正在保存"
        case .ready: "已保存"
        case .failed: "出错"
        case .unsupported: "不可用"
        }
    }

    private var statusForeground: Color {
        switch capture.state {
        case .recording: GolfTheme.live
        case .ready: GolfTheme.verified
        case .failed: GolfTheme.destructive
        case .unsupported: GolfTheme.warning
        default: .primary
        }
    }

    private var statusPrimaryDetail: String {
        switch capture.state {
        case .idle:
            "抬腕，准备开始"
        case .preparing:
            "正在启动传感器"
        case .processing:
            "正在保存并发送至 iPhone"
        case .ready:
            capture.edgePreview.points.isEmpty
                ? "完整分析将在 iPhone 更新"
                : "腕部轨迹预览"
        case .failed:
            capture.failureMessage ?? "采集未完成，请重试"
        case .unsupported:
            "需要支持 Core Motion 的 Apple Watch"
        case .recording:
            ""
        }
    }

    private var statusSecondaryDetail: String? {
        switch capture.state {
        case .ready:
            if capture.edgePreview.points.isEmpty {
                return nil
            }
            return "\(wristQualityDescription)。完整分析将在 iPhone 更新"
        case .failed:
            return "点按重试。若刚拒绝权限，请到设置中开启。"
        case .idle:
            return nil
        default:
            return nil
        }
    }

    private var wristQualityDescription: String {
        let quality = capture.edgePreview.quality
        let confidence = capture.edgePreview.confidence
        let score = max(quality, confidence)
        if score >= 0.75 {
            return "腕部信号清晰"
        }
        if score >= 0.45 {
            return "腕部信号一般"
        }
        if score > 0 {
            return "腕部信号偏弱"
        }
        return "腕部轨迹待核对"
    }

    private var statusAccessibilityLabel: String {
        var parts = [statusTitle]
        if capture.isRecording {
            parts.append(elapsedAccessibility(at: Date()))
        } else {
            parts.append(statusPrimaryDetail)
            if let secondary = statusSecondaryDetail {
                parts.append(secondary)
            }
        }
        parts.append(rateModeAccessibilityLabel)
        return parts.filter { !$0.isEmpty }.joined(separator: "，")
    }

    private var statusAccessibilityHint: String {
        switch capture.state {
        case .ready:
            return "轨迹仅为腕部示意，完整分析在 iPhone"
        case .recording:
            return "采集进行中，点按下方完成结束"
        case .idle:
            return "点按下方开始采集"
        default:
            return ""
        }
    }

    private func elapsedText(at date: Date) -> String {
        let seconds = max(0, date.timeIntervalSince(capture.startedAt ?? date))
        if isLuminanceReduced {
            return String(format: "%d 秒", Int(seconds.rounded(.down)))
        }
        return String(format: "%.1f 秒", seconds)
    }

    private func elapsedAccessibility(at date: Date) -> String {
        let seconds = max(0, date.timeIntervalSince(capture.startedAt ?? date))
        if isLuminanceReduced {
            return "\(Int(seconds.rounded(.down))) 秒"
        }
        return String(format: "%.1f 秒", seconds)
    }
}

#Preview("Ready") {
    SwingCaptureView()
}
