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
    let commercialReport: CommercialReport?
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
        let peak_omega_to_impact_s: Double?
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
        let kind: String?

        var trustLevel: TrustLevel {
            TrustLevel(rawValue: kind ?? (is_proxy == true ? "proxy" : "derived"))
                ?? .proxy
        }
    }

    struct AnalysisMeta: Codable, Sendable {
        let impact_mode: String?
        let impact_method: String?
        let impact_confidence: Double?
        let impact_provenance: String?
        let fs_hz: Double?
        let truth_quality: TruthQuality?
        let feature_quality: [String: QualityLayer]?
    }

    struct TrajectoryQuality: Codable, Sendable {
        let confidence: Double?
        let validity: String?
        let reasons: [String]?
        let pointCount: Int?
        let source: String?
    }

    struct QualityLayer: Codable, Sendable {
        let validity: String?
        let confidence: Double?
        let reasons: [String]?
    }

    struct TruthQuality: Codable, Sendable {
        let overall_validity: String?
        let overall_confidence: Double?
        let impact_provenance: String?
        let reasons: [String]?
        let layers: [String: QualityLayer]?
    }

    struct CommercialMetric: Codable, Sendable, Identifiable {
        var id: String { name }
        let name: String
        let value: Double?
        let units: String
        let kind: String
        let validity: String
        let confidence: Double
        let residual: Double?
        let reasons: [String]?

        var trustLevel: TrustLevel {
            return TrustLevel(rawValue: kind) ?? .derived
        }

        var isAvailable: Bool {
            validity != "abstain" && value != nil
        }
    }

    struct CommercialReport: Codable, Sendable {
        let version: String
        let truth: [CommercialMetric]
        let inference: [CommercialMetric]
        let findings: [Finding]?
        let personal_baseline: CommercialSection?
        let practice_loop: PracticeSection?
        let strategy: StrategySection?
    }

    struct CommercialSection: Codable, Sendable {
        let version: String?
        let implemented: Bool?
        let deltas: [CommercialMetric]?
        let metrics: [CommercialMetric]?
    }

    struct PracticeSection: Codable, Sendable {
        let version: String?
        let implemented: Bool?
        let focus_kpi: String?
        let in_window: Bool?
        let correction_direction: Double?
        let session_consistency: Double?
        let suggested_cue: String?
        let metrics: [CommercialMetric]?
    }

    struct StrategySection: Codable, Sendable {
        let version: String?
        let implemented: Bool?
        let tempo_under_pressure: Double?
        let dispersion: Double?
        let miss_bias: Double?
        let consistency_decay: Double?
        let bad_streak: Int?
        let metrics: [CommercialMetric]?
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

    func phaseSeconds(_ index: Int?) -> Double? {
        guard
            let index,
            let fs = sourceRatesHz?.deviceMotion,
            fs > 0
        else { return nil }
        return Double(index) / fs
    }

    var displayFindings: [Finding] {
        let source = commercialReport?.findings ?? findings ?? []
        return Array(source.filter { $0.code != "rhythm_ok" }.prefix(3))
    }
}
