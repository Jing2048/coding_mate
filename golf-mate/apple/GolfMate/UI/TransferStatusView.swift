import SwiftUI

struct TransferStatusView: View {
    @StateObject private var receiver = PhoneCaptureReceiver.shared

    var body: some View {
        NavigationStack {
            VStack(spacing: 18) {
                Image(systemName: "applewatch.radiowaves.left.and.right")
                    .font(.system(size: 54, weight: .light))
                    .foregroundStyle(.cyan)
                    .symbolEffect(.pulse, isActive: receiver.latestCaptureURL == nil)

                Text(receiver.latestCaptureURL == nil ? "等待 Watch" : "采集已到达")
                    .font(.title2.bold())

                Text(detail)
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)

                if let url = receiver.latestCaptureURL {
                    ShareLink(item: url) {
                        Label("导出原始采集", systemImage: "square.and.arrow.up")
                    }
                    .buttonStyle(.borderedProminent)
                }
            }
            .padding(28)
            .navigationTitle("Golf Mate Lab")
        }
    }

    private var detail: String {
        if let error = receiver.errorMessage {
            return error
        }
        if let sessionID = receiver.latestSessionID {
            return "Session \(sessionID.prefix(8))\n800 Hz ACC · 200 Hz Motion"
        }
        return "Watch 完成挥杆后，原始双流将可靠传输到这里。"
    }
}
