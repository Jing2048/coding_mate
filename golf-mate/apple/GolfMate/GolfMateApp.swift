import SwiftUI

@main
struct GolfMateApp: App {
    init() {
        _ = PhoneCaptureReceiver.shared
    }

    var body: some Scene {
        WindowGroup {
            TransferStatusView()
        }
    }
}
