import SwiftUI

struct MainTabView: View {
    var body: some View {
        TabView {
            NavigationStack {
                SwingDashboardView()
            }
            .tabItem {
                Label("挥杆", systemImage: "figure.golf")
            }

            NavigationStack {
                LabSettingsView()
            }
            .tabItem {
                Label("设置", systemImage: "gearshape")
            }
        }
    }
}

#if DEBUG
#Preview {
    MainTabView()
}
#endif
