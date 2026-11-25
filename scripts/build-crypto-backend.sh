#!/bin/bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
revision=45e844fa2a14ec92d146bd8f5778ac130b6625fb
work="${RUNNER_TEMP:?RUNNER_TEMP required}/openhc-openssl"
mkdir -p "$root/artifacts/logs" "$root/artifacts/licenses" "$work"
git clone --depth 1 --branch openssl-3.5.9 https://github.com/openssl/openssl.git "$work/source"
test "$(git -C "$work/source" rev-parse HEAD)" = "$revision"
cp "$work/source/LICENSE.txt" "$root/artifacts/licenses/OpenSSL-LICENSE.txt"
cp "$work/source/Configurations/15-ios.conf" "$root/artifacts/logs/openssl-ios-config.txt"
{
    echo 'candidate_backend=OpenSSL 3.5.9 (not a production selection)'
    echo "source_commit=$revision"
    echo 'deployment_target=15.0'
} > "$root/artifacts/logs/crypto-backend-version.txt"
for target in iosArm64 iosSimulatorArm64; do
    if [[ "$target" == iosArm64 ]]; then
        sdk=iphoneos
        config=ios64-xcrun
        minimum=-miphoneos-version-min=15.0
    else
        sdk=iphonesimulator
        config=iossimulator-arm64-xcrun
        minimum=-mios-simulator-version-min=15.0
    fi
    dest="$root/artifacts/crypto/$target"
    mkdir -p "$dest" "$work/$target"
    (
        cd "$work/$target"
        export SDKROOT="$(xcrun --sdk "$sdk" --show-sdk-path)"
        export CROSS_TOP="$(dirname "$SDKROOT")"
        export CROSS_SDK="$(basename "$SDKROOT")"
        export IPHONEOS_DEPLOYMENT_TARGET=15.0
        perl "$work/source/Configure" "$config" no-shared no-tests no-apps no-module no-dso no-asm \
            -arch arm64 "$minimum" --prefix="$work/install-$target"
        make -j3 build_libs
        cp libcrypto.a "$dest/"
        xcrun --sdk "$sdk" clang -arch arm64 -isysroot "$SDKROOT" "$minimum" -O2 \
            -Iinclude -I"$work/source/include" -I"$root/native/crypto" \
            -c "$root/native/crypto/openhc_crypto.c" -o "$dest/openhc_crypto.o"
        xcrun ar rcs "$dest/libopenhc_crypto.a" "$dest/openhc_crypto.o"
        lipo "$dest/libcrypto.a" -verify_arch arm64
        lipo "$dest/libopenhc_crypto.a" -verify_arch arm64
        otool -l "$dest/libcrypto.a" > "$dest/load-commands.txt"
        if [[ "$target" == iosArm64 ]]; then
            awk '/minos/ { if ($2+0 > 15) exit 1; found=1 } END { if (!found) exit 2 }' "$dest/load-commands.txt"
        fi
        shasum -a 256 "$dest/"*.a
    ) 2>&1 | tee "$root/artifacts/logs/crypto-$target-build.log"
done
