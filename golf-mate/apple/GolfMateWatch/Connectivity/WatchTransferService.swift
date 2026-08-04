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
        let data = try PackedCaptureV2.encode(payload)
        let folder = try pendingDirectory()
        try FileManager.default.createDirectory(
            at: folder,
            withIntermediateDirectories: true
        )
        let url = folder.appendingPathComponent("\(payload.sessionID.uuidString).gmpc")
        try data.write(to: url, options: .atomic)

        if let preview = payload.preview {
            let packet = try PreviewPacketV1(
                sessionID: payload.sessionID,
                captureMode: payload.captureMode,
                preview: preview
            ).encoded()
            if session?.isReachable == true {
                session?.sendMessageData(packet, replyHandler: nil) { [weak self] _ in
                    self?.queuePreview(packet, sessionID: payload.sessionID)
                }
            } else {
                queuePreview(packet, sessionID: payload.sessionID)
            }
        }
        transfer(url, payload: payload)
        return url
    }

    private func transfer(_ url: URL, payload: WatchCapturePayload? = nil) {
        let sessionID = payload?.sessionID.uuidString
            ?? url.deletingPathExtension().lastPathComponent
        session?.transferFile(
            url,
            metadata: [
                "schemaVersion": GolfMateCaptureContract.packedSchemaVersion,
                "sessionID": sessionID,
                "captureMode": payload?.captureMode.rawValue ?? "unknown",
                "accelerometerHz": payload?.device.accelerometerHz ?? 0,
                "deviceMotionHz": payload?.device.deviceMotionHz ?? 0,
            ]
        )
    }

    private func queuePreview(_ data: Data, sessionID: UUID) {
        session?.transferUserInfo([
            "kind": "preview-v1",
            "sessionID": sessionID.uuidString,
            "data": data,
        ])
    }

    private func pendingDirectory() throws -> URL {
        let root = try FileManager.default.url(
            for: .applicationSupportDirectory,
            in: .userDomainMask,
            appropriateFor: nil,
            create: true
        )
        return root.appendingPathComponent("PendingCaptures", isDirectory: true)
    }

    private func resendPending() {
        guard
            let folder = try? pendingDirectory(),
            let urls = try? FileManager.default.contentsOfDirectory(
                at: folder,
                includingPropertiesForKeys: nil
            )
        else { return }
        for url in urls where url.pathExtension == "gmpc" {
            transfer(url)
        }
    }

    private func acknowledge(_ sessionID: String) {
        guard let folder = try? pendingDirectory() else { return }
        let url = folder.appendingPathComponent("\(sessionID).gmpc")
        try? FileManager.default.removeItem(at: url)
    }

    func session(
        _ session: WCSession,
        activationDidCompleteWith activationState: WCSessionActivationState,
        error: Error?
    ) {
        if activationState == .activated, error == nil {
            resendPending()
        }
    }

    func session(_ session: WCSession, didReceiveUserInfo userInfo: [String: Any]) {
        guard
            userInfo["kind"] as? String == "capture-ack-v2",
            let sessionID = userInfo["sessionID"] as? String
        else { return }
        acknowledge(sessionID)
    }
}
