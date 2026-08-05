import SwiftUI

/// Compatibility wrapper — production entry is `SwingDashboardView` inside `MainTabView`.
struct TransferStatusView: View {
    var body: some View {
        SwingDashboardView()
    }
}

#if DEBUG
#Preview {
    NavigationStack {
        TransferStatusView()
    }
}
#endif
