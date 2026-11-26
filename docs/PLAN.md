# OpenHC-iPad Stage 0 Plan

## Scan session core implementation (2026-11-26)

Task 1 now has common Kotlin source: ScanReceiverSession.start emits OPEN_CONTROL_LISTENER; separate initial-FE35 onControlRfcommReady and onControlSdpReady callbacks must both succeed in the same generation before PAIRING_READY(QR,PIN). Accept revokes QR and permits a one-shot same-PIN AUTH_HANDOFF; Stop, transport failure, reversed clock and deadline emit CLEAR_PAIRING then CLOSE_CONTROL_TRANSPORT. Old-generation callbacks are ignored. Platform callers must execute returned actions in order and schedule tick using deadlineMillis; the model itself performs no I/O or timer scheduling. The existing Fe35ControlBridge.listenerReady remains exclusively the later auth listener callback.

The QR builder/address/host rules follow fixed upstream 8132399bea6aa86d68da6d3e1d9e3e001c0a7643; PIN uses the existing secure entropy source with bounded unbiased 20-bit rejection sampling. Inputs are memory-only and diagnostics redact QR/PIN/host/address. Ten new common tests cover synthetic exact QR/UTF-8, leading zero, rejection boundaries, partial startup, stale events, expiration, cleanup and same-PIN handoff. Local Gradle JVM execution was blocked by the existing JRE lacking JAVA_COMPILER/JDK tools; diff whitespace check passed. macOS CI validation is pending, so source existence is not yet a Native test PASS.

This implements only the session model. No screen QR/scan-capable app, real FE35 start/stop integration, root supervisor or IPC exists yet. Next is task 2: wire actual transport listener/SDP readiness and stop/cleanup to this model, using a synthetic BTdaemon boundary. No device/radio/identity-file access occurred. Real-phone scanning remains unavailable; FE36 auth/session, Wi-Fi/TCP, DMSDP/media remain outside this change.


Current status (2026-11-26): tested revision `b4c66242c775af7470504fb365cba3a02d8d9fc6`; macOS CI `45775185368` passed. The real CLI/C/Objective-C/Kotlin-Native bridge completed synthetic FE35 control negotiation in the iOS Simulator (190 assertions), and the local identity provider plus automatic controller BD_ADDR query are validated. This evidence covers the FE35 control path only: authentication, DMSDP, and media have not been migrated or verified end-to-end, so the port is not complete.

The original identity asset is available and existing-provider schema validation passed; CI45775185368 / b4c66242 package 0.3.5 is installed on iPad5,1 with the expected binary hash. A single 64 KiB collector capture classified BROKER, a limited point-in-time result. These facts do not supply a phone initiation path: the user’s working OpenHC flow is receiver Start → FE35 listener-ready → PairingReady QR/PIN display → phone scans. The prior phone initiation instruction is retracted; do not run headless inbound waiting for this user flow.

Missing software: PairingQrCode generation and QR rendering/UI, one session-scoped random PIN shared with later auth, listener-ready-to-UI/lifecycle wiring, and full WirelessReceiverSession/runner/platform startup. The Theos target is a Foundation command-line tool. BLE/GATT advertisement is also absent, but fixed upstream manual scan mode does not require it (WirelessController.beaconPlan returns null outside AUTO). Authentication state machine, Wi-Fi/TCP session startup, DMSDP and media remain unported; QR alone will not complete the connection.

Next software task: connect real listener-ready/stop events to the new Native QR/PIN/session core, then implement the UIKit foreground app and bounded supervisor IPC. The completed audit and four runnable mock acceptance deliverables are in docs/SCAN-STARTUP-IMPLEMENTATION.md; these components remain unimplemented. No phone acceptance or Trial now. Direction: receiver scan startup → Bluetooth control → auth → Wi-Fi/TCP → DMSDP/media.

Implementation boundary audit completed: see [scan-startup implementation](SCAN-STARTUP-IMPLEMENTATION.md) for four ordered code tasks and mock acceptance. Next is the Native QR/PIN/session core; no phone acceptance or Trial is authorized by this plan.

The remaining sections preserve the historical Stage 0 plan and evidence; next actions are governed by the current scan-startup paragraphs above.

Target: iPad mini 4 Wi-Fi (A8, 2 GB), iPadOS 15.8.8, Dopamine rootless, Sileo DEB. Development is Windows + WSL2/Theos; no local Mac is available.

The Kotlin/Native protocol library plus Objective-C/C platform layer is a hypothesis under test, not a selected architecture. JVM/JAR execution on iPad is out of scope. Kotlin 2.1.20 and Gradle 8.13 mirror the read-only reference project's pins. The initial bridge deliberately contains no protocol behavior.

Stage 0 gate 1: build an `iosArm64` static framework, expose an Objective-C callable self-check, link it into a Theos rootless command-line package, inspect arm64/minimum OS/link dependencies and signing, then run on the physical iPad and observe `KOTLIN_BRIDGE_OK`. A macOS CI build is a prerequisite because this workstation has no Apple toolchain. CI or simulator evidence does not count as physical-device evidence.

Gate 2: copy the fixed-revision `WifiChannels.kt` into common Kotlin and test JVM/Native behavior for channel/frequency mappings, boundaries and exceptions. Evaluate the minimal `WifiConnectionInfo` dependency closure separately. Do not change protocol behavior to make compilation pass. `MalformedMessageException` extends `java.io.IOException`; record an explicit Native replacement point before migrating callers.

Later gates cover authentication vectors (SPEKE3072, X25519, Ed25519, AES-GCM, HKDF), BTstack FE35/FE36 channels/SDP/actual channel numbers/authentication requirements/I/O/close, and hotspot IP/SSID/BSSID/frequency. Showcase MISManager and bridge100 are references only; bridge MAC is not assumed to equal BSSID. The password is local-only. Ordinary RFCOMM connection is not evidence of a real HiCar handshake.

Identity files and keys are excluded. All tests use synthetic values; logs must not contain passwords or keys. Reference repositories remain read-only.

Progress on 2026-11-25: gate 1 physical bridge passed by user-reported `KOTLIN_BRIDGE_OK`; the agent has not captured a device shell or architecture output. The next 0.2.0 probe adds a synthetic WifiConnectionInfo check via `--wifi`, with the parser slice kept verbatim and explicit platform-specific exception classes. Subsequent authentication/Bluetooth/hotspot evidence requirements and source findings are tracked in `docs/NEXT-PROBES.md`. No full protocol port is authorized by a hello result.

Progress on 2026-11-26: authentication standard vectors and a synthetic SPEKE3072 arithmetic/key-derivation slice passed JVM/Native simulator CI with a pinned static OpenSSL candidate. This validates a bounded backend experiment only. Deliver 0.3.0 for physical `--auth` and read-only `--platform` inventory before further live BTstack/hotspot work. Complete authentication state-machine/real HiCar transcript evidence remains outstanding.

Subsequent 2026-11-26 screenshots confirm physical `AUTH_VECTORS_OK`, platform inventory, and successful manual BTstack service registration/start. Next: 0.3.1 bounded daemon GET_VERSION/GET_STATE query, synthetic stream tests and signed rootless package. Then resolve actual FE35/FE36 SDP and channel lifecycle; a daemon response does not pass that gate. AP and real handshake remain outstanding.

The user then confirmed 0.3.1 query success (version 1.1, revision 3257, OFF state) and named an Honor 20 Pro / HarmonyOS 4.0 / HiCar peer. The bounded 0.3.2 daemon-side FE35/FE36 listener/SDP registration/cleanup/re-registration experiment subsequently passed on the physical device in two cycles. Do not conflate this with real peer SDP, no forced link authentication, negotiated channel direction, or I/O. Controller ownership and restoration must be resolved before powered experiments.
