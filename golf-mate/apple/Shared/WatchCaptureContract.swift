import Foundation

enum GolfMateCaptureContract {
    static let schemaVersion = "golfmate-watch-capture-v1"
    static let standardGravity = 9.80665
}

struct Vector3: Codable, Sendable {
    let x: Double
    let y: Double
    let z: Double
}

struct QuaternionWXYZ: Codable, Sendable {
    let w: Double
    let x: Double
    let y: Double
    let z: Double
}

struct Vector3Sample: Codable, Sendable {
    let timestamp: TimeInterval
    let x: Double
    let y: Double
    let z: Double
}

struct DeviceMotionSample: Codable, Sendable {
    let timestamp: TimeInterval
    let rotationRate: Vector3
    let gravity: Vector3
    let userAcceleration: Vector3
    /// Core Motion attitude serialized scalar-first to match Golf Mate.
    let attitudeWXYZ: QuaternionWXYZ
}

struct CaptureDevice: Codable, Sendable {
    let model: String
    let systemVersion: String
    let accelerometerHz: Double
    let deviceMotionHz: Double
}

struct WatchCapturePayload: Codable, Sendable {
    let schemaVersion: String
    let sessionID: UUID
    let startedAt: Date
    let endedAt: Date
    let handedness: String
    let wrist: String
    let mountExtrinsicWXYZ: [Double]
    let device: CaptureDevice
    /// Native CMBatchedSensorManager samples in g; never downsampled.
    let accelerometer800Hz: [Vector3Sample]
    /// Native 200 Hz device motion; rotation rate is rad/s.
    let deviceMotion200Hz: [DeviceMotionSample]

    var duration: TimeInterval {
        max(0, endedAt.timeIntervalSince(startedAt))
    }
}
