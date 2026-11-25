# Remaining Stage 0 probes

These are pending gates, not a claim of protocol portability. Reference revisions remain OpenHC `8132399bea6aa86d68da6d3e1d9e3e001c0a7643` and Showcase `ce9d1d50758f67307deb3f00c901a8e82894930c`.

## Authentication: candidate backend probe in CI

`core/auth/src/main/kotlin/io/github/gcbond/openhc/core/auth/crypto/AuthCrypto.kt` imports `java.math.BigInteger`, `java.security.MessageDigest`/`GeneralSecurityException`, `javax.crypto.Cipher`/`Mac`/specs, and Bouncy Castle X25519/Ed25519. This file cannot be copied unchanged into common Native code.

Existing `core/auth/src/test/.../CryptoTest.kt` includes named SHA-256 FIPS180, HMAC RFC4231, HKDF RFC5869, AES-GCM standard, Ed25519 RFC8032, X25519 RFC7748, and MODP prime/fixed-length tests. Use their synthetic/public test vectors without printing vector bytes, keys, passwords or derived secrets. SPEKE3072 also needs transcript/public-value validation, leading-zero padding and invalid-value/rejection equivalence; a passing generic modPow operation is insufficient.

The executable candidate probe now compares copied JVM-reference operations with OpenSSL-backed Native operations using the same standard vectors and synthetic SPEKE3072 math slice. See `docs/AUTH-PROBE.md` for exact boundaries, backend commit and required rejection tests. OpenSSL has compiled as static arm64 device/simulator libraries, and the new JVM/Native simulator vector tests passed in run 45649915495. This is not production backend selection; new physical results and real authentication transcripts remain pending.

## Bluetooth: needs real platform/device evidence

OpenHC `NearbySession.kt` defines FE35 control and FE36 default authentication subchannel service UUIDs. `NearbyAction.kt` describes an authentication channel number and optional service UUID received from the peer. These UUIDs are not fixed RFCOMM channel numbers.

Showcase's BTstack daemon exposes RFCOMM service registration, SDP and per-client cleanup code, but its CarPlay client is not a HiCar implementation. At the fixed reference revision, `src/classic/rfcomm.c:2187` initializes `rfcomm_security_level` to `LEVEL_0` and passes it to L2CAP service registration; no `rfcomm_set_required_security_level` call was found under platform/daemon, port/ios or source. This is source-only evidence, not evidence about the binary installed on the iPad. The client header and launchd plist name the local Unix socket `/tmp/BTstack`; that known path is inspected without connecting by the 0.3.0 `--platform` probe. A probe must observe both FE35/FE36 services and actual SDP/negotiated channel numbers, verify the no-forced-link-authentication requirement, accept/open both channels, transmit/receive synthetic data, and close/reopen cleanly. Ordinary RFCOMM connection is insufficient to mark a real HiCar handshake passed.

Before a meaningful device run, establish the installed BTstack daemon/client version and a confirmed control endpoint on the iPad. A subsequent real handshake test requires the user's compatible HiCar phone and an explicit pairing attempt. No daemon changes, Bluetooth takeover or connection to an unknown host has been performed.

## Hotspot: needs actual capability and radio measurements

Showcase `source/Showcase.m` around `showcase_mis_manager` loads WirelessModemSettings and calls MISManager; `source/carplay_bt.m` names `bridge100`. This is reference code only. The target is the Wi-Fi model of iPad mini 4: availability of a working hotspot/AP is an unresolved gate, and the existence of MISManager or a bridge alone would not prove it.

First use a read-only device capability probe for available APIs and interfaces. Then measure actual AP IP, SSID, radio BSSID and center frequency/channel, independently validating the BSSID rather than assigning the bridge interface MAC. Report unavailable/unknown fields explicitly; do not guess. Hotspot passwords stay on the device and must never be written to CI artifacts or terminal logs. Opening/changing a hotspot is a separate live experiment, not part of the synthetic parser check.

## Completed device action (user-reported)

The user confirmed `/var/jb/usr/bin/openhc-bridge-check --wifi` returned OK. Expected stdout is `WIFI_CONNECTION_INFO_OK`; exit status and installed package version were not independently captured. This is an in-process synthetic parser probe; it does not enable Wi-Fi, read stored credentials or open Bluetooth connections.

## Next device handoff

The 0.3.2 handoff was completed: the user installed the package and reported two local registration cycles ending in `BTSTACK_LOCAL_SERVICES_OK` outside active peer testing. The phone was not needed. This closes the local daemon prerequisite, not live FE35/FE36 I/O or a HiCar handshake. User's intended later peer is Honor 20 Pro / HarmonyOS 4.0 / HiCar supported. Controller ownership and recovery remain prerequisites to powered tests.

Update 2026-11-26: user reports 0.3.1 daemon query success, version 1.1 / revision 3257 / state 0. Do not repeat the query as a required gate. Next work is bounded FE35/FE36 daemon-side registration/SDP probing plus controller ownership/recovery review before any radio power request, then actual peer channel tests. State 0 is BTstack OFF per the fixed reference, not evidence of an initialization failure or Apple's Bluetooth switch position. A compatible HiCar peer is required for the later real handshake.

Update 2026-11-26: user ran the 0.3.2 local service probe on the iPad and reported two successful cycles. FE35 used channel 16 with handles 65537 then 65539; FE36 used channel 17 with handles 65538 then 65540; the probe ended with `BTSTACK_LOCAL_SERVICES_OK`. This closes the local daemon registration/cleanup/channel-reuse prerequisite. It does not close the live wireless SDP, peer channel negotiation, security-level, dual-channel I/O, or HiCar handshake gates. The next transport probe must be bounded by controller ownership/recovery checks and a known compatible peer (Honor 20 Pro / HarmonyOS 4.0 / HiCar, user-reported).

Update 2026-11-26: CI 45670248895's DEB was installed via existing USB SSH after remote SHA-256 verification. The binary ownership command completed but explicitly lacked service/process access. External root-shell snapshots have now supplied that evidence: BTdaemon and Apple bluetoothd coexist, BlueTool is registered but idle, BTLEServer is running, and no Showcase recovery guard is armed. This completes the read-only audit, **not** exclusive ownership or recovery validation. See `docs/BTSTACK-OWNERSHIP.md` for the exact evidence and applicable Dopamine/rootless source path.

Latest update: the bounded power-only client and independent launchd guard are implemented. One physical trial observed WORKING then OFF and verified Apple/baseline restoration before disarming; logs and limitations are in `docs/BTSTACK-OWNERSHIP.md`. A bare `CarPlay Simulator` PID 27078 was missed by the initial path-only name match; parsing is fixed. The user did not start Showcase, and the latest snapshot has no Showcase main process or Bluetooth helper. The same executable also hosts a persistent BAA broker, and its socket exists. Thus the name does not prove an active/competing session; withdraw the request for normal Stop. Keep the gate at shared-helper role verification using only PID/socket metadata, without killing the broker or reading its authentication data. Then implement a bounded live peer transport probe and arrange the separate Honor 20 Pro session for over-air FE35/negotiated auth-subchannel SDP, channel roles, synthetic transport I/O where appropriate, and close/reopen. No live HiCar authentication payloads/keys are to be logged.

Physical `AUTH_VECTORS_OK`, platform inventory, daemon query and two local FE35/FE36 registration cycles are already passed; do not reinstall 0.3.1 or repeat those as prerequisites. See `docs/BTSTACK-PROBE.md`: client disconnect triggers daemon cleanup, and query/local-registration passes do not pass live FE35/FE36 or AP gates. Available MIS/MobileWiFi symbols do not establish a functioning hotspot on this Wi-Fi-only target.
