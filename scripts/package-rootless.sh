#!/bin/bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root/theos"
: "${THEOS:?Set THEOS to a valid Theos checkout}"
test -f "$root/artifacts/iosArm64/OpenHCBridge.framework/OpenHCBridge"
make clean package FINALPACKAGE=1
find packages -maxdepth 1 -name '*.deb' -print
