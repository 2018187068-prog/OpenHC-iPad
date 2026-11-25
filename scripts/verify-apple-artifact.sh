#!/bin/bash
set -euo pipefail

framework="${1:-artifacts/iosArm64/OpenHCBridge.framework}"
binary="$framework/OpenHCBridge"
header="$framework/Headers/OpenHCBridge.h"

test -f "$binary"
test -f "$header"
file "$binary"
lipo "$binary" -verify_arch arm64
grep -q 'BridgeSelfCheck' "$header"
grep -q 'selfCheck' "$header"
nm -gU "$binary" | grep -q 'BridgeSelfCheck'
otool -l "$binary" | awk '
    /cmd LC_BUILD_VERSION/ { mode=1; next }
    mode == 1 && /minos/ { version=$2; mode=0; found=1 }
    /cmd LC_VERSION_MIN_IPHONEOS/ { mode=2; next }
    mode == 2 && /version/ { version=$2; mode=0; found=1 }
    found {
        split(version, part, ".")
        print "minimum iOS version " version
        if (part[1]+0 > 15 || (part[1]+0 == 15 && part[2]+0 > 0)) exit 1
        found=2
    }
    END { if (found != 2) exit 2 }
'
