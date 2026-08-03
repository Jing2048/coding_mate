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
    @Published private(set) var accelerometerSamples = 0
    @Published private(set) var deviceMotionSamples = 0
    @Published private(set) var lastCaptureURL: URL?
    @Published private(set) var startedAt: Date?

    let targetAccelerometerHz = 800
    let targetDeviceMotionHz = 200

    private let healthStore = HKHealthStore()
    private let sensorManager = CMBatchedSensorManager()
    private let buffer = SensorRingBuffer()
    private var workoutSession: HKWorkoutSession?
    private var workoutBuilder: HKLiveWorkoutBuilder?
    private var accelerometerTask: Task<Void, Never>?
    private var deviceMotionTask: Task<Void, Never>?
    private var sessionID = UUID()

    var highRateSupported: Bool {
        CMBatchedSensorManager.isAccelerometerSupported
            && CMBatchedSensorManager.isDeviceMotionSupported
    }

    var isRecording: Bool { state == .recording }

    func start() {
        guard state == .idle || state == .ready else { return }
        guard highRateSupported else {
            state = .unsupported
            return
        }

        state = .preparing
        sessionID = UUID()
        accelerometerSamples = 0
        deviceMotionSamples = 0
        lastCaptureURL = nil
        startedAt = Date()

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
        accelerometerTask?.cancel()
        deviceMotionTask?.cancel()
        sensorManager.stopAccelerometerUpdates()
        sensorManager.stopDeviceMotionUpdates()

        let endDate = Date()
        workoutSession?.end()
        workoutBuilder?.endCollection(withEnd: endDate) { [weak self] _, _ in
            self?.workoutBuilder?.finishWorkout { _, _ in }
        }

        Task {
            // Let the final delivered batch enter the actor before snapshotting.
            try? await Task.sleep(for: .milliseconds(100))
            let snapshot = await buffer.snapshot()
            do {
                let payload = makePayload(snapshot: snapshot, endedAt: endDate)
                lastCaptureURL = try WatchTransferService.shared.enqueue(payload)
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
        accelerometerTask = Task { [weak self] in
            guard let self else { return }
            do {
                for try await batch in sensorManager.accelerometerUpdates() {
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
                for try await batch in sensorManager.deviceMotionUpdates() {
                    if Task.isCancelled { break }
                    let samples = batch.map {
                        let q = $0.attitude.quaternion
                        return DeviceMotionSample(
                            timestamp: $0.timestamp,
                            rotationRate: Vector3(
                                x: $0.rotationRate.x,
                                y: $0.rotationRate.y,
                                z: $0.rotationRate.z
                            ),
                            gravity: Vector3(
                                x: $0.gravity.x,
                                y: $0.gravity.y,
                                z: $0.gravity.z
                            ),
                            userAcceleration: Vector3(
                                x: $0.userAcceleration.x,
                                y: $0.userAcceleration.y,
                                z: $0.userAcceleration.z
                            ),
                            attitudeWXYZ: QuaternionWXYZ(
                                w: q.w,
                                x: q.x,
                                y: q.y,
                                z: q.z
                            )
                        )
                    }
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

    private func failCapture(_ error: Error) {
        accelerometerTask?.cancel()
        deviceMotionTask?.cancel()
        sensorManager.stopAccelerometerUpdates()
        sensorManager.stopDeviceMotionUpdates()
        workoutSession?.end()
        state = .failed(error.localizedDescription)
        WKInterfaceDevice.current().play(.failure)
    }

    private func makePayload(
        snapshot: SensorRingBuffer.Snapshot,
        endedAt: Date
    ) -> WatchCapturePayload {
        let watch = WKInterfaceDevice.current()
        return WatchCapturePayload(
            schemaVersion: GolfMateCaptureContract.schemaVersion,
            sessionID: sessionID,
            startedAt: startedAt ?? endedAt,
            endedAt: endedAt,
            handedness: "right",
            wrist: "lead",
            mountExtrinsicWXYZ: [1, 0, 0, 0],
            device: CaptureDevice(
                model: watch.model,
                systemVersion: watch.systemVersion,
                accelerometerHz: Double(targetAccelerometerHz),
                deviceMotionHz: Double(targetDeviceMotionHz)
            ),
            accelerometer800Hz: snapshot.accelerometer,
            deviceMotion200Hz: snapshot.deviceMotion
        )
    }

    private func authorizeHealthKit() async throws {
        // watchOS 10+ provides a typed async HealthKit API; do not wrap the
        // completion-handler variant in withCheckedThrowingContinuation or the
        // Void generic cannot be inferred.
        let workout = HKObjectType.workoutType()
        try await healthStore.requestAuthorization(toShare: [workout], read: [])
    }
}
