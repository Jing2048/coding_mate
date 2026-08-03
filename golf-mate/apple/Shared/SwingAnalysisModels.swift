import Foundation

struct SwingAnalysisResult: Codable, Sendable {
    let schemaVersion: String
    let ok: Bool
    let sourceRatesHz: SourceRates?
    let highRateImpactHintS: Double?
    let phases: PhaseIndices?
    let features: FeatureBundle?
    let findings: [Finding]?
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
}
