import SwiftUI

struct SwingMotionField: View {
    let active: Bool
    let points: [TrajectoryPoint]

    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.isLuminanceReduced) private var isLuminanceReduced

    var body: some View {
        TimelineView(
            .animation(
                minimumInterval: isLuminanceReduced ? 1 : 1 / 30,
                paused: reduceMotion || !active
            )
        ) { timeline in
            Canvas { context, size in
                let rect = CGRect(
                    x: size.width * 0.08,
                    y: size.height * 0.12,
                    width: size.width * 0.84,
                    height: size.height * 0.70
                )

                let rendered = projectedPoints(in: rect)
                var orbit = Path()
                if let first = rendered.first {
                    orbit.move(to: first)
                    for point in rendered.dropFirst() {
                        orbit.addLine(to: point)
                    }
                } else {
                    orbit.addArc(
                        center: CGPoint(x: rect.midX, y: rect.midY + 5),
                        radius: rect.width * 0.43,
                        startAngle: .degrees(205),
                        endAngle: .degrees(-18),
                        clockwise: false
                    )
                }
                context.stroke(
                    orbit,
                    with: .linearGradient(
                        Gradient(colors: [
                            .mint.opacity(0.12),
                            .cyan.opacity(0.95),
                            .white.opacity(0.88),
                        ]),
                        startPoint: CGPoint(x: rect.minX, y: rect.maxY),
                        endPoint: CGPoint(x: rect.maxX, y: rect.minY)
                    ),
                    style: StrokeStyle(
                        lineWidth: active ? 4.5 : 2.5,
                        lineCap: .round
                    )
                )

                let t = active
                    ? timeline.date.timeIntervalSinceReferenceDate
                    : 0.18
                let phase = (t * 0.34).truncatingRemainder(dividingBy: 1)
                let fallbackAngle = Angle.degrees(205 + 137 * phase)
                let fallbackRadius = rect.width * 0.43
                let fallback = CGPoint(
                    x: rect.midX + cos(fallbackAngle.radians) * fallbackRadius,
                    y: rect.midY + 5 + sin(fallbackAngle.radians) * fallbackRadius
                )
                let point: CGPoint
                if rendered.isEmpty {
                    point = fallback
                } else {
                    let index = min(
                        rendered.count - 1,
                        Int(phase * Double(rendered.count))
                    )
                    point = rendered[index]
                }
                let glow = CGRect(
                    x: point.x - 8,
                    y: point.y - 8,
                    width: 16,
                    height: 16
                )
                context.fill(
                    Path(ellipseIn: glow),
                    with: .radialGradient(
                        Gradient(colors: [.white, .cyan.opacity(0)]),
                        center: point,
                        startRadius: 0,
                        endRadius: 10
                    )
                )

                var axis = Path()
                axis.move(to: CGPoint(x: rect.midX, y: rect.midY - 20))
                axis.addLine(to: point)
                context.stroke(
                    axis,
                    with: .color(.cyan.opacity(active ? 0.30 : 0.12)),
                    style: StrokeStyle(lineWidth: 1, dash: [2, 4])
                )
            }
        }
        .accessibilityHidden(true)
    }

    private func projectedPoints(in rect: CGRect) -> [CGPoint] {
        guard points.count >= 2 else { return [] }
        // Render the dominant x/z wrist plane. Normalize only for the compact
        // Watch viewport; metric coordinates remain in the transmitted packet.
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
        return points.map { point in
            CGPoint(
                x: rect.minX + CGFloat((point.x - minX) / spanX) * rect.width,
                y: rect.maxY - CGFloat((point.z - minZ) / spanZ) * rect.height
            )
        }
    }
}
