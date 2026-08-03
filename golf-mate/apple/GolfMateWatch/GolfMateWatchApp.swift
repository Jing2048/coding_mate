import SwiftUI

@main
struct GolfMateWatchApp: App {
    init() {
        _ = WatchTransferService.shared
    }

    var body: some Scene {
        WindowGroup {
            NavigationStack {
                SwingCaptureView()
            }
        }
    }
}
