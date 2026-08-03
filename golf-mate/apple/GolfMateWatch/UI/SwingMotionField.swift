import SwiftUI

struct SwingMotionField: View {
    let active: Bool

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
                let t = active
                    ? timeline.date.timeIntervalSinceReferenceDate
                    : 0.18
                let phase = (t * 0.34).truncatingRemainder(dividingBy: 1)
                let rect = CGRect(
                    x: size.width * 0.08,
                    y: size.height * 0.12,
                    width: size.width * 0.84,
                    height: size.height * 0.70
                )

                var orbit = Path()
                orbit.addArc(
                    center: CGPoint(x: rect.midX, y: rect.midY + 5),
                    radius: rect.width * 0.43,
                    startAngle: .degrees(205),
                    endAngle: .degrees(-18),
                    clockwise: false
                )
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

                // A compact, anatomical wrist/club trace—not a claimed trajectory.
                let angle = Angle.degrees(205 + 137 * phase)
                let radius = rect.width * 0.43
                let point = CGPoint(
                    x: rect.midX + cos(angle.radians) * radius,
                    y: rect.midY + 5 + sin(angle.radians) * radius
                )
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
}
