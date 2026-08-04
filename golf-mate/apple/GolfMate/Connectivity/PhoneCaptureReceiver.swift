import Combine
import Foundation
import WatchConnectivity

final class PhoneCaptureReceiver: NSObject, ObservableObject, WCSessionDelegate {
    static let shared = PhoneCaptureReceiver()

    @Published private(set) var latestCaptureURL: URL?
    @Published private(set) var latestSessionID: String?
    @Published private(set) var latestCaptureMode: String?
    @Published private(set) var latestAccelerometerHz: Double?
    @Published private(set) var latestDeviceMotionHz: Double?
    @Published private(set) var latestPreview: EdgeTrajectoryPreview?
    @Published private(set) var latestPreviewSessionID: String?
    @Published private(set) var errorMessage: String?

    private override init() {
        super.init()
        guard WCSession.isSupported() else { return }
        WCSession.default.delegate = self
        WCSession.default.activate()
    }

    func session(
        _ session: WCSession,
        activationDidCompleteWith activationState: WCSessionActivationState,
        error: Error?
    ) {
        DispatchQueue.main.async { self.errorMessage = error?.localizedDescription }
    }

    func sessionDidBecomeInactive(_ session: WCSession) {}
    func sessionDidDeactivate(_ session: WCSession) { session.activate() }

    func session(
        _ session: WCSession,
        didReceive file: WCSessionFile
    ) {
        do {
            let captures = try captureDirectory()
            let name = (file.metadata?["sessionID"] as? String) ?? UUID().uuidString
            let isPacked = file.metadata?["schemaVersion"] as? String
                == GolfMateCaptureContract.packedSchemaVersion
            let destination = captures.appendingPathComponent(
                "\(name).\(isPacked ? "gmpc" : "json")"
            )
            if FileManager.default.fileExists(atPath: destination.path) {
                try FileManager.default.removeItem(at: destination)
            }
            try FileManager.default.moveItem(at: file.fileURL, to: destination)
            let mode = file.metadata?["captureMode"] as? String
            let accelHz = Self.doubleMetadata(file.metadata?["accelerometerHz"])
            let motionHz = Self.doubleMetadata(file.metadata?["deviceMotionHz"])
            DispatchQueue.main.async {
                self.latestSessionID = name
                self.latestCaptureURL = destination
                self.latestCaptureMode = mode
                self.latestAccelerometerHz = accelHz
                self.latestDeviceMotionHz = motionHz
                self.errorMessage = nil
            }
            session.transferUserInfo([
                "kind": "capture-ack-v2",
                "sessionID": name,
            ])
        } catch {
            DispatchQueue.main.async {
                self.errorMessage = error.localizedDescription
            }
        }
    }

    func session(_ session: WCSession, didReceiveMessageData messageData: Data) {
        receivePreview(messageData)
    }

    func session(_ session: WCSession, didReceiveUserInfo userInfo: [String: Any]) {
        guard
            userInfo["kind"] as? String == "preview-v1",
            let data = userInfo["data"] as? Data
        else { return }
        receivePreview(data)
    }

    private func receivePreview(_ data: Data) {
        do {
            let packet = try PreviewPacketV1.decode(data)
            DispatchQueue.main.async {
                self.latestPreview = packet.preview
                self.latestPreviewSessionID = packet.sessionID.uuidString
                self.latestCaptureMode = packet.captureMode.rawValue
                self.errorMessage = nil
            }
        } catch {
            DispatchQueue.main.async {
                self.errorMessage = error.localizedDescription
            }
        }
    }

    private static func doubleMetadata(_ value: Any?) -> Double? {
        if let number = value as? Double { return number }
        if let number = value as? NSNumber { return number.doubleValue }
        if let text = value as? String { return Double(text) }
        return nil
    }

    private func captureDirectory() throws -> URL {
        let root = try FileManager.default.url(
            for: .documentDirectory,
            in: .userDomainMask,
            appropriateFor: nil,
            create: true
        )
        let captures = root.appendingPathComponent(
            "GolfMateCaptures",
            isDirectory: true
        )
        try FileManager.default.createDirectory(
            at: captures,
            withIntermediateDirectories: true
        )
        return captures
    }
}
