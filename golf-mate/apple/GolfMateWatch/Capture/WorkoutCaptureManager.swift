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

    func refreshCapability() {
        if highRateSupported {
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

    func start() {
        guard state == .idle || state == .ready else { return }
        refreshCapability()
        guard canCapture else {
            state = .unsupported
            return
        }

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
                await buffer.reset()
                try beginWorkout()
            } catch {
                state = .failed(error.localizedDescription)
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
                state = .failed(error.localizedDescription)
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
                    self.state = .failed(error?.localizedDescription ?? "Workout failed")
                    return
                }
                self.state = .recording
                WKInterfaceDevice.current().play(.start)
                self.startSensorStreams()
            }
        }
    }

    private func startSensorStreams() {
        if highRateSupported {
            captureMode = .highRate
            displayAccelerometerHz = 800
            displayDeviceMotionHz = 200
            startLivePreviewStream()
            startHighRateStreams()
        } else {
            captureMode = .compat
            displayAccelerometerHz = 100
            displayDeviceMotionHz = 100
            startCompatStreams()
        }
    }

    private func startHighRateStreams() {
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
            } catch where Task.isCancelled {
                return
            } catch {
                failCapture(error)
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
                }
            } catch where Task.isCancelled {
                return
            } catch {
                failCapture(error)
            }
        }
    }

    private func startCompatStreams() {
        // Series 5 / legacy path: request 100 Hz. Actual delivered rate is
        // measured from timestamps and written into the capture payload.
        let interval = 1.0 / 100.0
        motionManager.accelerometerUpdateInterval = interval
        motionManager.deviceMotionUpdateInterval = interval

        let sensorBuffer = buffer
        motionManager.startAccelerometerUpdates(to: motionQueue) { [weak self] data, error in
            if let error {
                Task { @MainActor in self?.failCapture(error) }
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
                        self?.failCapture(error)
                    }
                }
            }
        }

        motionManager.startDeviceMotionUpdates(
            using: .xArbitraryZVertical,
            to: motionQueue
        ) { [weak self] data, error in
            if let error {
                Task { @MainActor in self?.failCapture(error) }
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
                        self?.failCapture(error)
                    }
                }
            }
        }
    }

    /// Series 8+ keeps the low-latency 100 Hz rail active alongside the
    /// 800/200 Hz batched fidelity rail. Failure only removes preview/haptics;
    /// it must never abort the lossless capture.
    private func startLivePreviewStream() {
        motionManager.deviceMotionUpdateInterval = 1.0 / 100.0
        motionManager.startDeviceMotionUpdates(
            using: .xArbitraryZVertical,
            to: motionQueue
        ) { [weak self] data, _ in
            guard let self, let data else { return }
            Task { @MainActor in
                self.consumeLivePreview(data)
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

    private func failCapture(_ error: Error) {
        stopSensorStreams()
        workoutSession?.end()
        state = .failed(error.localizedDescription)
        WKInterfaceDevice.current().play(.failure)
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
}
