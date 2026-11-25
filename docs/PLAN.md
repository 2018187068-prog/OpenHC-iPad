# OpenHC-iPad Stage 0 Plan

Current status (2026-11-26): prior startup and broker-owner checks are complete
and must not be repeated. The fixed broker endpoint owner was observed as PID
27078 and matched its comm; this confirms a broker role, not absence of a
parallel active session or exclusive controller ownership. One earlier
power/restoration cycle passed its state and restore observations, but its
preflight missed a shared helper, so it is not an uncontested ownership PASS.
This turn adds a finite metadata classifier, explicit synthetic two-channel
runner core, and a bounded FE35 outbound C socket adapter/CLI for a controlled
synthetic peer. Installed BTdaemon RFCOMM opened-event routing/length remains
unknown until the adapter's first controlled connection observes it. The C
socket mock is wired into CI but has not run in this Windows environment
because clang is unavailable. GitHub-hosted macOS run `45698383060` passed the
actual C mock and Theos package build; the candidate DEB is version 0.3.3 and
was not installed. No wireless SDP/I/O or real HiCar handshake has passed. The
synthetic loopback is an optional engineering test; there is no
evidence the user has a suitable peer, and it is not a HiCar project
prerequisite. No device command is ready because the adapter is not integrated
with the existing power driver's guarded WORKING lifetime. The shortest real
Honor path is FE35 incoming/listen/accept plus its control state machine, then
protocol-directed auth transport, followed by a single-driver lease callback.
See `HANDOFF-CURRENT.md` and `BTSTACK-OWNERSHIP.md` for this boundary.

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
