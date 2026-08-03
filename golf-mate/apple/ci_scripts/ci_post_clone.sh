#!/bin/sh
# Xcode Cloud: generate GolfAiJing.xcodeproj from project.yml after clone.
set -euo pipefail

echo "ci_post_clone: installing XcodeGen if needed"
if ! command -v xcodegen >/dev/null 2>&1; then
  brew install xcodegen
fi

APPLE_DIR="${CI_PRIMARY_REPOSITORY_PATH:-$(cd "$(dirname "$0")/../.." && pwd)}/golf-mate/apple"
cd "$APPLE_DIR"

echo "ci_post_clone: generating Xcode project in $APPLE_DIR"
rm -rf GolfMate.xcodeproj GolfAiJing.xcodeproj
xcodegen generate

echo "ci_post_clone: project ready"
ls -la GolfAiJing.xcodeproj
