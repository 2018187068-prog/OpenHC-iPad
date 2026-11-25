# Decisions and Evidence

## 2026-11-25: Isolated validation harness

- The reference repositories at `8132399bea6aa86d68da6d3e1d9e3e001c0a7643` and `ce9d1d50758f67307deb3f00c901a8e82894930c` are clean and remain read-only.
- `D:\OpenHC-iPad` was absent before this work, so the validation project was created there.
- Reuse reference Kotlin 2.1.20 and Gradle 8.13 for the first compiler probe; this is a reproducibility choice, not proof that they are optimal or compatible until CI output confirms the iOS target.
- A local static bridge is the smallest useful experiment. Its hello API says nothing about protocol portability.
- Windows reports no registered WSL distribution. GitHub CLI is unauthenticated. SSH config contains only `aliyun-vps` and `singa-vps`; neither is an iPad alias and neither was contacted. No xcrun, Theos, clang or ldid command was found on Windows.
- Gradle 8.13 was downloaded and parsed the new project on Windows; it disabled both Apple targets and the JVM test task could not start because only a Java 8 JRE is installed. No Kotlin compilation, simulator, CI or device result is claimed.
- An isolated JDK 8 archive download into the OS temp directory stalled at roughly 69%; its curl process was stopped. The partial temp archive could not be removed because the terminal policy rejected the deletion command.
- Stage 0 is not passed until the physical iPad run.

## Open platform question

`MalformedMessageException` in the reference extends `java.io.IOException`. Native migration needs an explicit common exception type and call-site policy; do not silently replace it during unrelated compilation work.

## 2026-11-25: User-reported physical bridge pass; minimal WiFi parser probe

The user reported `KOTLIN_BRIDGE_OK` from the physical device after install/run instructions. Record this as user-reported evidence, with no agent SSH session, architecture output or on-device artifact hash claimed. Gate 1 is passed at that evidence level; this does not complete Stage 0.

Extract WifiMode/WifiConnectionInfo without parser edits. Exclude the adjacent WifiLinkMessages object and its JVM-only charset conversion. Preserve IOException ancestry on JVM via an explicit actual exception and use Exception on Native. Keep message/cause, wire fields, validation and existing acceptance of leading zeroes in numeric port text; do not alter protocol semantics to compile. Audit session IOException catches before migrating session code. All new probe credentials are synthetic and never emitted in probe output.

## 2026-11-25: User-confirmed WiFi parser device pass

The user confirmed the second command (`/var/jb/usr/bin/openhc-bridge-check --wifi`) returned OK. Accept this as user-reported physical execution of the synthetic parser probe, separately from CI/simulator results. No package-version output or installed hash was supplied. Authentication, BTstack dual channels and actual hotspot capability remain unverified.

## 2026-11-26: Pinned static authentication-backend candidate

OpenSSL 3.5.9, commit `45e844fa2a14ec92d146bd8f5778ac130b6625fb`, is used solely as a reproducible C-backend experiment. It is not selected as the final architecture. Copy JVM AuthCrypto exactly, adapt only an explicit common interface and HKDF array-copy boundary, and compare shared standard vectors and a synthetic SPEKE3072 math slice. Preserve reference fixed-width/public-value behavior for tested cases; record unknown exception/encoding/state-machine equivalence instead of changing protocol callers. CI 45649915495 passed both test targets and static rootless packaging.

Add a read-only platform inventory to the same 0.3.0 package to resolve known device prerequisites. It may load platform bundles for class/symbol inspection and enumerate IPv4 interfaces, but does not instantiate sharing control, alter WiFi state, read credentials or connect a Bluetooth socket. API/symbol presence is not hotspot capability or HiCar success. Wait for the user's auth result/inventory before claiming physical evidence or doing live dual-channel/AP experiments. Include upstream OpenHC/OpenSSL licenses with the validation package.

## 2026-11-26: Device evidence and bounded BTstack query

Accept user screenshot `AUTH_VECTORS_OK` as physical synthetic-vector evidence, not authentication state-machine or handshake evidence. Platform inventory confirms required symbol presence, not hotspot/AP capability. The user's manual bootstrap/kickstart sequence subsequently yielded a registered launchd service, `/tmp/BTstack` listener and running PID 35779 at 00:39.

Before radio or service registration work, add an independently implemented two-query client against that confirmed local socket. Permit only GET_VERSION and GET_STATE, with bounded lengths/counts/deadlines and explicit close. Synthetic server tests verify framing/failure behavior on macOS; device responsiveness stays pending until user supplies output. No power/discoverability/pairing commands are sent, but daemon disconnect cleanup can update discoverability, schedule power-off or disconnect HCI links when no clients remain; document this and run outside active Bluetooth sessions. Do not mislabel the connected query as side-effect-free or treat a returned version as binary provenance.

## 2026-11-26: Local FE35/FE36 registration prerequisite

After physical daemon query success, proceed with transient listener/SDP registrations only while the observed BTstack state is OFF. Choose free candidate channels and print actual values, skip only explicit busy results, avoid persistent channel DB writes and never unregister a resource without a matching successful ownership acknowledgement. Explicitly remove owned records/listeners, use a query ordering barrier, then prove same-channel local reuse on another connection. Partial/malformed/timeout cases must fail; uncertain cleanup is reported rather than hidden. This is a local registration prerequisite; it does not validate radio discoverability, actual SDP over air, real peer I/O, installed security policy or HiCar handshake. User-named Honor 20 Pro / HarmonyOS 4.0 is the intended later peer, not a verified compatibility claim.

Physical result: the user reported two successful cycles on 2026-11-26, with FE35 on channel 16 and FE36 on channel 17, and new SDP handles on the second cycle. Mark the local registration/cleanup/channel-reuse prerequisite complete while preserving the separate live transport and handshake gates.
