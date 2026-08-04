import Foundation

struct PreviewPacketV1: Sendable {
    static let magic = Data([0x47, 0x4D, 0x50, 0x56]) // GMPV
    static let version: UInt16 = 1

    let sessionID: UUID
    let captureMode: CaptureMode
    let preview: EdgeTrajectoryPreview

    func encoded() throws -> Data {
        guard preview.points.count == EdgeTrajectoryContract.pointCount else {
            throw PackedCaptureV2.CodecError.invalidPreview
        }
        var data = Data(capacity: 820)
        data.append(Self.magic)
        data.appendInteger(Self.version)
        data.appendInteger(UInt16(0))
        data.appendUUIDBytes(sessionID)
        data.append(captureMode == .highRate ? 1 : 0)
        data.append(contentsOf: [0, 0, 0])
        data.appendFloat(preview.confidence)
        data.appendFloat(preview.quality)
        data.appendFloat(preview.transitionRush)
        data.appendFloat(preview.inferenceP95Ms)
        data.appendInteger(UInt16(preview.points.count))
        data.appendInteger(UInt16(0))
        for point in preview.points {
            data.appendFloat(point.x)
            data.appendFloat(point.y)
            data.appendFloat(point.z)
        }
        let checksum = previewCRC32(data)
        data.appendInteger(checksum)
        return data
    }

    static func decode(_ data: Data) throws -> PreviewPacketV1 {
        var reader = PreviewReader(data)
        guard try reader.readData(count: 4) == magic else {
            throw PreviewError.invalidMagic
        }
        guard try reader.readInteger(UInt16.self) == version else {
            throw PreviewError.invalidVersion
        }
        _ = try reader.readInteger(UInt16.self)
        let session = try reader.readUUID()
        let modeByte = try reader.readByte()
        _ = try reader.readData(count: 3)
        let confidence = try reader.readFloat()
        let quality = try reader.readFloat()
        let rush = try reader.readFloat()
        let latency = try reader.readFloat()
        let count = Int(try reader.readInteger(UInt16.self))
        _ = try reader.readInteger(UInt16.self)
        guard count == EdgeTrajectoryContract.pointCount else {
            throw PreviewError.invalidPointCount
        }
        var points: [TrajectoryPoint] = []
        points.reserveCapacity(count)
        for _ in 0 ..< count {
            points.append(
                TrajectoryPoint(
                    x: try reader.readFloat(),
                    y: try reader.readFloat(),
                    z: try reader.readFloat()
                )
            )
        }
        let bodyEnd = reader.offset
        let expectedCRC = try reader.readInteger(UInt32.self)
        guard reader.isAtEnd, previewCRC32(data.prefix(bodyEnd)) == expectedCRC else {
            throw PreviewError.checksumMismatch
        }
        return PreviewPacketV1(
            sessionID: session,
            captureMode: modeByte == 1 ? .highRate : .compat,
            preview: EdgeTrajectoryPreview(
                version: EdgeTrajectoryContract.version,
                points: points,
                confidence: confidence,
                quality: quality,
                transitionRush: rush,
                inferenceP95Ms: latency,
                source: "watch_preview_packet_v1"
            )
        )
    }
}

private enum PreviewError: LocalizedError {
    case truncated
    case invalidMagic
    case invalidVersion
    case invalidPointCount
    case checksumMismatch

    var errorDescription: String? {
        switch self {
        case .truncated: "Preview packet is truncated."
        case .invalidMagic: "Preview packet magic is invalid."
        case .invalidVersion: "Preview packet version is unsupported."
        case .invalidPointCount: "Preview packet point count is invalid."
        case .checksumMismatch: "Preview packet checksum failed."
        }
    }
}

private struct PreviewReader {
    let data: Data
    private(set) var offset = 0
    var isAtEnd: Bool { offset == data.count }

    init(_ data: Data) {
        self.data = data
    }

    mutating func readData(count: Int) throws -> Data {
        guard count >= 0, offset + count <= data.count else {
            throw PreviewError.truncated
        }
        defer { offset += count }
        return data.subdata(in: offset ..< offset + count)
    }

    mutating func readByte() throws -> UInt8 {
        guard offset < data.count else { throw PreviewError.truncated }
        defer { offset += 1 }
        return data[offset]
    }

    mutating func readInteger<T: FixedWidthInteger>(_ type: T.Type) throws -> T {
        let bytes = try readData(count: MemoryLayout<T>.size)
        return bytes.withUnsafeBytes { raw in
            raw.loadUnaligned(as: T.self).littleEndian
        }
    }

    mutating func readFloat() throws -> Float {
        Float(bitPattern: try readInteger(UInt32.self))
    }

    mutating func readUUID() throws -> UUID {
        let bytes = try readData(count: 16)
        let tuple = bytes.withUnsafeBytes { raw in
            raw.loadUnaligned(as: uuid_t.self)
        }
        return UUID(uuid: tuple)
    }
}

private func previewCRC32<S: Sequence>(_ bytes: S) -> UInt32 where S.Element == UInt8 {
    var crc = UInt32.max
    for byte in bytes {
        crc ^= UInt32(byte)
        for _ in 0 ..< 8 {
            crc = (crc >> 1) ^ (0xEDB8_8320 & (0 &- (crc & 1)))
        }
    }
    return crc ^ UInt32.max
}

private extension Data {
    mutating func appendInteger<T: FixedWidthInteger>(_ value: T) {
        var little = value.littleEndian
        Swift.withUnsafeBytes(of: &little) { append(contentsOf: $0) }
    }

    mutating func appendFloat(_ value: Float) {
        appendInteger(value.bitPattern)
    }

    mutating func appendUUIDBytes(_ value: UUID) {
        var uuid = value.uuid
        Swift.withUnsafeBytes(of: &uuid) { append(contentsOf: $0) }
    }
}
