#!/bin/bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
app="$RUNNER_TEMP/fe35-cli-smoke.app"
bundle_id="com.gcbond.openhc.fe35-cli-smoke"
framework="$repo_root/bridge/build/bin/iosSimulatorArm64/releaseFramework/OpenHCBridge.framework"
mkdir -p "$app/Documents"

python3 - "$app/Info.plist" <<'PY'
import plistlib
import sys

with open(sys.argv[1], "wb") as stream:
    plistlib.dump({
        "CFBundleExecutable": "fe35-cli-smoke",
        "CFBundleIdentifier": "com.gcbond.openhc.fe35-cli-smoke",
        "CFBundleName": "FE35 Bridge Smoke",
        "CFBundlePackageType": "APPL",
        "CFBundleVersion": "1",
        "CFBundleShortVersionString": "1",
        "LSRequiresIPhoneOS": True,
    }, stream)
PY

for qr_source in ScanQRBitmap vendor/qrcodegen/qrcodegen; do
  xcrun --sdk iphonesimulator clang -arch arm64 -mios-simulator-version-min=15.0 \
    -std=c11 -Wall -Wextra -Werror -c "$repo_root/theos/scan-ui/$qr_source.c" \
    -o "$RUNNER_TEMP/owner-$(basename "$qr_source").o"
done
xcrun --sdk iphonesimulator clang -arch arm64 -mios-simulator-version-min=15.0 \
  -fobjc-arc -DOPENHC_CLI_NO_MAIN -DOPENHC_FE35_SIMULATOR_TEST \
  -DOPENHC_TRANSPORT_TEST_TIMEOUTS -DOPENHC_SCAN_OWNER_TEST -DOPENHC_SCAN_OWNER_PROCESS_TEST \
  -F"$(dirname "$framework")" -framework OpenHCBridge -framework Foundation -framework CoreFoundation \
  -framework UIKit -framework CoreGraphics \
  "$repo_root/theos/main.m" "$repo_root/theos/fe35-bridge-smoke.m" \
  "$repo_root/theos/fe35-control-bridge.m" "$repo_root/theos/btstack-probe.c" \
  "$repo_root/scripts/fe35-cli-smoke-runner.m" \
  "$repo_root/scripts/scan-transport-sim-fixture.m" \
  "$repo_root/theos/scan-owner/ScanOwner.c" "$repo_root/theos/scan-owner/ScanOwnerPeer.c" \
  "$repo_root/theos/scan-owner/ScanOwnerRuntime.m" \
  "$repo_root/theos/scan-owner/ScanOwnerForeground.m" \
  "$repo_root/theos/scan-owner/ScanProcessLeaseAdapter.m" \
  "$repo_root/theos/scan-owner/ScanLeaseProtocol.c" \
  "$repo_root/theos/scan-owner/ScanLeaseChannel.c" \
  "$repo_root/scripts/scan-owner-sim-fixture.m" \
  "$repo_root/scripts/hicar-auth-sim-fixture.m" \
  "$repo_root/theos/scan-ui/ScanQRCode.m" \
  "$RUNNER_TEMP/owner-ScanQRBitmap.o" "$RUNNER_TEMP/owner-qrcodegen.o" \
  "$repo_root/scripts/fe35-inbound-sim-probe-stubs.c" \
  -o "$app/fe35-cli-smoke"
codesign --force --sign - "$app"

udid="$(python3 - <<'PY'
import json
import subprocess

devices = json.loads(subprocess.check_output(["xcrun", "simctl", "list", "devices", "available", "-j"]))["devices"]
for runtime in sorted(devices, reverse=True):
    for device in devices[runtime]:
        if device["name"].startswith("iPhone"):
            print(device["udid"])
            raise SystemExit(0)
raise SystemExit("No available iPhone simulator")
PY
)"
booted_by_test=0
data_dir=""
if ! xcrun simctl list devices | grep -F "$udid" | grep -F '(Booted)' >/dev/null; then
  xcrun simctl boot "$udid"
  booted_by_test=1
fi
cleanup() {
  status=$?
  trap - EXIT
  if [[ -n "$data_dir" && -d "$data_dir/Documents" ]]; then
    if ! python3 - "$data_dir/Documents" "$repo_root/artifacts/scan-owner/simulator-last-case" <<'PY'
from pathlib import Path
import shutil, sys
source, destination = map(Path, sys.argv[1:])
destination.mkdir(parents=True, exist_ok=True)
for name in ('fe35-cli-status.log', 'fe35-cli-result'):
    p = source / name
    if p.is_file(): shutil.copyfile(p, destination / name)
for pattern in ('scan-guard-*/scan-events', 'owner-guard-*/scan-events'):
    for p in source.glob(pattern):
        shutil.copyfile(p, destination / (p.parent.name + '-events.log'))
PY
    then
      if [[ "$status" == 0 ]]; then status=1; fi
    fi
  fi
  if [[ "$booted_by_test" == 1 ]]; then xcrun simctl shutdown "$udid" || true; fi
  exit "$status"
}
trap cleanup EXIT
xcrun simctl bootstatus "$udid" -b
xcrun simctl install "$udid" "$app"
xcrun simctl launch "$udid" "$bundle_id" --fe35-bridge-smoke
data_dir="$(xcrun simctl get_app_container "$udid" "$bundle_id" data)"
for _ in $(seq 1 40); do
  if [[ -f "$data_dir/Documents/fe35-cli-result" ]]; then break; fi
  sleep 0.5
done
test "$(cat "$data_dir/Documents/fe35-cli-result")" = 0
echo "FE35_PUBLIC_KOTLIN_BRIDGE_CLI_SMOKE_OK"
python3 "$repo_root/scripts/test-fe35-cli-inbound-simulator.py" \
  --udid "$udid" --bundle-id "$bundle_id" --data-dir "$data_dir"
