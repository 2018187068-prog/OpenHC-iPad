#!/bin/bash
# Combined review entry; NOT full S0/device acceptance. Existing tools required:
# Xcode/JDK17/Gradle8.13, Theos/ldid/dpkg; RUNNER_TEMP must name a private work dir.
set -euo pipefail
cd "$(dirname "$0")/.."
test "$#" -eq 1 || { echo 'usage: bash scripts/check-scan-owner-apple.sh /absolute/pinned-source.zip' >&2; exit 2; }
test -n "$RUNNER_TEMP"
mkdir -p artifacts/logs artifacts/scan-owner "$RUNNER_TEMP"
printf 'source_commit=%s\nrun_id=%s\nscope=owner-native-common-UI-focused-not-S0\nproduction_admission=deny-all\njvm_validation=focused-host-job\n' \
  "$(git rev-parse HEAD)" "${GITHUB_RUN_ID:-local}" > artifacts/scan-owner/BUILD.txt
source_manifest() {
python3 - <<'PY'
from pathlib import Path
import hashlib
paths = set()
for directory in ('theos/scan-owner', 'bridge/src', 'native/crypto'):
    paths.update(p for p in Path(directory).rglob('*')
                 if p.is_file() and not {'.theos', 'packages', 'build'}.intersection(p.parts))
for directory in ('theos/scan-ui',):
    paths.update(p for p in Path(directory).rglob('*')
                 if p.is_file() and not {'.theos', 'packages', 'build'}.intersection(p.parts)
                 and (p.suffix in ('.c', '.h', '.m', '.plist') or p.name == 'Makefile'))
for name in (
    'build.gradle.kts', 'settings.gradle.kts', 'gradle.properties', 'bridge/build.gradle.kts',
    '.github/workflows/scan-app-focused.yml',
    'theos/btstack-probe.c', 'theos/Fe35CleanupCertainty.h', 'theos/fe35-control-bridge.h', 'theos/fe35-control-bridge.m',
    'theos/Fe35BridgeBounds.h',
    'theos/main.m', 'theos/fe35-bridge-smoke.m',
    'theos/session-owner-probe.c', 'theos/scan-supervisor/ScanHelperClient.h',
    'theos/scan-supervisor/ScanHelperClient.m',
    'scripts/check-scan-owner-apple.sh', 'scripts/prepare-scan-owner-crypto.py',
    'scripts/test-scan-owner.py', 'scripts/scan-owner-tests.c',
    'scripts/test-scan-owner-process.py', 'scripts/scan-owner-process-tests.c',
    'scripts/scan-owner-process-fixture.c', 'scripts/check-scan-owner-package.py',
    'scripts/test-scan-owner-crypto.py', 'scripts/scan-owner-sim-fixture.m',
    'scripts/test-simulator-failure-evidence.py',
    'scripts/fe35-cli-smoke-runner.m', 'scripts/scan-transport-sim-fixture.m',
    'scripts/hicar-auth-sim-fixture.m',
    'scripts/fe36-cid-sim-fixture.m', 'scripts/test-fe36-cid-simulator.py',
    'scripts/test-fe36-wifi-diagnostics.py',
    'scripts/test-fe36-cancellation-order.py',
    'scripts/test-fe36-case-matrix.py',
    'scripts/test-fe35-cleanup-certainty.py', 'scripts/fe35-cleanup-certainty-test.c',
    'docs/FE35-CLEANUP-CERTAINTY-DIAGNOSTIC.md',
    'docs/FE36-CONSOLIDATED-DIAGNOSTIC-MATRIX.md',
    'scripts/test-fe36-negative-terminal.py',
    'theos/Fe36AuthTransport.h',
    'theos/NearbyWifiTransport.h', 'theos/NearbyWifiListener.h',
    'scripts/test-nearby-wifi-harness.py', 'scripts/test-nearby-wifi-listener.py',
    'scripts/nearby-wifi-listener-test.c', 'docs/FE36-NEARBY-LISTENER-CORRECTION.md',
    'scripts/nearby-tcp-test-phone.py', 'docs/FE36-LIVE-TCP-CONTROL.md',
    'scripts/nearby-tcp-pump-test.c',
    'scripts/fe35-inbound-sim-probe-stubs.c', 'scripts/test-fe35-cli-smoke-simulator.sh',
    'scripts/fe35-control-bridge-test-stub.c', 'scripts/btstack-sigpipe-test.c',
    'scripts/test-btstack-probe.py', 'scripts/test-btstack-transport-socket.py',
    'scripts/test-session-owner-probe.py', 'scripts/check-scan-demo-archive.py',
    'scripts/scan-demo-dpkg-deb.sh',
    'scripts/test-fe35-cli-inbound-simulator.py', 'scripts/check-scan-ui.sh',
    'scripts/scan-ui-tests.m', 'scripts/test-scan-qr-cpu.py', 'scripts/build-crypto-backend.sh'):
    paths.add(Path(name))
for p in sorted(paths):
    print(hashlib.sha256(p.read_bytes()).hexdigest(), p.as_posix())
PY
}
source_manifest > artifacts/scan-owner/source-inputs.sha256
python3 scripts/prepare-scan-owner-crypto.py "$1" 2>&1 | tee artifacts/logs/owner-crypto-source.log
# Gradle tracks current inputs. NEVER copy an old framework from the ZIP.
# Full JVM validation belongs to focused-host; do not duplicate it on macOS.
gradle :bridge:linkReleaseFrameworkIosArm64 \
  :bridge:linkReleaseFrameworkIosSimulatorArm64 :bridge:iosSimulatorArm64Test \
  --no-daemon --stacktrace 2>&1 | tee artifacts/logs/owner-current-frameworks.log
export OPENHC_BRIDGE_FRAMEWORK_DIR="$PWD/bridge/build/bin/iosArm64/releaseFramework"
bash scripts/verify-apple-artifact.sh "$OPENHC_BRIDGE_FRAMEWORK_DIR/OpenHCBridge.framework" 2>&1 | tee artifacts/logs/owner-framework-audit.log
python3 scripts/test-scan-owner.py 2>&1 | tee artifacts/logs/owner-darwin-core.log
python3 scripts/test-scan-owner-process.py --output artifacts/scan-owner/process 2>&1 | tee artifacts/logs/owner-darwin-process.log
python3 scripts/test-fe36-negative-terminal.py 2>&1 | tee artifacts/logs/owner-fe36-negative-terminal.log
python3 scripts/test-fe36-wifi-diagnostics.py 2>&1 | tee artifacts/logs/owner-fe36-wifi-diagnostics.log
python3 scripts/test-fe36-cancellation-order.py 2>&1 | tee artifacts/logs/owner-fe36-cancellation-order.log
python3 scripts/test-fe36-case-matrix.py 2>&1 | tee artifacts/logs/owner-fe36-case-matrix.log
python3 scripts/test-fe35-cleanup-certainty.py 2>&1 | tee artifacts/logs/owner-fe35-cleanup-certainty.log
python3 scripts/test-nearby-wifi-harness.py 2>&1 | tee artifacts/logs/owner-nearby-wifi-harness.log
python3 scripts/test-nearby-wifi-listener.py 2>&1 | tee artifacts/logs/owner-nearby-wifi-listener.log
clang -std=c11 -Wall -Wextra -Werror scripts/nearby-wifi-listener-test.c -o "$RUNNER_TEMP/nearby-wifi-listener-test"
"$RUNNER_TEMP/nearby-wifi-listener-test" 2>&1 | tee artifacts/logs/owner-nearby-production-listener.log
clang -std=c11 -Wall -Wextra -Werror scripts/nearby-tcp-pump-test.c -o "$RUNNER_TEMP/nearby-tcp-pump-test"
"$RUNNER_TEMP/nearby-tcp-pump-test" 2>&1 | tee artifacts/logs/owner-nearby-production-tcp-pump.log
for suite in btstack-probe btstack-transport-socket session-owner-probe; do
  python3 "scripts/test-$suite.py" 2>&1 | tee "artifacts/logs/owner-darwin-$suite.log"
done
# Actual deployment branch (no test admission), both SDKs. No helper rebuild.
for sdk in iphoneos iphonesimulator; do
  {
  minimum=-miphoneos-version-min=15.0; target=iosArm64
  if [[ "$sdk" == iphonesimulator ]]; then minimum=-mios-simulator-version-min=15.0; target=iosSimulatorArm64; fi
  xcrun --sdk "$sdk" clang -dM -E -include sys/un.h -x c /dev/null > "artifacts/scan-owner/$sdk-peer-macros.txt"
  if grep -q '^#define LOCAL_PEERTOKEN ' "artifacts/scan-owner/$sdk-peer-macros.txt"; then
    echo "$sdk peer collector branch=kernel-evidence-only production-admission=deny-all"
  else
    echo "$sdk peer collector branch=unsupported-deny production-admission=deny-all"
  fi
  for source in ScanOwner.c ScanOwnerPeer.c ScanLeaseProtocol.c ScanLeaseChannel.c ScanGuardProcess.c ScanBrokerProcess.c; do
    xcrun --sdk "$sdk" clang -arch arm64 "$minimum" -std=c11 -Wall -Wextra -Werror \
      -c "theos/scan-owner/$source" -o "$RUNNER_TEMP/$sdk-$source.o"
  done
  for source in ScanOwnerRuntime.m ScanOwnerForeground.m ScanProcessLeaseAdapter.m ../fe35-control-bridge.m; do
    xcrun --sdk "$sdk" clang -arch arm64 "$minimum" -Wall -Wextra -Werror -fobjc-arc \
      -F"$PWD/bridge/build/bin/$target/releaseFramework" \
      -c "theos/scan-owner/$source" -o "$RUNNER_TEMP/$sdk-$(basename "$source").o"
  done
  xcrun --sdk "$sdk" clang -arch arm64 "$minimum" -std=c11 -Wall -Wextra -Werror \
    -c theos/btstack-probe.c -o "$RUNNER_TEMP/$sdk-native-probe.o"
  } 2>&1 | tee "artifacts/logs/owner-$sdk-deployment-compile.log"
done
# Original 3 FE35 + 8 scan cases retained, plus 11 real owner/native/common cases.
# Only daemon/admission/lease effects are synthetic.
bash scripts/test-fe35-cli-smoke-simulator.sh 2>&1 | tee artifacts/logs/owner-fe35-common-simulator.log
# CPU golden/3 system decoders, UIKit PONG/lifecycle and actual App DEB; no helper.
bash scripts/check-scan-ui.sh 2>&1 | tee artifacts/logs/owner-ui-app.log
# Build-only inert components: no enabled launch job, no helper replacement.
{
make -C theos/scan-owner package FINALPACKAGE=1 THEOS="$THEOS" TARGET_CODESIGN=ldid TARGET_CODESIGN_FLAGS=-S
package="$(find theos/scan-owner/packages -name '*.deb' -print -quit)"
python3 scripts/check-scan-owner-package.py "$package"
mkdir -p artifacts/scan-owner/inert-package
cp "$package" artifacts/scan-owner/inert-package/
dpkg-deb -c "$package"
dpkg-deb -x "$package" "$RUNNER_TEMP/owner-inert-package"
for name in broker guard; do
  binary="$RUNNER_TEMP/owner-inert-package/var/jb/usr/libexec/openhc-owner-inert/openhc-scan-$name"
  lipo "$binary" -verify_arch arm64
  ldid -h "$binary" 2>&1 | grep CodeDirectory
  otool -L "$binary"
  shasum -a 256 "$binary"
done
} 2>&1 | tee artifacts/logs/owner-inert-package.log
source_manifest > "$RUNNER_TEMP/owner-source-inputs-after.sha256"
cmp artifacts/scan-owner/source-inputs.sha256 "$RUNNER_TEMP/owner-source-inputs-after.sha256"
shasum -a 256 artifacts/scan-owner/source-inputs.sha256 >> artifacts/scan-owner/BUILD.txt
echo SCAN_OWNER_COMBINED_APPLE_OK_NOT_DEVICE_ACCEPTANCE
