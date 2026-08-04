# Golf-ai-Jing (Apple)

Native Apple Watch capture + iPhone transfer shell for end-to-end algorithm validation.

App display / product name: **Golf-ai-Jing** (Watch + iPhone).

Bundle IDs (unique; `GolfMate` is taken on App Store Connect):

- iPhone: `com.jing.golfai.GolfAiJing`
- Watch: `com.jing.golfai.GolfAiJing.watchkitapp`

## Architecture

```text
Apple Watch
  HKWorkoutSession
  ├─ high_rate (Series 8 / Ultra+): CMBatchedSensorManager → ~800 Hz ACC + ~200 Hz Motion
  └─ compat    (Series 5+):         CMMotionManager         → ~100 Hz ACC + ~100 Hz Motion
        ↓ lossless golfmate-watch-capture-v1 JSON (+ captureMode)
  WCSession.transferFile
        ↓
iPhone Documents/GolfMateCaptures
        ↓
python scripts/analyze_watch_capture.py capture.json
        ↓ full Golf Mate pipeline
```

Dense accel (≥400 Hz) is never discarded and can drive a sub-frame impact hint.
Compat captures still run the full pipeline; Impact timing falls back to the
segmental detector (no fake 800 Hz claim).

## Generate the Xcode project

This repository uses [XcodeGen](https://github.com/yonaskolb/XcodeGen) so project files are
reproducible:

```bash
cd golf-mate/apple
brew install xcodegen
./scripts/regenerate_xcode.sh
open GolfAiJing.xcodeproj
```

### Xcode Cloud

Workflow start condition should use branch **`main`**.

| Setting | Value |
|---------|--------|
| Project | `golf-mate/apple/GolfAiJing.xcodeproj` (generated in `ci_post_clone`) |
| Scheme | `Golf-ai-Jing` |
| Post-clone | `golf-mate/apple/ci_scripts/ci_post_clone.sh` |

Xcode Cloud discovers `ci_scripts/` next to the Xcode project after clone; the script runs
`xcodegen generate` so the `.xcodeproj` does not need to be committed.

### Fix: `WKCompanionAppBundleIdentifier` mismatch

If Xcode reports:

```text
Invalid value of WKCompanionAppBundleIdentifier ... com.jing.golfai.GolfAiJing
(expected com.golfmate.lab.GolfMate)
```

the Watch Info.plist is new, but Xcode is still building the **old** host
`GolfMate.xcodeproj` (`com.golfmate.lab.GolfMate`). Fix:

```bash
# Quit Xcode first
cd golf-mate/apple
./scripts/regenerate_xcode.sh
rm -rf ~/Library/Developer/Xcode/DerivedData/*Golf*
open GolfAiJing.xcodeproj   # never GolfMate.xcodeproj
```

Confirm both targets:

| Target | Bundle ID |
|--------|-----------|
| GolfAiJing | `com.jing.golfai.GolfAiJing` |
| GolfAiJingWatch | `com.jing.golfai.GolfAiJing.watchkitapp` |
| Watch → WKCompanionAppBundleIdentifier | `com.jing.golfai.GolfAiJing` |

Set your Development Team for both targets, keep HealthKit enabled, and run on a
physical Apple Watch. Series 8 / Ultra+ uses the 800/200 high-rate path; Series 5
(and other watches with Core Motion only) automatically use ~100 Hz compat mode.
`CMBatchedSensorManager` does not provide high-rate data in the Watch simulator.

**OS note:** app targets watchOS 10. Series 5’s last supported OS is watchOS 10,
so install from an Xcode/watchOS 10 toolchain or keep the Watch on watchOS 10.

In App Store Connect, create the app as **Golf-ai-Jing** (not GolfMate).

## Analyze with the full algorithm (required)

Watch/iPhone **do not** ship a reduced Swift reimplementation. After capture arrives
on the iPhone, the app POSTs the raw JSON to the Mac lab server, which runs the
same `analyze_swing` pipeline used in pytest.

```bash
# Terminal A — full-fidelity algorithm service
cd golf-mate/algo
source .venv/bin/activate
python scripts/watch_lab_server.py --host 0.0.0.0 --port 8765

# Optional offline file path
python scripts/analyze_watch_capture.py ~/capture.json -o analysis.json
```

On the iPhone app, set the analysis URL to `http://<your-mac-lan-ip>:8765`.
Simulator can use `http://127.0.0.1:8765`.

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
