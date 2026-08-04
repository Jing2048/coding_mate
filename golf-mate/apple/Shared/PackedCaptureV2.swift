import Foundation

enum PackedCaptureV2 {
    static let magic = Data([0x47, 0x4D, 0x50, 0x43]) // GMPC
    static let version: UInt16 = 2
    static let baseHeaderSize = 136
    static let previewBlockSize = 780
    static let previewPointCount = 64
    static let previewFlag: UInt32 = 1 << 1

    enum CodecError: LocalizedError {
        case insufficientSamples
        case invalidPreview
        case invalidTimestamp
        case layout(String)

        var errorDescription: String? {
            switch self {
            case .insufficientSamples:
                "Packed capture requires both sensor streams."
            case .invalidPreview:
                "Preview must contain exactly 64 finite points."
            case .invalidTimestamp:
                "Sensor timestamps must be finite and strictly increasing."
            case let .layout(message):
                "Packed capture layout error: \(message)"
            }
        }
    }

    static func encode(_ capture: WatchCapturePayload) throws -> Data {
        guard
            capture.accelerometer800Hz.count >= 2,
            capture.deviceMotion200Hz.count >= 2
        else { throw CodecError.insufficientSamples }

        let payload = try makePayload(capture)
        let preview = try makePreviewBlock(capture.preview)
        let headerSize = baseHeaderSize + preview.count
        var header = Data(capacity: headerSize)
        header.append(magic)
        header.appendLE(version)
        header.appendLE(UInt16(headerSize))
        header.appendLE(preview.isEmpty ? UInt32(0) : previewFlag)
        header.append(capture.captureMode == .highRate ? 1 : 0)
        header.append(capture.handedness == "left" ? 1 : 0)
        header.append(capture.wrist == "trail" ? 1 : 0)
        header.append(0)
        header.appendLE(Float(capture.device.accelerometerHz))
        header.appendLE(Float(capture.device.deviceMotionHz))
        header.appendLE(UInt32(capture.accelerometer800Hz.count))
        header.appendLE(UInt32(capture.deviceMotion200Hz.count))
        header.appendUUID(capture.sessionID)
        header.appendLE(capture.startedAt.timeIntervalSince1970)
        header.appendLE(capture.endedAt.timeIntervalSince1970)
        for value in capture.mountExtrinsicWXYZ.prefix(4) {
            header.appendLE(Float(value))
        }
        for _ in capture.mountExtrinsicWXYZ.count ..< 4 {
            header.appendLE(Float(0))
        }
        header.appendUTF8(capture.device.model, fixedWidth: 32)
        header.appendUTF8(capture.device.systemVersion, fixedWidth: 16)
        header.appendLE(UInt32(payload.count))
        header.appendLE(CRC32.checksum(payload))
        guard header.count == baseHeaderSize else {
            throw CodecError.layout("base header is \(header.count), expected \(baseHeaderSize)")
        }
        header.append(preview)
        guard header.count == headerSize else {
            throw CodecError.layout("header offset mismatch")
        }
        header.append(payload)
        return header
    }

    private static func makePreviewBlock(
        _ preview: EdgeTrajectoryPreview?
    ) throws -> Data {
        guard let preview else { return Data() }
        guard preview.points.count == previewPointCount else {
            throw CodecError.invalidPreview
        }
        var data = Data(capacity: previewBlockSize)
        data.appendLE(preview.confidence)
        data.appendLE(preview.quality)
        data.appendLE(UInt16(previewPointCount))
        data.appendLE(UInt16(0))
        for point in preview.points {
            guard
                point.x.isFinite,
                point.y.isFinite,
                point.z.isFinite
            else { throw CodecError.invalidPreview }
            data.appendLE(point.x)
            data.appendLE(point.y)
            data.appendLE(point.z)
        }
        guard data.count == previewBlockSize else {
            throw CodecError.layout("preview block size mismatch")
        }
        return data
    }

    private static func makePayload(_ capture: WatchCapturePayload) throws -> Data {
        let accel = capture.accelerometer800Hz
        let motion = capture.deviceMotion200Hz
        var data = Data(capacity: 16 + 16 * accel.count + 56 * motion.count)
        data.appendLE(accel[0].timestamp)
        data.appendLE(motion[0].timestamp)
        try appendTimestampDeltas(accel.map(\.timestamp), to: &data)
        for sample in accel {
            data.appendLE(Float(sample.x))
            data.appendLE(Float(sample.y))
            data.appendLE(Float(sample.z))
        }
        try appendTimestampDeltas(motion.map(\.timestamp), to: &data)
        for sample in motion {
            data.appendVector(sample.rotationRate)
        }
        for sample in motion {
            data.appendVector(sample.gravity)
        }
        for sample in motion {
            data.appendVector(sample.userAcceleration)
        }
        for sample in motion {
            data.appendLE(Float(sample.attitudeWXYZ.w))
            data.appendLE(Float(sample.attitudeWXYZ.x))
            data.appendLE(Float(sample.attitudeWXYZ.y))
            data.appendLE(Float(sample.attitudeWXYZ.z))
        }
        return data
    }

    private static func appendTimestampDeltas(
        _ timestamps: [TimeInterval],
        to data: inout Data
    ) throws {
        data.appendLE(UInt32(0))
        for index in 1 ..< timestamps.count {
            let delta = timestamps[index] - timestamps[index - 1]
            let microseconds = delta * 1_000_000
            guard
                delta.isFinite,
                microseconds >= 1,
                microseconds <= Double(UInt32.max)
            else { throw CodecError.invalidTimestamp }
            data.appendLE(UInt32(microseconds.rounded()))
        }
    }
}

private enum CRC32 {
    static func checksum(_ data: Data) -> UInt32 {
        var crc = UInt32.max
        for byte in data {
            crc ^= UInt32(byte)
            for _ in 0 ..< 8 {
                crc = (crc >> 1) ^ (0xEDB8_8320 & (0 &- (crc & 1)))
            }
        }
        return crc ^ UInt32.max
    }
}

private extension Data {
    mutating func appendLE<T: FixedWidthInteger>(_ value: T) {
        var little = value.littleEndian
        Swift.withUnsafeBytes(of: &little) { append(contentsOf: $0) }
    }

    mutating func appendLE(_ value: Float) {
        appendLE(value.bitPattern)
    }

    mutating func appendLE(_ value: Double) {
        appendLE(value.bitPattern)
    }

    mutating func appendUUID(_ value: UUID) {
        var uuid = value.uuid
        Swift.withUnsafeBytes(of: &uuid) { append(contentsOf: $0) }
    }

    mutating func appendUTF8(_ value: String, fixedWidth: Int) {
        let bytes = Array(value.utf8.prefix(fixedWidth))
        append(contentsOf: bytes)
        if bytes.count < fixedWidth {
            append(
                contentsOf: [UInt8](
                    repeating: 0,
                    count: fixedWidth - bytes.count
                )
            )
        }
    }

    mutating func appendVector(_ value: Vector3) {
        appendLE(Float(value.x))
        appendLE(Float(value.y))
        appendLE(Float(value.z))
    }
}
