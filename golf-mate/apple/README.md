# Golf Mate Apple

Native Apple Watch capture + iPhone transfer shell for end-to-end algorithm validation.

## Architecture

```text
Apple Watch Series 8+
  HKWorkoutSession
  ├─ CMBatchedSensorManager accelerometerUpdates  → 800 Hz raw (g)
  └─ CMBatchedSensorManager deviceMotionUpdates   → 200 Hz gyro (rad/s)
        ↓ lossless golfmate-watch-capture-v1 JSON
  WCSession.transferFile
        ↓
iPhone Documents/GolfMateCaptures
        ↓
python scripts/analyze_watch_capture.py capture.json
        ↓ full Golf Mate pipeline
```

The 800 Hz stream is never discarded. Python aligns it onto the 200 Hz AHRS grid and also
uses the original stream for a sub-frame impact timestamp.

## Generate the Xcode project

This repository uses [XcodeGen](https://github.com/yonaskolb/XcodeGen) so project files are
reproducible:

```bash
cd golf-mate/apple
brew install xcodegen
xcodegen generate
open GolfMate.xcodeproj
```

Set your Development Team for both targets, keep HealthKit enabled, and run on a physical
Series 8 / Ultra or newer Watch. `CMBatchedSensorManager` does not provide high-rate data
in the Watch simulator.

## Analyze a transferred capture

```bash
cd golf-mate/algo
source .venv/bin/activate
python scripts/analyze_watch_capture.py ~/capture.json -o analysis.json
```

## Required capabilities

- Watch target: HealthKit + background delivery
- `NSMotionUsageDescription`
- Health share/update descriptions
- Active `.golf` workout before starting Core Motion streams
- Paired iPhone with WatchConnectivity

## UI

`SwingCaptureView` implements the “Precision Kinetics” direction:

- glanceable 800/200 capability badges;
- cyan/mint active state and a restrained simulated motion field;
- one dominant capture action;
- Reduce Motion and Always On-aware animation;
- no unprocessed metric is presented as measured truth.

See `docs/PRD_APPLE_WATCH.md` for research rationale and acceptance criteria.
