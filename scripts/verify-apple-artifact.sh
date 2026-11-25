#!/bin/bash
set -euo pipefail

framework="${1:-artifacts/iosArm64/OpenHCBridge.framework}"
binary="$framework/OpenHCBridge"
header="$framework/Headers/OpenHCBridge.h"

test -f "$binary"
test -f "$header"
file "$binary"
lipo -verify_arch arm64 "$binary"
grep -q 'BridgeSelfCheck' "$header"
grep -q 'selfCheck' "$header"
nm -gU "$binary" | grep -q 'BridgeSelfCheck'
