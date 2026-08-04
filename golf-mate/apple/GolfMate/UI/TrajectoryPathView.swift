import SwiftUI

struct TrajectoryPathView: View {
    let points: [TrajectoryPoint]
    let title: String
    let confidence: Float
    let provisional: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text(title)
                    .font(.caption.weight(.bold))
                    .tracking(1)
                Spacer()
                Text(provisional ? "PROVISIONAL" : "FINAL")
                    .font(.caption2.weight(.bold))
                    .foregroundStyle(provisional ? .orange : .mint)
                Text("\(Int(confidence * 100))%")
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(.secondary)
            }
            Canvas { context, size in
                let rendered = project(points, size: size)
                guard let first = rendered.first else { return }
                var path = Path()
                path.move(to: first)
                for point in rendered.dropFirst() {
                    path.addLine(to: point)
                }
                context.stroke(
                    path,
                    with: .linearGradient(
                        Gradient(colors: [.mint, .cyan, .white]),
                        startPoint: .zero,
                        endPoint: CGPoint(x: size.width, y: size.height)
                    ),
                    style: StrokeStyle(lineWidth: 5, lineCap: .round, lineJoin: .round)
                )
            }
            .frame(height: 180)
            .background(Color.black.opacity(0.84), in: RoundedRectangle(cornerRadius: 16))
        }
        .padding(14)
        .background(Color.primary.opacity(0.04), in: RoundedRectangle(cornerRadius: 18))
        .accessibilityElement(children: .combine)
        .accessibilityLabel(
            "\(provisional ? "Provisional" : "Final") wrist trajectory, confidence \(Int(confidence * 100)) percent"
        )
    }

    private func project(_ points: [TrajectoryPoint], size: CGSize) -> [CGPoint] {
        guard points.count >= 2 else { return [] }
        // PCA would be overkill for the preview UI. x/z matches the Watch
        // projection and preserves preview→final visual continuity.
        let xs = points.map(\.x)
        let zs = points.map(\.z)
        guard
            let minX = xs.min(),
            let maxX = xs.max(),
            let minZ = zs.min(),
            let maxZ = zs.max()
        else { return [] }
        let spanX = max(maxX - minX, 0.05)
        let spanZ = max(maxZ - minZ, 0.05)
        let inset: CGFloat = 18
        return points.map {
            CGPoint(
                x: inset + CGFloat(($0.x - minX) / spanX) * (size.width - 2 * inset),
                y: size.height - inset
                    - CGFloat(($0.z - minZ) / spanZ) * (size.height - 2 * inset)
            )
        }
    }
}
