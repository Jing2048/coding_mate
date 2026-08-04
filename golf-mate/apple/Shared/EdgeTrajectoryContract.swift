import Foundation

enum EdgeTrajectoryContract {
    static let version = "edge-trajectory-v1"
    static let inputHz = 100
    static let pointCount = 64
}

struct TrajectoryPoint: Codable, Sendable, Equatable {
    let x: Float
    let y: Float
    let z: Float
}

struct EdgeTrajectoryPreview: Codable, Sendable {
    let version: String
    let points: [TrajectoryPoint]
    let confidence: Float
    let quality: Float
    let transitionRush: Float
    let inferenceP95Ms: Float
    let source: String

    static let empty = EdgeTrajectoryPreview(
        version: EdgeTrajectoryContract.version,
        points: [],
        confidence: 0,
        quality: 0,
        transitionRush: 0,
        inferenceP95Ms: 0,
        source: "none"
    )
}
