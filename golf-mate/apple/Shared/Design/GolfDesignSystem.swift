import SwiftUI

enum GolfTheme {
    static let cornerRadius: CGFloat = 16
    static let compactCornerRadius: CGFloat = 10
    static let sectionSpacing: CGFloat = 24

    static let live = Color.teal
    static let verified = Color.green
    static let warning = Color.orange
    static let destructive = Color.red
    static let inferred = Color.secondary
    static let quietSurface = Color.secondary.opacity(0.08)
}

enum TrustLevel: String, Codable, Sendable {
    case measured
    case derived
    case proxy
    case inferred
    case provisional
    case verified
    case degraded
    case abstain

    var title: String {
        switch self {
        case .measured: "实测"
        case .derived: "计算"
        case .proxy: "代理"
        case .inferred: "推断"
        case .provisional: "预览"
        case .verified: "质量正常"
        case .degraded: "质量受限"
        case .abstain: "不输出"
        }
    }

    var icon: String {
        switch self {
        case .measured, .verified: "checkmark.circle.fill"
        case .derived: "sum"
        case .proxy: "arrow.triangle.2.circlepath"
        case .inferred: "waveform.path.ecg"
        case .provisional: "clock"
        case .degraded: "exclamationmark.triangle.fill"
        case .abstain: "minus.circle"
        }
    }

    var color: Color {
        switch self {
        case .measured, .verified: GolfTheme.verified
        case .derived: .primary
        case .proxy, .degraded: GolfTheme.warning
        case .inferred: GolfTheme.inferred
        case .provisional: GolfTheme.live
        case .abstain: .secondary
        }
    }
}

struct TrustBadge: View {
    let level: TrustLevel
    var compact = false

    var body: some View {
        Label(level.title, systemImage: level.icon)
            .font(compact ? .caption2.weight(.semibold) : .caption.weight(.semibold))
            .foregroundStyle(level.color)
            .padding(.horizontal, compact ? 6 : 8)
            .padding(.vertical, compact ? 3 : 5)
            .background(level.color.opacity(0.12), in: Capsule())
            .accessibilityLabel("数据类型：\(level.title)")
    }
}

struct GolfSectionHeader: View {
    let title: String
    var subtitle: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(title)
                .font(.headline)
            if let subtitle {
                Text(subtitle)
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .combine)
    }
}

struct GolfSurface: ViewModifier {
    var padding: CGFloat = 16

    func body(content: Content) -> some View {
        content
            .padding(padding)
            .background(
                GolfTheme.quietSurface,
                in: RoundedRectangle(
                    cornerRadius: GolfTheme.cornerRadius,
                    style: .continuous
                )
            )
    }
}

extension View {
    func golfSurface(padding: CGFloat = 16) -> some View {
        modifier(GolfSurface(padding: padding))
    }
}
