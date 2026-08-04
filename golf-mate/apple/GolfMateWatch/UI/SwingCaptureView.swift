import SwiftUI

struct SwingCaptureView: View {
    @StateObject private var capture = WorkoutCaptureManager()

    var body: some View {
        ZStack {
            background
            VStack(spacing: 0) {
                rateHeader
                ZStack {
                    SwingMotionField(active: capture.isRecording)
                    centerStatus
                }
                .frame(maxHeight: .infinity)
                action
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
        }
        .containerBackground(for: .navigation) { background }
        .toolbar(.hidden, for: .navigationBar)
        .onAppear { capture.refreshCapability() }
    }

    private var background: some View {
        LinearGradient(
            colors: backgroundColors,
            startPoint: .topLeading,
            endPoint: .bottomTrailing
        )
        .ignoresSafeArea()
    }

    private var backgroundColors: [Color] {
        switch capture.state {
        case .recording:
            [Color(red: 0.01, green: 0.10, blue: 0.13), .black]
        case .ready:
            [Color(red: 0.02, green: 0.16, blue: 0.10), .black]
        case .failed:
            [Color(red: 0.20, green: 0.04, blue: 0.04), .black]
        default:
            [Color(red: 0.04, green: 0.06, blue: 0.10), .black]
        }
    }

    private var rateHeader: some View {
        HStack(spacing: 6) {
            ratePill(value: "\(capture.displayAccelerometerHz)", label: "ACC")
            ratePill(value: "\(capture.displayDeviceMotionHz)", label: "MOTION")
            if capture.isCompatMode {
                Text("兼容")
                    .font(.system(size: 7, weight: .bold, design: .rounded))
                    .padding(.horizontal, 5)
                    .padding(.vertical, 3)
                    .background(Color.orange.opacity(0.22), in: Capsule())
                    .foregroundStyle(.orange)
            }
            Spacer(minLength: 2)
            Circle()
                .fill(capture.isRecording ? Color.mint : Color.white.opacity(0.32))
                .frame(width: 6, height: 6)
                .shadow(
                    color: capture.isRecording ? .mint : .clear,
                    radius: 5
                )
                .accessibilityLabel(
                    capture.isRecording ? "Capturing" : "Capture idle"
                )
        }
    }

    private func ratePill(value: String, label: String) -> some View {
        HStack(spacing: 2) {
            Text(value)
                .font(.system(size: 9, weight: .bold, design: .rounded))
            Text(label)
                .font(.system(size: 7, weight: .semibold, design: .rounded))
                .foregroundStyle(.secondary)
        }
        .padding(.horizontal, 6)
        .padding(.vertical, 3)
        .background(.ultraThinMaterial, in: Capsule())
    }

    private var centerStatus: some View {
        VStack(spacing: 2) {
            Text(statusEyebrow)
                .font(.system(size: 8, weight: .bold, design: .rounded))
                .tracking(1.4)
                .foregroundStyle(capture.isRecording ? .mint : .cyan)

            Text(statusTitle)
                .font(.system(size: 24, weight: .medium, design: .rounded))
                .contentTransition(.numericText())
                .minimumScaleFactor(0.7)

            if capture.isRecording {
                TimelineView(.periodic(from: .now, by: 0.1)) { _ in
                    Text(elapsedText)
                        .font(.system(size: 11, weight: .medium, design: .monospaced))
                        .foregroundStyle(.secondary)
                }
            } else {
                Text(statusDetail)
                    .font(.system(size: 9, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
                    .multilineTextAlignment(.center)
                    .frame(maxWidth: 128)
            }
        }
        .accessibilityElement(children: .combine)
    }

    @ViewBuilder
    private var action: some View {
        switch capture.state {
        case .idle:
            primaryButton("开始挥杆", systemImage: "figure.golf") {
                capture.start()
            }
        case .recording:
            primaryButton("完成", systemImage: "stop.fill", destructive: true) {
                capture.stop()
            }
        case .ready:
            primaryButton("再来一杆", systemImage: "arrow.clockwise") {
                capture.reset()
            }
        case .unsupported:
            Label("此设备无法采集运动", systemImage: "applewatch.slash")
                .font(.caption2)
                .foregroundStyle(.orange)
                .padding(.bottom, 5)
        case .failed:
            primaryButton("重试", systemImage: "arrow.clockwise") {
                capture.reset()
            }
        case .preparing, .processing:
            ProgressView()
                .controlSize(.small)
                .padding(.bottom, 8)
        }
    }

    private func primaryButton(
        _ title: String,
        systemImage: String,
        destructive: Bool = false,
        action: @escaping () -> Void
    ) -> some View {
        Button(action: action) {
            Label(title, systemImage: systemImage)
                .font(.system(size: 12, weight: .bold, design: .rounded))
                .frame(maxWidth: .infinity)
        }
        .buttonStyle(.borderedProminent)
        .tint(destructive ? .red : .cyan)
        .clipShape(Capsule())
        .padding(.bottom, 2)
    }

    private var statusEyebrow: String {
        switch capture.state {
        case .recording: capture.isCompatMode ? "COMPAT IMU" : "LIVE IMU"
        case .ready: "CAPTURE LOCKED"
        case .processing: "VERIFYING"
        case .preparing: "ARMING SENSORS"
        case .failed: "CAPTURE ERROR"
        case .unsupported: "HARDWARE"
        case .idle: capture.isCompatMode ? "COMPAT LAB" : "SWING LAB"
        }
    }

    private var statusTitle: String {
        switch capture.state {
        case .recording: "挥杆"
        case .ready: "已采集"
        case .processing: "封装中"
        case .preparing: "准备"
        case .failed: "未完成"
        case .unsupported: "不可用"
        case .idle: "就位"
        }
    }

    private var statusDetail: String {
        switch capture.state {
        case .idle:
            capture.isCompatMode
                ? "抬腕开始 · Series 5 兼容约 100 Hz"
                : "抬腕开始 · 800/200 全速双流"
        case .ready:
            "\(capture.accelerometerSamples) ACC · \(capture.deviceMotionSamples) MOTION"
        case let .failed(message): message
        case .unsupported: "Core Motion 不可用"
        default: ""
        }
    }

    private var elapsedText: String {
        let seconds = max(0, Date().timeIntervalSince(capture.startedAt ?? Date()))
        return String(format: "%04.1f s", seconds)
    }
}

#Preview("Ready") {
    SwingCaptureView()
}
