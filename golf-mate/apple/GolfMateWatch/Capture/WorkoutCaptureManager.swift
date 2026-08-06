import Combine
import CoreMotion
import Foundation
import HealthKit
import WatchKit

@MainActor
final class WorkoutCaptureManager: NSObject, ObservableObject {
    enum CaptureState: Equatable {
        case idle
        case preparing
        case recording
        case processing
        case ready
        case unsupported
        case failed(String)
    }

    @Published private(set) var state: CaptureState = .idle
    @Published private(set) var captureMode: CaptureMode = .highRate
    @Published private(set) var accelerometerSamples = 0
    @Published private(set) var deviceMotionSamples = 0
    @Published private(set) var lastCaptureURL: URL?
    @Published private(set) var startedAt: Date?
    @Published private(set) var edgePreview = EdgeTrajectoryPreview.empty
    @Published private(set) var hapticEnqueueLatencyMs: Float = 0
    /// Target / requested rates shown in the UI before a capture finishes.
    @Published private(set) var displayAccelerometerHz = 800
    @Published private(set) var displayDeviceMotionHz = 200

    private let healthStore = HKHealthStore()
    private let batchedSensors = CMBatchedSensorManager()
    private let motionManager = CMMotionManager()
    private let motionQueue: OperationQueue = {
        let queue = OperationQueue()
        queue.name = "com.jing.golfai.compat-motion"
        queue.maxConcurrentOperationCount = 1
        return queue
    }()
    private let buffer = SensorRingBuffer()
    private let edgeRuntime = EdgeTrajectoryRuntime()
    private let hapticPolicy = HapticPolicy()
    private var workoutSession: HKWorkoutSession?
    private var workoutBuilder: HKLiveWorkoutBuilder?
    private var accelerometerTask: Task<Void, Never>?
    private var deviceMotionTask: Task<Void, Never>?
    private var sessionID = UUID()
    private var livePreviewSampleCounter = 0
    /// After a high-rate start failure, stay on the 100 Hz path for this launch.
    private var preferCompatOnly = false
    /// Bumped whenever sensor streams are (re)started so teardown errors from an
    /// old high-rate task cannot fail a healthy compat fallback session.
    private var sensorEpoch = 0

    /// Series 8 / Ultra+ high-rate path.
    var highRateSupported: Bool {
        CMBatchedSensorManager.isAccelerometerSupported
            && CMBatchedSensorManager.isDeviceMotionSupported
    }

    /// Series 5 and other watches that only expose CMMotionManager.
    var compatSupported: Bool {
        motionManager.isAccelerometerAvailable && motionManager.isDeviceMotionAvailable
    }

    var canCapture: Bool { highRateSupported || compatSupported }

    var isRecording: Bool { state == .recording }

    var isCompatMode: Bool { captureMode == .compat }

    var failureMessage: String? {
        if case let .failed(message) = state { return message }
        return nil
    }

    func refreshCapability() {
        if highRateSupported, !preferCompatOnly {
            captureMode = .highRate
            displayAccelerometerHz = 800
            displayDeviceMotionHz = 200
        } else if compatSupported {
            captureMode = .compat
            displayAccelerometerHz = 100
            displayDeviceMotionHz = 100
        } else {
            captureMode = .compat
            displayAccelerometerHz = 0
            displayDeviceMotionHz = 0
        }
    }

    /// Warm HealthKit + capability checks so the first Start is less likely to
    /// race the system permission sheets.
    func preparePermissions() {
        refreshCapability()
        Task {
            try? await authorizeHealthKit()
        }
    }

    func start() {
        guard state == .idle || state == .ready else { return }
        refreshCapability()
        guard canCapture else {
            state = .unsupported
            return
        }

        teardownSession(playHaptic: false)
        state = .preparing
        sessionID = UUID()
        accelerometerSamples = 0
        deviceMotionSamples = 0
        lastCaptureURL = nil
        startedAt = Date()
        edgeRuntime.reset()
        hapticPolicy.reset()
        edgePreview = .empty
        hapticEnqueueLatencyMs = 0
        livePreviewSampleCounter = 0

        Task {
            do {
                try await authorizeHealthKit()
                try ensureWorkoutSharingAuthorized()
                await buffer.reset()
                try beginWorkout()
            } catch {
                state = .failed(Self.userFacingMessage(for: error))
            }
        }
    }

    func stop() {
        guard state == .recording else { return }
        state = .processing
        edgePreview = edgeRuntime.finalize()
        stopSensorStreams()

        let endDate = Date()
        workoutSession?.end()
        workoutBuilder?.endCollection(withEnd: endDate) { [weak self] _, _ in
            Task { @MainActor in
                self?.workoutBuilder?.finishWorkout { _, _ in }
            }
        }

        Task {
            // Let the final delivered batch enter the actor before snapshotting.
            try? await Task.sleep(for: .milliseconds(100))
            let snapshot = await buffer.snapshot()
            do {
                let payload = makePayload(snapshot: snapshot, endedAt: endDate)
                lastCaptureURL = try WatchTransferService.shared.enqueue(payload)
                displayAccelerometerHz = Int(payload.device.accelerometerHz.rounded())
                displayDeviceMotionHz = Int(payload.device.deviceMotionHz.rounded())
                state = .ready
                WKInterfaceDevice.current().play(.success)
            } catch {
                state = .failed(Self.userFacingMessage(for: error))
                WKInterfaceDevice.current().play(.failure)
            }
        }
    }

    func reset() {
        guard !isRecording else { return }
        state = .idle
        startedAt = nil
        edgePreview = .empty
        refreshCapability()
    }

    private func beginWorkout() throws {
        let configuration = HKWorkoutConfiguration()
        configuration.activityType = .golf
        configuration.locationType = .outdoor

        let workoutSession = try HKWorkoutSession(
            healthStore: healthStore,
            configuration: configuration
        )
        workoutSession.delegate = self
        let builder = workoutSession.associatedWorkoutBuilder()
        builder.dataSource = HKLiveWorkoutDataSource(
            healthStore: healthStore,
            workoutConfiguration: configuration
        )
        self.workoutSession = workoutSession
        self.workoutBuilder = builder

        let startDate = startedAt ?? Date()
        workoutSession.startActivity(with: startDate)
        builder.beginCollection(withStart: startDate) { [weak self] success, error in
            Task { @MainActor in
                guard let self else { return }
                guard success else {
                    self.state = .failed(
                        Self.userFacingMessage(
                            for: error ?? CaptureSetupError.workoutFailed
                        )
                    )
                    return
                }
                self.state = .recording
                WKInterfaceDevice.current().play(.start)
                self.startSensorStreams()
            }
        }
    }

    private func startSensorStreams() {
        sensorEpoch += 1
        let epoch = sensorEpoch
        let useHighRate = highRateSupported && !preferCompatOnly
        if useHighRate {
            captureMode = .highRate
            displayAccelerometerHz = 800
            displayDeviceMotionHz = 200
            // Fidelity rail only. Live preview is derived from batched Device
            // Motion — never start CMMotionManager alongside batched sensors.
            startHighRateStreams(epoch: epoch)
        } else {
            captureMode = .compat
            displayAccelerometerHz = 100
            displayDeviceMotionHz = 100
            startCompatStreams(epoch: epoch)
        }
    }

    private func startHighRateStreams(epoch: Int) {
        accelerometerTask = Task { [weak self] in
            guard let self else { return }
            do {
                for try await batch in batchedSensors.accelerometerUpdates() {
                    if Task.isCancelled { break }
                    let samples = batch.map {
                        Vector3Sample(
                            timestamp: $0.timestamp,
                            x: $0.acceleration.x,
                            y: $0.acceleration.y,
                            z: $0.acceleration.z
                        )
                    }
                    try await buffer.appendAccelerometer(samples)
                    let counts = await buffer.counts()
                    accelerometerSamples = counts.accelerometer
                }
            } catch is CancellationError {
                return
            } catch where Task.isCancelled {
                return
            } catch {
                handleSensorFailure(error, rail: .accelerometer, epoch: epoch)
            }
        }

        deviceMotionTask = Task { [weak self] in
            guard let self else { return }
            do {
                for try await batch in batchedSensors.deviceMotionUpdates() {
                    if Task.isCancelled { break }
                    let samples = batch.map { Self.deviceMotionSample(from: $0) }
                    try await buffer.appendDeviceMotion(samples)
                    let counts = await buffer.counts()
                    deviceMotionSamples = counts.deviceMotion
                    // ~200 Hz batches → keep every other sample for the 100 Hz
                    // causal preview / haptic rail without opening CMMotionManager.
                    for (index, motion) in batch.enumerated() where index.isMultiple(of: 2) {
                        consumeLivePreview(motion)
                    }
                }
            } catch is CancellationError {
                return
            } catch where Task.isCancelled {
                return
            } catch {
                handleSensorFailure(error, rail: .deviceMotion, epoch: epoch)
            }
        }
    }

    private func startCompatStreams(epoch: Int) {
        // Series 5 / legacy path, or high-rate fallback: request 100 Hz.
        let interval = 1.0 / 100.0
        motionManager.accelerometerUpdateInterval = interval
        motionManager.deviceMotionUpdateInterval = interval

        let sensorBuffer = buffer
        motionManager.startAccelerometerUpdates(to: motionQueue) { [weak self] data, error in
            if let error {
                Task { @MainActor in
                    self?.handleSensorFailure(error, rail: .accelerometer, epoch: epoch)
                }
                return
            }
            guard let data else { return }
            let sample = Vector3Sample(
                timestamp: data.timestamp,
                x: data.acceleration.x,
                y: data.acceleration.y,
                z: data.acceleration.z
            )
            Task {
                do {
                    try await sensorBuffer.appendAccelerometer([sample])
                    let counts = await sensorBuffer.counts()
                    if counts.accelerometer.isMultiple(of: 10) {
                        await MainActor.run {
                            self?.accelerometerSamples = counts.accelerometer
                        }
                    }
                } catch {
                    await MainActor.run {
                        self?.handleSensorFailure(error, rail: .accelerometer, epoch: epoch)
                    }
                }
            }
        }

        motionManager.startDeviceMotionUpdates(
            using: .xArbitraryZVertical,
            to: motionQueue
        ) { [weak self] data, error in
            if let error {
                Task { @MainActor in
                    self?.handleSensorFailure(error, rail: .deviceMotion, epoch: epoch)
                }
                return
            }
            guard let data else { return }
            let sample = Self.deviceMotionSample(from: data)
            Task {
                do {
                    try await sensorBuffer.appendDeviceMotion([sample])
                    let counts = await sensorBuffer.counts()
                    await MainActor.run {
                        guard let self else { return }
                        self.deviceMotionSamples = counts.deviceMotion
                        self.consumeLivePreview(data)
                    }
                } catch {
                    await MainActor.run {
                        self?.handleSensorFailure(error, rail: .deviceMotion, epoch: epoch)
                    }
                }
            }
        }
    }

    private func consumeLivePreview(_ motion: CMDeviceMotion) {
        guard state == .recording else { return }
        let update = edgeRuntime.consume(motion)
        livePreviewSampleCounter += 1
        if livePreviewSampleCounter.isMultiple(of: 5) || update.shouldCueTransitionRush {
            edgePreview = update.preview
        }
        if update.shouldCueTransitionRush {
            hapticPolicy.cueTransitionRush()
            hapticEnqueueLatencyMs = hapticPolicy.enqueueLatencyMs
        }
    }

    private enum SensorRail {
        case accelerometer
        case deviceMotion
    }

    /// High-rate start failures fall back to the 100 Hz path instead of aborting
    /// the swing. Preview/haptic issues never kill an already healthy fidelity rail.
    private func handleSensorFailure(
        _ error: Error,
        rail: SensorRail,
        epoch: Int
    ) {
        guard epoch == sensorEpoch else { return }
        if Task.isCancelled || state == .processing || state == .ready {
            return
        }
        if case .failed = state { return }

        let hasFidelity =
            accelerometerSamples >= 16 && deviceMotionSamples >= 8
        if captureMode == .highRate, hasFidelity, rail == .deviceMotion {
            // Keep lossless accel/motion already buffered; drop only live preview.
            return
        }

        if
            captureMode == .highRate,
            !preferCompatOnly,
            compatSupported,
            accelerometerSamples < 16
        {
            fallbackToCompat(reason: error)
            return
        }

        failCapture(error)
    }

    private func fallbackToCompat(reason: Error) {
        preferCompatOnly = true
        stopSensorStreams()
        captureMode = .compat
        displayAccelerometerHz = 100
        displayDeviceMotionHz = 100
        // Keep the active workout; only switch the motion source.
        // startSensorStreams bumps sensorEpoch so stale high-rate errors die.
        startSensorStreams()
        #if DEBUG
        print("High-rate capture fell back to compat: \(reason.localizedDescription)")
        #endif
    }

    private func stopSensorStreams() {
        accelerometerTask?.cancel()
        deviceMotionTask?.cancel()
        accelerometerTask = nil
        deviceMotionTask = nil
        batchedSensors.stopAccelerometerUpdates()
        batchedSensors.stopDeviceMotionUpdates()
        motionManager.stopAccelerometerUpdates()
        motionManager.stopDeviceMotionUpdates()
    }

    private func teardownSession(playHaptic: Bool) {
        stopSensorStreams()
        if let session = workoutSession {
            session.end()
        }
        workoutSession = nil
        workoutBuilder = nil
        if playHaptic {
            WKInterfaceDevice.current().play(.failure)
        }
    }

    private func failCapture(_ error: Error) {
        teardownSession(playHaptic: true)
        state = .failed(Self.userFacingMessage(for: error))
    }

    private func makePayload(
        snapshot: SensorRingBuffer.Snapshot,
        endedAt: Date
    ) -> WatchCapturePayload {
        let watch = WKInterfaceDevice.current()
        let accelHz = Self.measuredRate(
            timestamps: snapshot.accelerometer.map(\.timestamp),
            fallback: Double(displayAccelerometerHz)
        )
        let motionHz = Self.measuredRate(
            timestamps: snapshot.deviceMotion.map(\.timestamp),
            fallback: Double(displayDeviceMotionHz)
        )
        return WatchCapturePayload(
            schemaVersion: GolfMateCaptureContract.schemaVersion,
            sessionID: sessionID,
            startedAt: startedAt ?? endedAt,
            endedAt: endedAt,
            handedness: "right",
            wrist: "lead",
            mountExtrinsicWXYZ: [1, 0, 0, 0],
            captureMode: captureMode,
            device: CaptureDevice(
                model: watch.model,
                systemVersion: watch.systemVersion,
                accelerometerHz: accelHz,
                deviceMotionHz: motionHz
            ),
            preview: edgePreview.points.count == EdgeTrajectoryContract.pointCount
                ? edgePreview
                : nil,
            accelerometer800Hz: snapshot.accelerometer,
            deviceMotion200Hz: snapshot.deviceMotion
        )
    }

    nonisolated private static func deviceMotionSample(
        from motion: CMDeviceMotion
    ) -> DeviceMotionSample {
        let q = motion.attitude.quaternion
        return DeviceMotionSample(
            timestamp: motion.timestamp,
            rotationRate: Vector3(
                x: motion.rotationRate.x,
                y: motion.rotationRate.y,
                z: motion.rotationRate.z
            ),
            gravity: Vector3(
                x: motion.gravity.x,
                y: motion.gravity.y,
                z: motion.gravity.z
            ),
            userAcceleration: Vector3(
                x: motion.userAcceleration.x,
                y: motion.userAcceleration.y,
                z: motion.userAcceleration.z
            ),
            attitudeWXYZ: QuaternionWXYZ(
                w: q.w,
                x: q.x,
                y: q.y,
                z: q.z
            )
        )
    }

    private static func measuredRate(
        timestamps: [TimeInterval],
        fallback: Double
    ) -> Double {
        guard timestamps.count >= 3 else { return fallback }
        let span = timestamps.last! - timestamps.first!
        guard span > 1e-3 else { return fallback }
        return Double(timestamps.count - 1) / span
    }

    private func authorizeHealthKit() async throws {
        // watchOS 10+ provides a typed async HealthKit API; do not wrap the
        // completion-handler variant in withCheckedThrowingContinuation or the
        // Void generic cannot be inferred.
        let workout = HKObjectType.workoutType()
        try await healthStore.requestAuthorization(toShare: [workout], read: [])
    }

    private func ensureWorkoutSharingAuthorized() throws {
        let status = healthStore.authorizationStatus(for: .workoutType())
        // Only hard-fail on explicit denial. `.notDetermined` can still succeed
        // after the request sheet on some watchOS builds.
        if status == .sharingDenied {
            throw CaptureSetupError.healthKitDenied
        }
    }

    private static func userFacingMessage(for error: Error) -> String {
        if let setup = error as? CaptureSetupError {
            return setup.errorDescription ?? setup.localizedDescription
        }
        let ns = error as NSError
        if ns.domain == "CMErrorDomain" {
            switch ns.code {
            case 105, 107:
                return "无法访问运动传感器，请在系统设置中允许“运动与健身”。"
            case 109:
                return "需要先开始高尔夫体能训练会话，请重试。"
            default:
                break
            }
        }
        let text = error.localizedDescription.trimmingCharacters(in: .whitespacesAndNewlines)
        if text.isEmpty {
            return "采集未完成，请重试"
        }
        return text
    }
}

extension WorkoutCaptureManager: HKWorkoutSessionDelegate {
    nonisolated func workoutSession(
        _ workoutSession: HKWorkoutSession,
        didChangeTo toState: HKWorkoutSessionState,
        from fromState: HKWorkoutSessionState,
        date: Date
    ) {}

    nonisolated func workoutSession(
        _ workoutSession: HKWorkoutSession,
        didFailWithError error: Error
    ) {
        Task { @MainActor in
            guard self.state == .preparing || self.state == .recording else { return }
            self.failCapture(error)
        }
    }
}

private enum CaptureSetupError: LocalizedError {
    case healthKitDenied
    case workoutFailed

    var errorDescription: String? {
        switch self {
        case .healthKitDenied:
            return "请允许写入体能训练，否则无法采集挥杆。"
        case .workoutFailed:
            return "无法启动高尔夫训练会话，请重试。"
        }
    }
}
