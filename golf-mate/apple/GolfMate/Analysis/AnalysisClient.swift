import Foundation

/// Talks to the Mac-side full Python pipeline (`scripts/watch_lab_server.py`).
/// This keeps algorithm fidelity identical to `pytest` / `analyze_swing`.
@MainActor
final class AnalysisClient: ObservableObject {
    static let shared = AnalysisClient()

    @Published var serverURLString: String = UserDefaults.standard.string(
        forKey: "golfmate.analysisURL"
    ) ?? "http://127.0.0.1:8765"

    @Published private(set) var isAnalyzing = false
    @Published private(set) var lastResult: SwingAnalysisResult?
    @Published private(set) var lastError: String?
    @Published private(set) var serverHealthy = false
    @Published private(set) var isCheckingServer = false
    @Published private(set) var lastAnalyzedURL: URL?
    @Published private(set) var lastAttemptedURL: URL?

    private var analysisGeneration = 0
    private init() {}

    func persistServerURL() {
        UserDefaults.standard.set(serverURLString, forKey: "golfmate.analysisURL")
    }

    func ping() async {
        isCheckingServer = true
        defer { isCheckingServer = false }
        guard let url = URL(string: serverURLString.trimmingCharacters(in: .whitespaces))?
            .appending(path: "health")
        else {
            serverHealthy = false
            return
        }
        do {
            let (data, response) = try await URLSession.shared.data(from: url)
            guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
                serverHealthy = false
                return
            }
            let payload = try JSONDecoder().decode(HealthPayload.self, from: data)
            serverHealthy = payload.ok && payload.algorithm == "full-python-analyze_swing"
        } catch {
            serverHealthy = false
        }
    }

    func analyze(captureFile url: URL) async {
        analysisGeneration += 1
        let generation = analysisGeneration
        lastAttemptedURL = url
        isAnalyzing = true
        lastError = nil
        defer {
            if generation == analysisGeneration {
                isAnalyzing = false
            }
        }

        do {
            let data = try Data(contentsOf: url)
            guard
                let endpoint = URL(
                    string: serverURLString.trimmingCharacters(in: .whitespaces)
                )?
                .appending(path: "analyze")
            else {
                throw AnalysisError.badURL
            }

            var request = URLRequest(url: endpoint)
            request.httpMethod = "POST"
            request.setValue(
                url.pathExtension == "gmpc"
                    ? "application/x-golfmate-packed-v2"
                    : "application/json",
                forHTTPHeaderField: "Content-Type"
            )
            request.timeoutInterval = 60
            request.httpBody = data

            let (responseData, response) = try await URLSession.shared.data(for: request)
            guard let http = response as? HTTPURLResponse else {
                throw AnalysisError.badResponse
            }
            let decoded = try JSONDecoder().decode(
                SwingAnalysisResult.self,
                from: responseData
            )
            if http.statusCode >= 400 || decoded.ok == false {
                throw AnalysisError.server(decoded.error ?? "analysis failed")
            }
            guard generation == analysisGeneration else { return }
            lastResult = decoded
            lastAnalyzedURL = url
            serverHealthy = true
        } catch {
            guard generation == analysisGeneration else { return }
            lastError = error.localizedDescription
        }
    }

    func clearError() {
        lastError = nil
    }
}

private struct HealthPayload: Codable {
    let ok: Bool
    let algorithm: String?
}

private enum AnalysisError: LocalizedError {
    case badURL
    case badResponse
    case server(String)

    var errorDescription: String? {
        switch self {
        case .badURL: "分析服务地址无效。"
        case .badResponse: "分析服务没有返回有效结果。"
        case let .server(message): message
        }
    }
}
