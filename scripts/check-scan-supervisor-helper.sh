#!/bin/bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
test_root="${RUNNER_TEMP:-${TMPDIR:-/tmp}}/openhc-scan-helper-package"
project="$repo_root/theos/scan-supervisor"
mkdir -p "$test_root"

: "${THEOS:?Set THEOS to a checked-out Theos tree}"
make -C "$project" package FINALPACKAGE=1 THEOS="$THEOS" \
  TARGET_CODESIGN=ldid TARGET_CODESIGN_FLAGS=-S
package="$(find "$project/packages" -name '*.deb' -print -quit)"
test -n "$package"
dpkg-deb -f "$package" Package Architecture | tee "$test_root/control.txt"
dpkg-deb -x "$package" "$test_root/root"
helper="$test_root/root/var/jb/usr/libexec/openhc-scan-ping-helper"
plist="$test_root/root/var/jb/Library/LaunchDaemons/com.gcbond.openhc-scan-ping-helper.plist"
runtime_dir="$test_root/root/var/jb/var/run/openhc"
test -x "$helper"
test -f "$plist"
test -f "$runtime_dir/README.txt"
grep -q 'iphoneos-arm64' "$test_root/control.txt"
grep -q '/var/jb/usr/libexec/openhc-scan-ping-helper' "$plist"
grep -q 'KeepAlive' "$plist"
file "$helper"
lipo "$helper" -verify_arch arm64
plutil -lint "$plist"
otool -L "$helper"
ldid -h "$helper" 2>&1 | grep -q CodeDirectory
python3 "$repo_root/scripts/test-scan-supervisor-integration.py" | tee "$test_root/integration.log"
mkdir -p "$repo_root/artifacts/scan-supervisor"
cp "$package" "$repo_root/artifacts/scan-supervisor/"
cp "$test_root/integration.log" "$repo_root/artifacts/scan-supervisor/"
echo SCAN_SUPERVISOR_HELPER_ROOTLESS_PACKAGE_OK
