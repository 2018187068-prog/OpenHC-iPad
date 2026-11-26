#!/bin/bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
framework="$repo_root/bridge/build/bin/iosSimulatorArm64/releaseFramework/OpenHCBridge.framework"
test_root="${RUNNER_TEMP:-${TMPDIR:-/tmp}}/openhc-scan-ui-check"
app="$test_root/OpenHCScanDemo.app"
bundle_id="com.gcbond.openhc-scan-demo"
mkdir -p "$app" "$repo_root/artifacts/scan-ui"
cp "$repo_root/theos/scan-ui/Resources/Info.plist" "$app/Info.plist"
xcrun --sdk iphonesimulator clang -arch arm64 -mios-simulator-version-min=15.0 \
  -fobjc-arc -Wall -Wextra -Werror -Wno-deprecated-declarations -Wno-sign-compare -DOPENHC_SCAN_UI_TEST \
  -F"$(dirname "$framework")" -framework OpenHCBridge -framework UIKit \
  -framework Foundation -framework CoreImage -framework CoreGraphics -framework QuartzCore \
  "$repo_root/theos/scan-ui/main.m" "$repo_root/theos/scan-ui/ScanDemo.m" \
  "$repo_root/theos/scan-ui/ScanQRCode.m" "$repo_root/scripts/scan-ui-tests.m" \
  -o "$app/OpenHCScanDemo"
codesign --force --sign - "$app"
udid="$(python3 - <<'PY'
import json, subprocess
devices = json.loads(subprocess.check_output(['xcrun', 'simctl', 'list', 'devices', 'available', '-j']))['devices']
for runtime in sorted(devices, reverse=True):
    for device in devices[runtime]:
        if device['name'].startswith('iPad'):
            print(device['udid'])
            raise SystemExit(0)
raise SystemExit('No available iPad Simulator')
PY
)"
booted_by_test=0
if ! xcrun simctl list devices | grep -F "$udid" | grep -F '(Booted)' >/dev/null; then
  xcrun simctl boot "$udid"
  booted_by_test=1
fi
cleanup() {
  xcrun simctl terminate "$udid" "$bundle_id" || true
  if [[ "$booted_by_test" == 1 ]]; then xcrun simctl shutdown "$udid" || true; fi
}
trap cleanup EXIT
xcrun simctl bootstatus "$udid" -b
xcrun simctl install "$udid" "$app"
data_dir="$(xcrun simctl get_app_container "$udid" "$bundle_id" data)"
rm -f "$data_dir/Documents/scan-ui-result" "$data_dir/Documents/scan-ui-stage"
xcrun simctl launch --stdout="$test_root/stdout.log" --stderr="$test_root/stderr.log" "$udid" "$bundle_id"
for _ in $(seq 1 60); do
  if [[ -f "$data_dir/Documents/scan-ui-stage" ]]; then break; fi
  sleep .5
done
test "$(cat "$data_dir/Documents/scan-ui-stage")" = READY_FOR_HOME
# Launch another system app: UIKit delivers the real resign/background lifecycle.
xcrun simctl launch "$udid" com.apple.Preferences
for _ in $(seq 1 30); do
  if [[ -f "$data_dir/Documents/scan-ui-result" ]]; then break; fi
  sleep .5
done
cat "$test_root/stdout.log"
cat "$test_root/stderr.log"
test "$(cat "$data_dir/Documents/scan-ui-result")" = PASS
cp "$data_dir/Documents/scan-ui-"*.png "$repo_root/artifacts/scan-ui/"
cp "$test_root/stdout.log" "$test_root/stderr.log" "$repo_root/artifacts/scan-ui/"
echo SCAN_UI_SIMULATOR_ACCEPTANCE_OK

# Independent rootless UIKit package. Existing CLI target and DEB remain intact.
make -C "$repo_root/theos/scan-ui" package FINALPACKAGE=1 THEOS="$THEOS" \
  TARGET_CODESIGN=ldid TARGET_CODESIGN_FLAGS=-S
cp "$repo_root/theos/scan-ui/packages/"*.deb "$repo_root/artifacts/scan-ui/"
package="$(find "$repo_root/theos/scan-ui/packages" -name '*.deb' -print -quit)"
dpkg-deb -c "$package"
dpkg-deb -f "$package" Package Architecture
dpkg-deb -x "$package" "$test_root/device-package"
binary="$test_root/device-package/var/jb/Applications/OpenHCScanDemo.app/OpenHCScanDemo"
test -f "$binary"
lipo "$binary" -verify_arch arm64
otool -L "$binary"
ldid -h "$binary" 2>&1 | grep CodeDirectory
echo SCAN_UI_ROOTLESS_ARM64_PACKAGE_OK
