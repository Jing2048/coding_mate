import Foundation
import WatchConnectivity

final class WatchTransferService: NSObject, WCSessionDelegate {
    static let shared = WatchTransferService()

    private let session: WCSession? = WCSession.isSupported() ? .default : nil

    override private init() {
        super.init()
        session?.delegate = self
        session?.activate()
    }

    @discardableResult
    func enqueue(_ payload: WatchCapturePayload) throws -> URL {
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        encoder.outputFormatting = [.sortedKeys]
        let data = try encoder.encode(payload)

        let folder = FileManager.default.temporaryDirectory
            .appendingPathComponent("GolfMateCaptures", isDirectory: true)
        try FileManager.default.createDirectory(
            at: folder,
            withIntermediateDirectories: true
        )
        let url = folder.appendingPathComponent("\(payload.sessionID.uuidString).json")
        try data.write(to: url, options: .atomic)

        session?.transferFile(
            url,
            metadata: [
                "schemaVersion": payload.schemaVersion,
                "sessionID": payload.sessionID.uuidString,
                "captureMode": payload.captureMode.rawValue,
                "accelerometerHz": payload.device.accelerometerHz,
                "deviceMotionHz": payload.device.deviceMotionHz,
            ]
        )
        return url
    }

    func session(
        _ session: WCSession,
        activationDidCompleteWith activationState: WCSessionActivationState,
        error: Error?
    ) {}
}
