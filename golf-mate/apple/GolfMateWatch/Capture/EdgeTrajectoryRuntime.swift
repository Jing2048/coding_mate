import CoreMotion
import Foundation

/// Causal, allocation-bounded preview runtime for the 100 Hz live rail.
///
/// The runtime deliberately estimates a provisional lead-wrist arc. The full
/// Python teacher remains the source of truth and replaces this preview.
@MainActor
final class EdgeTrajectoryRuntime {
    struct Update {
        let preview: EdgeTrajectoryPreview
        let shouldCueTransitionRush: Bool
    }

    private static let maxSamples = 512
    private static let leverLengthM: Float = 0.62
    private static let activeOmegaRadS: Double = 1.2
    private static let quietOmegaRadS: Double = 0.55
    private static let rushAngularAccelRadS2: Double = 95

    private let student = EdgeCoreMLStudent()
    private var points: [TrajectoryPoint] = []
    private var imuSamples: [EdgeIMUSample] = []
    private var latenciesMs: [Float] = []
    private var origin: TrajectoryPoint?
    private var startedAt: TimeInterval?
    private var lastTimestamp: TimeInterval?
    private var lastOmega = 0.0
    private var peakOmega = 0.0
    private var topDetected = false
    private var transitionRush: Float = 0
    private var cueEmitted = false
    private var observedSamples = 0

    init() {
        points.reserveCapacity(Self.maxSamples)
        imuSamples.reserveCapacity(Self.maxSamples)
        latenciesMs.reserveCapacity(Self.maxSamples)
    }

    func reset() {
        points.removeAll(keepingCapacity: true)
        imuSamples.removeAll(keepingCapacity: true)
        latenciesMs.removeAll(keepingCapacity: true)
        origin = nil
        startedAt = nil
        lastTimestamp = nil
        lastOmega = 0
        peakOmega = 0
        topDetected = false
        transitionRush = 0
        cueEmitted = false
        observedSamples = 0
    }

    func consume(_ motion: CMDeviceMotion) -> Update {
        let clockStart = ContinuousClock.now
        observedSamples += 1

        let omega = sqrt(
            motion.rotationRate.x * motion.rotationRate.x
                + motion.rotationRate.y * motion.rotationRate.y
                + motion.rotationRate.z * motion.rotationRate.z
        )
        if imuSamples.count < Self.maxSamples {
            imuSamples.append(
                EdgeIMUSample(
                    timestamp: motion.timestamp,
                    gyro: SIMD3(
                        motion.rotationRate.x,
                        motion.rotationRate.y,
                        motion.rotationRate.z
                    ),
                    accel: SIMD3(
                        (motion.gravity.x + motion.userAcceleration.x)
                            * GolfMateCaptureContract.standardGravity,
                        (motion.gravity.y + motion.userAcceleration.y)
                            * GolfMateCaptureContract.standardGravity,
                        (motion.gravity.z + motion.userAcceleration.z)
                            * GolfMateCaptureContract.standardGravity
                    )
                )
            )
        }
        if startedAt == nil, omega >= Self.activeOmegaRadS {
            startedAt = motion.timestamp
        }

        let absolute = rotatedLeverPoint(motion.attitude.quaternion)
        if origin == nil {
            origin = absolute
        }
        if startedAt != nil, points.count < Self.maxSamples, let origin {
            points.append(
                TrajectoryPoint(
                    x: absolute.x - origin.x,
                    y: absolute.y - origin.y,
                    z: absolute.z - origin.z
                )
            )
        }

        var shouldCue = false
        if let lastTimestamp {
            let dt = max(motion.timestamp - lastTimestamp, 1e-3)
            let angularAccel = (omega - lastOmega) / dt
            peakOmega = max(peakOmega, omega)

            // Top is a low-rate reversal after an established backswing peak.
            if !topDetected, peakOmega > 2.5, omega < Self.quietOmegaRadS {
                topDetected = true
            } else if topDetected, angularAccel > Self.rushAngularAccelRadS2 {
                transitionRush = Float(
                    min(1, angularAccel / (Self.rushAngularAccelRadS2 * 1.8))
                )
                if transitionRush >= 0.72, !cueEmitted {
                    cueEmitted = true
                    shouldCue = true
                }
            }
        }
        lastTimestamp = motion.timestamp
        lastOmega = omega

        let latency = clockStart.duration(to: .now)
        let milliseconds = Float(
            Double(latency.components.seconds) * 1_000
                + Double(latency.components.attoseconds) / 1e15
        )
        latenciesMs.append(milliseconds)
        if latenciesMs.count > Self.maxSamples {
            latenciesMs.removeFirst()
        }

        return Update(
            preview: makePreview(final: false),
            shouldCueTransitionRush: shouldCue
        )
    }

    func finalize() -> EdgeTrajectoryPreview {
        let base = makePreview(final: true)
        let inferenceStart = ContinuousClock.now
        guard
            let prediction = student.predict(samples: imuSamples),
            prediction.points.count == base.points.count
        else { return base }
        let latency = inferenceStart.duration(to: .now)
        latenciesMs.append(
            Float(
                Double(latency.components.seconds) * 1_000
                    + Double(latency.components.attoseconds) / 1e15
            )
        )

        // Until optical-aligned device validation closes, the distilled model
        // is a bounded correction to the causal kinematic path, never the sole
        // geometric truth.
        let blend = min(0.30, 0.30 * prediction.confidence)
        let corrected = zip(base.points, prediction.points).map { causal, model in
            TrajectoryPoint(
                x: causal.x + blend * (model.x - causal.x),
                y: causal.y + blend * (model.y - causal.y),
                z: causal.z + blend * (model.z - causal.z)
            )
        }
        return EdgeTrajectoryPreview(
            version: EdgeTrajectoryContract.version,
            points: corrected,
            confidence: min(
                0.90,
                max(base.confidence * 0.90, prediction.confidence * 0.65)
            ),
            quality: min(base.quality, prediction.confidence),
            transitionRush: max(transitionRush, prediction.transitionRush),
            inferenceP95Ms: percentile95(latenciesMs),
            source: "watch_coreml_student_blend"
        )
    }

    private func makePreview(final: Bool) -> EdgeTrajectoryPreview {
        let sampled = resample(points, count: EdgeTrajectoryContract.pointCount)
        let coverage = min(1, Float(points.count) / 120)
        let motionEvidence = min(1, Float(peakOmega / 8))
        let confidence = min(0.86, 0.15 + 0.48 * coverage + 0.23 * motionEvidence)
        let p95 = percentile95(latenciesMs)
        return EdgeTrajectoryPreview(
            version: EdgeTrajectoryContract.version,
            points: sampled,
            confidence: confidence,
            quality: final ? confidence : confidence * 0.85,
            transitionRush: transitionRush,
            inferenceP95Ms: p95,
            source: "watch_causal_kinematic_student"
        )
    }

    private func rotatedLeverPoint(_ q: CMQuaternion) -> TrajectoryPoint {
        // q * v * q^-1, with v along the distal lead-arm direction.
        let vx = 0.0
        let vy = -Double(Self.leverLengthM)
        let vz = 0.0
        let tx = 2 * (q.y * vz - q.z * vy)
        let ty = 2 * (q.z * vx - q.x * vz)
        let tz = 2 * (q.x * vy - q.y * vx)
        return TrajectoryPoint(
            x: Float(vx + q.w * tx + (q.y * tz - q.z * ty)),
            y: Float(vy + q.w * ty + (q.z * tx - q.x * tz)),
            z: Float(vz + q.w * tz + (q.x * ty - q.y * tx))
        )
    }

    private func resample(
        _ input: [TrajectoryPoint],
        count: Int
    ) -> [TrajectoryPoint] {
        guard !input.isEmpty else { return [] }
        guard input.count > 1 else { return Array(repeating: input[0], count: count) }
        return (0 ..< count).map { index in
            let u = Double(index) * Double(input.count - 1) / Double(count - 1)
            let lo = Int(floor(u))
            let hi = min(lo + 1, input.count - 1)
            let a = Float(u - Double(lo))
            return TrajectoryPoint(
                x: input[lo].x + a * (input[hi].x - input[lo].x),
                y: input[lo].y + a * (input[hi].y - input[lo].y),
                z: input[lo].z + a * (input[hi].z - input[lo].z)
            )
        }
    }

    private func percentile95(_ values: [Float]) -> Float {
        guard !values.isEmpty else { return 0 }
        let sorted = values.sorted()
        let index = min(sorted.count - 1, Int(Double(sorted.count - 1) * 0.95))
        return sorted[index]
    }
}
