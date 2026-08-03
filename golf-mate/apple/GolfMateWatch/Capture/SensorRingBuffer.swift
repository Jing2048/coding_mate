import Foundation

actor SensorRingBuffer {
    struct Snapshot: Sendable {
        let accelerometer: [Vector3Sample]
        let deviceMotion: [DeviceMotionSample]
    }

    // This screen captures one swing. Refuse >60 s rather than silently dropping
    // old samples—the validation contract is lossless.
    private let maxAccelerometerSamples = 800 * 60
    private let maxDeviceMotionSamples = 200 * 60
    private var accelerometer: [Vector3Sample] = []
    private var deviceMotion: [DeviceMotionSample] = []

    func reset() {
        accelerometer.removeAll(keepingCapacity: true)
        deviceMotion.removeAll(keepingCapacity: true)
        accelerometer.reserveCapacity(800 * 10)
        deviceMotion.reserveCapacity(200 * 10)
    }

    func appendAccelerometer(_ batch: [Vector3Sample]) throws {
        guard accelerometer.count + batch.count <= maxAccelerometerSamples else {
            throw BufferError.capacityExceeded
        }
        accelerometer.append(contentsOf: batch)
    }

    func appendDeviceMotion(_ batch: [DeviceMotionSample]) throws {
        guard deviceMotion.count + batch.count <= maxDeviceMotionSamples else {
            throw BufferError.capacityExceeded
        }
        deviceMotion.append(contentsOf: batch)
    }

    func counts() -> (accelerometer: Int, deviceMotion: Int) {
        (accelerometer.count, deviceMotion.count)
    }

    func snapshot() -> Snapshot {
        Snapshot(
            accelerometer: accelerometer.sorted { $0.timestamp < $1.timestamp },
            deviceMotion: deviceMotion.sorted { $0.timestamp < $1.timestamp }
        )
    }
}

private enum BufferError: LocalizedError {
    case capacityExceeded

    var errorDescription: String? {
        "Single-swing capture exceeded 60 seconds."
    }
}
