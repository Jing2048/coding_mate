import Foundation

struct SwingAnalysisResult: Codable, Sendable {
    let schemaVersion: String
    let ok: Bool
    let captureMode: String?
    let sourceRatesHz: SourceRates?
    let highRateImpactHintS: Double?
    let phases: PhaseIndices?
    let features: FeatureBundle?
    let findings: [Finding]?
    let finalTrajectory: [[Double]]?
    let trajectoryConfidence: Double?
    let trajectoryQuality: TrajectoryQuality?
    let meta: AnalysisMeta?
    let error: String?

    struct SourceRates: Codable, Sendable {
        let accelerometer: Double
        let deviceMotion: Double
    }

    struct PhaseIndices: Codable, Sendable {
        let address: Int
        let top: Int
        let impact: Int
        let finish: Int
    }

    struct FeatureBundle: Codable, Sendable {
        let tempo_s: Double?
        let backswing_s: Double?
        let downswing_s: Double?
        let rhythm: Double?
        let peak_omega_rad_s: Double?
        let hand_speed_peak_m_s: Double?
        let plane_angle_deg: Double?
        let closure_rate_rad_s: Double?
    }

    struct Finding: Codable, Sendable, Identifiable {
        var id: String { code + message }
        let code: String
        let severity: String
        let message: String
        let is_proxy: Bool?
    }

    struct AnalysisMeta: Codable, Sendable {
        let impact_mode: String?
        let impact_method: String?
        let impact_confidence: Double?
        let fs_hz: Double?
    }

    struct TrajectoryQuality: Codable, Sendable {
        let confidence: Double?
        let validity: String?
        let reasons: [String]?
        let pointCount: Int?
        let source: String?
    }

    var finalTrajectoryPoints: [TrajectoryPoint] {
        (finalTrajectory ?? []).compactMap { values in
            guard values.count == 3 else { return nil }
            return TrajectoryPoint(
                x: Float(values[0]),
                y: Float(values[1]),
                z: Float(values[2])
            )
        }
    }
}
