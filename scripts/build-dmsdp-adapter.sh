#!/bin/bash
# Current-source CommonCrypto adapter only; pinned OpenSSL archives stay unchanged.
set -euo pipefail
cd "$(dirname "$0")/.."
for target in iosArm64 iosSimulatorArm64; do
  sdk=iphoneos; minimum=-miphoneos-version-min=15.0
  if [[ "$target" == iosSimulatorArm64 ]]; then sdk=iphonesimulator; minimum=-mios-simulator-version-min=15.0; fi
  dest="$PWD/artifacts/crypto/$target";mkdir -p "$dest"
  xcrun --sdk "$sdk" clang -arch arm64 "$minimum" -std=c11 -Wall -Wextra -Werror -O2 \
    -c native/dmsdp/openhc_dmsdp.c -o "$dest/openhc_dmsdp.o"
  xcrun ar rcs "$dest/libopenhc_dmsdp.a" "$dest/openhc_dmsdp.o"
  lipo "$dest/libopenhc_dmsdp.a" -verify_arch arm64
  shasum -a 256 "$dest/libopenhc_dmsdp.a"
done
