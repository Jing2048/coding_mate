import SwiftUI

/// Low-ink wrist-plane preview. Never implies club path.
struct SwingMotionField: View {
    let active: Bool
    let points: [TrajectoryPoint]

    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.isLuminanceReduced) private var isLuminanceReduced

    private var prefersStatic: Bool {
        reduceMotion || isLuminanceReduced || !active
    }

    var body: some View {
        Group {
            if prefersStatic {
                fieldCanvas(phase: 1)
            } else {
                TimelineView(.animation(minimumInterval: 1.0 / 20.0, paused: false)) { timeline in
                    let t = timeline.date.timeIntervalSinceReferenceDate
                    let phase = (t * 0.28).truncatingRemainder(dividingBy: 1)
                    fieldCanvas(phase: phase)
                }
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(accessibilitySummary)
        .accessibilityHint("腕部运动示意，非球杆路径")
        .privacySensitive()
    }

    private func fieldCanvas(phase: Double) -> some View {
        Canvas { context, size in
            let rect = CGRect(
                x: size.width * 0.10,
                y: size.height * 0.14,
                width: size.width * 0.80,
                height: size.height * 0.68
            )
            let rendered = projectedPoints(in: rect)

            if rendered.count >= 2 {
                var stroke = Path()
                stroke.move(to: rendered[0])
                for point in rendered.dropFirst() {
                    stroke.addLine(to: point)
                }
                context.stroke(
                    stroke,
                    with: .color(GolfTheme.live.opacity(active ? 0.85 : 0.55)),
                    style: StrokeStyle(
                        lineWidth: active ? 2.5 : 2,
                        lineCap: .round,
                        lineJoin: .round
                    )
                )

                let tip: CGPoint
                if prefersStatic {
                    tip = rendered.last!
                } else {
                    let index = min(
                        rendered.count - 1,
                        max(0, Int(phase * Double(rendered.count)))
                    )
                    tip = rendered[index]
                }
                drawCurrentPoint(context: context, at: tip, emphasized: active)
            } else {
                // Quiet static wrist posture — no decorative orbit or screensaver.
                let rest = CGPoint(x: rect.midX, y: rect.midY + rect.height * 0.08)
                drawCurrentPoint(context: context, at: rest, emphasized: false)
            }
        }
    }

    private func drawCurrentPoint(
        context: GraphicsContext,
        at point: CGPoint,
        emphasized: Bool
    ) {
        let radius: CGFloat = emphasized ? 4 : 3
        let oval = CGRect(
            x: point.x - radius,
            y: point.y - radius,
            width: radius * 2,
            height: radius * 2
        )
        context.fill(
            Path(ellipseIn: oval),
            with: .color(emphasized ? GolfTheme.live : Color.primary.opacity(0.45))
        )
    }

    private var accessibilitySummary: String {
        if points.count >= 2 {
            if active {
                return "腕部轨迹进行中，已记录 \(points.count) 个采样点"
            }
            return "腕部轨迹预览，共 \(points.count) 个采样点"
        }
        if active {
            return "等待腕部运动数据"
        }
        return "腕部静止示意"
    }

    private func projectedPoints(in rect: CGRect) -> [CGPoint] {
        guard points.count >= 2 else { return [] }
        // Dominant wrist x/z plane for the compact Watch viewport only.
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
