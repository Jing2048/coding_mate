import Foundation
import WatchKit

/// Practice-only, one-cue-per-swing transition feedback.
@MainActor
final class HapticPolicy {
    private var didCue = false
    private var lastCueAt: ContinuousClock.Instant?
    private(set) var enqueueLatencyMs: Float = 0

    func reset() {
        didCue = false
        enqueueLatencyMs = 0
    }

    func cueTransitionRush(detectedAt: ContinuousClock.Instant = .now) {
        guard !didCue else { return }
        if let lastCueAt, lastCueAt.duration(to: .now) < .seconds(2) {
            return
        }
        didCue = true
        lastCueAt = .now
        WKInterfaceDevice.current().play(.directionUp)
        let latency = detectedAt.duration(to: .now)
        enqueueLatencyMs = Float(
            Double(latency.components.seconds) * 1_000
                + Double(latency.components.attoseconds) / 1e15
        )
    }
}
