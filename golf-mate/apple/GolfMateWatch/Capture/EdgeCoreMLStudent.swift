import CoreML
import Foundation

struct EdgeIMUSample {
    let timestamp: TimeInterval
    let gyro: SIMD3<Double>
    /// Specific force in m/s², matching the Python edge contract.
    let accel: SIMD3<Double>
}

struct EdgeStudentPrediction {
    let points: [TrajectoryPoint]
    let confidence: Float
    let transitionRush: Float
}

/// Dynamic loader keeps the runtime honest: a missing or incompatible model
/// deterministically falls back to the causal kinematic preview.
final class EdgeCoreMLStudent {
    private static let featureCount = 29
    private static let outputCount = 198
    private let model: MLModel?

    init(bundle: Bundle = .main) {
        guard
            let url = bundle.url(
                forResource: "edge_trajectory_v1",
                withExtension: "mlmodelc"
            )
        else {
            model = nil
            return
        }
        let configuration = MLModelConfiguration()
        configuration.computeUnits = .all
        model = try? MLModel(contentsOf: url, configuration: configuration)
    }

    func predict(samples: [EdgeIMUSample]) -> EdgeStudentPrediction? {
        guard let model, samples.count >= 16 else { return nil }
        do {
            let features = extractFeatures(samples)
            let input = try MLMultiArray(
                shape: [1, NSNumber(value: Self.featureCount)],
                dataType: .float32
            )
            for (index, value) in features.enumerated() {
                input[index] = NSNumber(value: Float(value))
            }
            let provider = try MLDictionaryFeatureProvider(
                dictionary: ["features": MLFeatureValue(multiArray: input)]
            )
            let result = try model.prediction(from: provider)
            guard
                let output = result.featureValue(for: "edge_outputs")?.multiArrayValue,
                output.count == Self.outputCount
            else { return nil }
            let values = (0 ..< output.count).map {
                Float(truncating: output[$0])
            }
            let points = stride(from: 4, to: 4 + 64 * 3, by: 3).map { index in
                TrajectoryPoint(
                    x: values[index],
                    y: values[index + 1],
                    z: values[index + 2]
                )
            }
            guard points.allSatisfy({
                $0.x.isFinite && $0.y.isFinite && $0.z.isFinite
            }) else { return nil }
            return EdgeStudentPrediction(
                points: points,
                confidence: min(1, max(0, values[196])),
                transitionRush: min(1, max(0, values[197]))
            )
        } catch {
            return nil
        }
    }

    private func extractFeatures(_ allSamples: [EdgeIMUSample]) -> [Double] {
        let samples = Array(allSamples.prefix(512))
        let gyro = samples.map(\.gyro)
        let accel = samples.map(\.accel)
        let gmag = gyro.map(norm)
        let amag = accel.map(norm)
        let n = samples.count
        let duration = max(0, samples.last!.timestamp - samples.first!.timestamp)
        let peakG = Double(gmag.indices.max(by: { gmag[$0] < gmag[$1] }) ?? 0)
            / Double(max(n - 1, 1))
        let peakA = Double(amag.indices.max(by: { amag[$0] < amag[$1] }) ?? 0)
            / Double(max(n - 1, 1))
        let gEnergy = quadrantEnergy(gmag)
        let aEnergy = quadrantEnergy(amag)
        let half = max(n / 2, 1)
        let early = mean(gmag[..<half].map { $0 * $0 })
        let late = mean(gmag[half...].map { $0 * $0 })
        let energyDenominator = early + late + 1e-12
        let jerk = mean(zip(gmag.dropFirst(), gmag).map { abs($0 - $1) })
        let stillness = Double(gmag.filter { $0 < 0.8 }.count) / Double(n)

        return [
            duration,
            mean(gmag), standardDeviation(gmag), gmag.max() ?? 0,
            mean(amag), standardDeviation(amag), amag.max() ?? 0,
            peakG, peakA,
            gEnergy[0], gEnergy[1], gEnergy[2], gEnergy[3],
            aEnergy[0], aEnergy[1], aEnergy[2], aEnergy[3],
            rms(gyro.map(\.x)), rms(gyro.map(\.y)), rms(gyro.map(\.z)),
            rms(accel.map(\.x)), rms(accel.map(\.y)), rms(accel.map(\.z)),
            correlation(gmag, amag),
            early / energyDenominator,
            late / energyDenominator,
            jerk,
            stillness,
            Double(n) / 512,
        ]
    }

    private func norm(_ value: SIMD3<Double>) -> Double {
        sqrt(value.x * value.x + value.y * value.y + value.z * value.z)
    }

    private func mean(_ values: [Double]) -> Double {
        guard !values.isEmpty else { return 0 }
        return values.reduce(0, +) / Double(values.count)
    }

    private func standardDeviation(_ values: [Double]) -> Double {
        let average = mean(values)
        return sqrt(mean(values.map { ($0 - average) * ($0 - average) }))
    }

    private func rms(_ values: [Double]) -> Double {
        sqrt(mean(values.map { $0 * $0 }))
    }

    private func quadrantEnergy(_ values: [Double]) -> [Double] {
        (0 ..< 4).map { quadrant in
            let lo = values.count * quadrant / 4
            let hi = values.count * (quadrant + 1) / 4
            guard hi > lo else { return 0 }
            return mean(values[lo ..< hi].map { $0 * $0 })
        }
    }

    private func correlation(_ lhs: [Double], _ rhs: [Double]) -> Double {
        guard lhs.count == rhs.count, lhs.count > 3 else { return 0 }
        let lMean = mean(lhs)
        let rMean = mean(rhs)
        let numerator = zip(lhs, rhs).reduce(0) {
            $0 + ($1.0 - lMean) * ($1.1 - rMean)
        }
        let lNorm = sqrt(lhs.reduce(0) { $0 + pow($1 - lMean, 2) })
        let rNorm = sqrt(rhs.reduce(0) { $0 + pow($1 - rMean, 2) })
        let value = numerator / (lNorm * rNorm + 1e-12)
        return value.isFinite ? value : 0
    }
}
