#!/bin/bash
set -euo pipefail

binary="${1:?usage: verify-device-binary.sh <Mach-O binary> }"
file "$binary"
lipo -verify_arch arm64 "$binary"
otool -l "$binary" | awk '
    /cmd LC_BUILD_VERSION/ { in_build=1; next }
    in_build && /minos/ {
        print
        if ($2+0 != 15.0) exit 1
        found=1
        in_build=0
    }
    END { if (!found) exit 2 }
'
