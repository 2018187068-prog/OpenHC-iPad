# Remaining Stage 0 probes

These are pending gates, not a claim of protocol portability. Reference revisions remain OpenHC `8132399bea6aa86d68da6d3e1d9e3e001c0a7643` and Showcase `ce9d1d50758f67307deb3f00c901a8e82894930c`.

## Authentication: source review only

`core/auth/src/main/kotlin/io/github/gcbond/openhc/core/auth/crypto/AuthCrypto.kt` imports `java.math.BigInteger`, `java.security.MessageDigest`/`GeneralSecurityException`, `javax.crypto.Cipher`/`Mac`/specs, and Bouncy Castle X25519/Ed25519. This file cannot be copied unchanged into common Native code.

Existing `core/auth/src/test/.../CryptoTest.kt` includes named SHA-256 FIPS180, HMAC RFC4231, HKDF RFC5869, AES-GCM standard, Ed25519 RFC8032, X25519 RFC7748, and MODP prime/fixed-length tests. Use their synthetic/public test vectors without printing vector bytes, keys, passwords or derived secrets. SPEKE3072 also needs transcript/public-value validation, leading-zero padding and invalid-value/rejection equivalence; a passing generic modPow operation is insufficient.

Next executable experiment must isolate backend operations and compare JVM-reference and Native pass/fail results, including AES-GCM tamper rejection and X25519 invalid/zero-output handling. An external C backend is a candidate requiring its own iOS 15 arm64 build, symbols, licensing and error-semantics checks; none has been selected or linked. Authentication vectors have **not** passed on Native or the iPad.

## Bluetooth: needs real platform/device evidence

OpenHC `NearbySession.kt` defines FE35 control and FE36 default authentication subchannel service UUIDs. `NearbyAction.kt` describes an authentication channel number and optional service UUID received from the peer. These UUIDs are not fixed RFCOMM channel numbers.

Showcase's BTstack daemon exposes RFCOMM service registration, SDP and per-client cleanup code, but its CarPlay client is not a HiCar implementation. A probe must observe both FE35/FE36 services and actual SDP/negotiated channel numbers, verify the no-forced-link-authentication requirement, accept/open both channels, transmit/receive synthetic data, and close/reopen cleanly. Ordinary RFCOMM connection is insufficient to mark a real HiCar handshake passed.

Before a meaningful device run, establish the installed BTstack daemon/client version and a confirmed control endpoint on the iPad. A subsequent real handshake test requires the user's compatible HiCar phone and an explicit pairing attempt. No daemon changes, Bluetooth takeover or connection to an unknown host has been performed.

## Hotspot: needs actual capability and radio measurements

Showcase `source/Showcase.m` around `showcase_mis_manager` loads WirelessModemSettings and calls MISManager; `source/carplay_bt.m` names `bridge100`. This is reference code only. The target is the Wi-Fi model of iPad mini 4: availability of a working hotspot/AP is an unresolved gate, and the existence of MISManager or a bridge alone would not prove it.

First use a read-only device capability probe for available APIs and interfaces. Then measure actual AP IP, SSID, radio BSSID and center frequency/channel, independently validating the BSSID rather than assigning the bridge interface MAC. Report unavailable/unknown fields explicitly; do not guess. Hotspot passwords stay on the device and must never be written to CI artifacts or terminal logs. Opening/changing a hotspot is a separate live experiment, not part of the synthetic parser check.

## Current device action

After installing the 0.2.0 DEB, run `/var/jb/usr/bin/openhc-bridge-check --wifi`. Expected stdout is `WIFI_CONNECTION_INFO_OK` and exit status 0. This is an in-process synthetic parser probe; it does not enable Wi-Fi, read stored credentials or open Bluetooth connections.
