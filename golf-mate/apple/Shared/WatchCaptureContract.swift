import Foundation

enum GolfMateCaptureContract {
    static let schemaVersion = "golfmate-watch-capture-v1"
    static let standardGravity = 9.80665
}

/// Hardware capture path. High-rate needs Series 8 / Ultra+;
/// compat covers Series 5 (and other watches with Core Motion only).
enum CaptureMode: String, Codable, Sendable {
    case highRate = "high_rate"
    case compat = "compat"
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
    /// Measured sample rate from the capture timestamps (not a hard claim).
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
    let captureMode: CaptureMode
    let device: CaptureDevice
    /// Native accelerometer samples in g. Field name kept for schema v1;
    /// actual Hz is in ``device.accelerometerHz`` (800 high-rate / ~100 compat).
    let accelerometer800Hz: [Vector3Sample]
    /// Native Device Motion samples; rotation rate is rad/s. Actual Hz is in
    /// ``device.deviceMotionHz`` (200 high-rate / ~100 compat).
    let deviceMotion200Hz: [DeviceMotionSample]

    var duration: TimeInterval {
        max(0, endedAt.timeIntervalSince(startedAt))
    }
}
