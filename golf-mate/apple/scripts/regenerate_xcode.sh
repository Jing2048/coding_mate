#!/usr/bin/env bash
# Regenerate GolfAiJing.xcodeproj and remove stale GolfMate project leftovers.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "==> Removing stale Xcode projects / generated plists"
rm -rf GolfMate.xcodeproj GolfAiJing.xcodeproj
rm -f Config/GolfMate-Info.plist Config/GolfMateWatch-Info.plist

if ! command -v xcodegen >/dev/null 2>&1; then
  echo "error: xcodegen not found. Install with: brew install xcodegen" >&2
  exit 1
fi

echo "==> xcodegen generate"
xcodegen generate

echo "==> Done. Open only:"
echo "    open \"$ROOT/GolfAiJing.xcodeproj\""
echo ""
echo "Bundle IDs (must match):"
echo "  iPhone : com.jing.golfai.GolfAiJing"
echo "  Watch  : com.jing.golfai.GolfAiJing.watchkitapp"
echo "  WKCompanionAppBundleIdentifier = com.jing.golfai.GolfAiJing"
echo ""
echo "If Xcode still shows com.golfmate.lab.GolfMate:"
echo "  1) Quit Xcode"
echo "  2) rm -rf ~/Library/Developer/Xcode/DerivedData/*Golf*"
echo "  3) open GolfAiJing.xcodeproj (never GolfMate.xcodeproj)"
