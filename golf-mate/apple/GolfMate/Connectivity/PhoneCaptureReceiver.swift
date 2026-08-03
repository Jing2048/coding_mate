import Combine
import Foundation
import WatchConnectivity

final class PhoneCaptureReceiver: NSObject, ObservableObject, WCSessionDelegate {
    static let shared = PhoneCaptureReceiver()

    @Published private(set) var latestCaptureURL: URL?
    @Published private(set) var latestSessionID: String?
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
            let destination = captures.appendingPathComponent("\(name).json")
            if FileManager.default.fileExists(atPath: destination.path) {
                try FileManager.default.removeItem(at: destination)
            }
            try FileManager.default.moveItem(at: file.fileURL, to: destination)
            DispatchQueue.main.async {
                self.latestSessionID = name
                self.latestCaptureURL = destination
                self.errorMessage = nil
            }
        } catch {
            DispatchQueue.main.async {
                self.errorMessage = error.localizedDescription
            }
        }
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
