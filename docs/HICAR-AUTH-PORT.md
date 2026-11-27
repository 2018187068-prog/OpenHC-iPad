# Same-PIN HiCar authentication protocol slice — 2026-11-28

Original Run: run_25334cb0a007; task_dc8a9b811763 / ctx_c3eff6a0385b.
Base: 5bedba3ac887af8d26062d2510d269992794e5a3, stage0-auth-validation.
This is runnable authentication software, not device/phone interoperability or full HiCar acceptance. Production admission and native radio/Trial effects remain disabled.

## Implemented closure and provenance

Read-only reference: D:/OpenHC-iPad-ref/OpenHC, commit 8132399bea6aa86d68da6d3e1d9e3e001c0a7643. Only source/tests and the explicitly synthetic auth vector resource were read; no identity/assets/credentials were used.

The nine upstream files below are ported under bridge/src/commonMain/kotlin/io/github/gcbond/openhc/bridge/hicarauth. They implement the real outer HiCar JSON session, accessory state machine, SPEKE PAKE, authenticated Ed25519 identity exchange, STS trusted reconnect, wire parsing/building, and memory trust contract. Existing OpenHarmony Apache notices remain in the derived state-machine/HiChain files.

New Portability.kt supplies common JSON parsing and platform entropy; crypto/AuthCrypto.kt maps the exact required primitives to the existing bridge.auth backend. No AuthBackend/native crypto/build-crypto source or archive format changed. The 2048-bit range-check modulus is copied from reference; the PAKE 3072-bit modulus reuses existing SpekeMathProbe.prime. No successful crypto operation is stubbed.

Pinned addition: org.jetbrains.kotlinx:kotlinx-serialization-json:1.8.1 in commonMain, exactly the reference dependency version. It supplies the common JSON DOM; no serialization compiler plugin, repository substitution, new crypto library, or backend expansion.

Deliberate portability/security changes:

- Java SecureRandom, BigInteger, MessageDigest, Arrays, ByteArrayOutputStream and charset APIs are replaced by common code or existing verified backend calls. Native entropy uses existing oh_random_bytes; JVM uses existing SecureRandom. Rejection sampling preserves uniform six-digit PINs including leading zeros. The exported coordinator never generates a replacement scan PIN.
- Preserve reference key ordering/compact JSON, field-case/number/unsigned-version semantics, message codes, supported-version checks, request retry/state behavior, PAKE/STS proof inputs and output derivation. No new wire header or downgrade default. Native/JVM common tests share the same synthetic golden bytes.
- Strict UTF-8 framing, 10,240-byte message limit, nesting 32 (including JSON nested inside data), bounded offset arithmetic; exported bridge additionally limits chunks to 4,096 and cumulative connection input to 65,536 bytes.
- Serialized bridge lock, one handoff and one connection incarnation, captured generation, absolute deadline at most 240 seconds, monotonic-clock validation, idempotent terminal cancellation. Stale generations are inert; same-generation wrong/reused connection closes the session.
- Cancel/retry/terminal paths wipe ephemeral PAKE/STS/key buffers. Immutable Kotlin strings and caller-owned transport/action copies cannot be recalled; the platform must release them promptly and never log them. No claim of complete managed-heap erasure.
- Verified exchange peerAuthId must match the outer handshake identity before commit, and a valid 16-byte session key must exist. This hardening deliberately rejects reference-permitted signed identity substitution; it does not change valid transcript bytes.
- Parser exceptions do not retain input/cause. Handshake notes expose only flags/version presence, not peer-supplied version. Exported actions have fixed reasons and redacted toString; SEND bytes and the one-shot key are transport/secret data, never diagnostics.
- File TrustStore/codec and JVM synchronization were not ported. Memory stores are confined to the serialized owner/auth executor. Sharing a store across concurrent bridge instances requires additional platform serialization.

## Exported bridge and same-PIN ownership

Fe36AuthSessionBridge is production protocol code exported by OpenHCBridge.framework; no deployed provider/factory is enabled. Fe36AuthConfig carries only in-memory service/self identity, envelope version and bounded device-info config supplied by a future trusted owner. It opens no file/socket and asserts no caller authority.

1. ScanReceiverSession actual RFCOMM+SDP callbacks produce PAIRING_READY; ACCEPTED clears frontend pairing and takeAuthHandoff emits the original one-shot AUTH_HANDOFF.
2. Owner passes that exact event, captured generation and original immutable session/lease deadline to handoff(event, nowMillis, deadlineMillis). It emits OPEN_AUTH_CONNECTION (an ordered adapter request, not a network action). It never refreshes the PIN or budget. The platform must pass the existing minimum deadline, not mint a new budget.
3. The serialized adapter assigns one positive connection incarnation, calls connected, and copies accepted FE36 bytes into receive. Execute returned SEND actions in order outside the bridge lock, on the same bounded connection. Preserve SEND before AUTHENTICATED; a SEND failure cancels the candidate connection and must not promote a key. No callbacks or I/O execute under the bridge lock.
4. Only real successful PAKE proof plus verified signed identity exchange, or verified supplied-trust STS, yields AUTHENTICATED. takeSessionKey(generation, connection, nowMillis) validates time again, returns a copy once and wipes the internal key. Null requires closing the candidate next-stage connection. This is not a WiFi/TCP/media session.
5. Owner Stop/background/deadline/disconnect must cancel this coordinator on the same serial executor and close FE36 even after cryptographic success; tick/stop/disconnected revoke an unconsumed key after success. Before success terminal actions are FAILED,CLOSE; after success CLOSE only. Stale callbacks cannot revive a completed bridge. Retain bridge/config/store/connection until its ordered terminal actions and worker return are processed.

Memory-only TrustStore has actual Ed25519 local identities and verified peer keys, partitioned by SHA256(service package || service type). commitPairing is called only after successful PIN identity proof/identity binding. Failure emits no authentication success. A platform secure-persistence implementation must provide a trusted authenticated snapshot, atomic identity+peer replacement, rollback on failure, access control, protected key storage and serialized access; it must never auto-trust deviceId or accept client-supplied records as authority. No platform persistence implementation or file store is provided. STS reconnect with verified memory records is tested; no-trust or tampered-key reconnect fails.

## Evidence and synthetic boundaries

Actual local execution on Windows/JDK17:

- Initial offline compile failed because exact JSON dependency was not cached; one ordinary online compile downloaded it through existing Maven Central and passed. No local HTTP429 occurred.
- Final focused command below passed in 52 seconds: 57 tests, zero failures/errors/skips. New auth suites: CVectorsTest 7, Fe36AuthBridgeTest 11, HiCarAuthSessionTest 17, RoundTripTest 10 (45 total); existing ScanReceiverSessionTest 12. Log: artifacts/scan-owner/auth-local-tests.log; XML: bridge/build/test-results/jvmTest. The extra Fe35ControlBridgeTest filter matches no class; it is not counted as a test.
- Includes all 38 upstream error probes, exact pair/STS/wrong-PIN replies and keys, outer envelope byte equality, fragmentation/UTF-8/limits, real-CSPRNG round trips, verified memory-trust reconnect, old/tampered trust rejection, atomic-store failure, same scan PIN, same-PIN recorded C transcript replay against fresh session randomness, signed peer substitution, retries, connection/generation fences, pre/post-success cancellation/expiry/reversed clock and one-shot key.
- Embedded synthetic C golden resource exactly equals upstream UTF-8 bytes: 56,826 bytes, SHA256 728e7b6b0b7d38c2094be3a5784a183fb5f87abdcb933291ebd33b550307c298. It contains C OpenHarmony deviceauth_lite golden outputs; this is independent reference evidence beyond a same-port roundtrip, not a fresh C implementation execution.
- python scripts/test-scan-owner-crypto.py: 6 tests passed (synthetic preparer tests, not a new download/digest verification of the real pinned archive). Bash syntax and Python compile checks passed for modified harness scripts; common auth sources contain no Java imports. Existing backend, owner/guard/UI production inputs unchanged. Old owner551+122/protocol308/process32 and UI checks were not repeated locally because their inputs did not change. They remain required in the new combined run.

Prepared Simulator execution (PENDING; no local Apple SDK): scripts/hicar-auth-sim-fixture.m is compiled into the existing owner/native/common Simulator harness, called from OHCScanOwnerRuntime.events at the actual AUTH_HANDOFF after existing same-PIN/CLEAR assertions. It executes four real-crypto exchanges through exported OHCBFe36AuthSessionBridge: same-PIN verified success, wrong PIN, forged Ed signature, signed changed peer. Both directions execute real AF_UNIX socketpair writes/reads; arbitrary 1..17-byte fragments reach the real Native framer. Descriptors close in finally. This is a separately coded ObjC phone algorithm translated from the same upstream TestPhone, not an independent vendor stack. Only synthetic identities and in-memory trust are used. Fixture time/connection IDs, admission, daemon and hardware effects are synthetic. No Bluetooth/FE36 device stream is exercised. Named static assertion labels and FE36_AUTH_OBJC_SOCKET_CASES_OK=4 are required; original 3+8+11+3, UI and package assertions remain. Source review checked ObjC selectors, ARC ownership/no switch-crossed block lifetime, crypto operation arguments, callback nonreentrancy and descriptors; actual compilation/runtime acceptance remains the macOS gate.

The auth fixture runs synchronously on the test owner's existing serial event executor without invoking the owner recursively. It uses an explicit synthetic protocol clock/deadline; it neither extends production owner timeouts nor changes the existing real-clock harness limits. Production must supply actual monotonic timestamps and schedule deadline checks independently.

## Commands and combined validation

```text
# JDK17 / existing Gradle8.13; set JAVA_HOME to the installed JDK17
gradle :bridge:jvmTest --tests '*hicarauth*' --tests '*ScanReceiverSessionTest*' --tests '*Fe35ControlBridgeTest*' --offline --no-daemon --console=plain
python scripts/test-scan-owner-crypto.py
bash -n scripts/check-scan-owner-apple.sh scripts/test-fe35-cli-smoke-simulator.sh
python -m py_compile scripts/test-fe35-cli-inbound-simulator.py

# GitHub macos-15 existing tools, pinned crypto-only ZIP; never restore old frameworks
bash scripts/check-scan-owner-apple.sh /absolute/pinned-source.zip
```

Existing workflow431974121 owner mode already runs all common JVM tests on Linux, current iosArm64/Simulator framework builds, all common Native tests, production SDK compilation, original/integrated Simulator cases, UI/system-decoder and actual App/inert package gates. This slice adds the ObjC compile unit/marker and source-manifest entry; no workflow skip/retry/repository override is introduced for the earlier external Maven429. JVM/Native failure remains fatal. All logs/stderr/XML, source SHA manifest, exact BUILD metadata and available package/Simulator evidence are archived by existing always-upload steps. Current frameworks must rebuild for changed common inputs. Crypto-only reuse gate remains source-valid against its pinned source; backend/build script are unchanged.

Submission is one bounded reviewed [skip ci] commit, one feature-branch push, exact remote-SHA verification, one workflow431974121 owner dispatch and one initial receipt. Corrected SHA/run receipt and preservation/index evidence are recorded in local Temp/openhc-auth-submission-20261128.json and handoff after submission; until then this report records local passes and pending Apple validation, not a new full pass. Previous run46028448171 evidence belongs only to 5bedba3; its coordinator-owned host429 recovery is untouched.

## Exact next production joins / shortest route to real HiCar

- Start/provider: installed ScanDemo syntheticDemoProvider remains unchanged. A reviewed receiver provider must create OHCScanOwnerRuntime only behind proven rootless broker/private-channel provenance, trusted fixed root-owned configuration and actual local BD_ADDR. Mobile supplies no identity/path/service/guard truth. Current rootless launch/FD delivery/admission and native Trial hardware restoration effects lack target proof; production admission stays deny-all. No certificate/profile/Team ID work is required.
- Readiness/UI: use openhc_btstack_scan_inbound actual RFCOMM+SDP acknowledgements, ScanReceiverSession PAIRING_READY and OHCScanOwnerForeground publication for that generation. Replace the installed synthetic provider/timer in a later bounded field-ready build; Stop/background/disconnect/deadline revoke QR/PIN before teardown. Neither PONG nor the new authenticator authorizes initial readiness.
- FE36 transport: theos/btstack-probe.c dispatch_bridge_batch/open_auth_listener and Fe35ControlBridge.listenerReady currently handle the subsequent auth-listener request/registration. The current control worker does not own a separately accepted FE36 CID and feed it to the new bridge, and cleanup unregisters its auth listener. Add one retained auth connection worker/session binding, captured owner generation/one-shot PIN/minimum absolute deadline, CID demultiplexing/MTU-bounded copied ingress, ordered bounded egress, stop FD and typed completion/cleanup. Keep listenerReady exclusively the FE36/auth-listener callback. AUTH_HANDOFF and Nearby/control HANDSHAKE_COMPLETED are not cryptographic success.
- On actual FE36 acceptance call connected; on bytes call receive; execute SEND only to that CID; on success consume the key once into the next trusted transport stage. On Stop/disconnect/deadline terminate both control/auth resources before safe lease recovery. Memory trust is sufficient for a bounded synthetic first pairing; target secure persistence/trusted config must be implemented/reviewed before persistent real pairing/reconnect claims.
- Earliest separately authorized device window first proves launch/peer/FD provenance and independent guard recovery; then actual dual-ready, Honor scan and Nearby/FE36 arrival. Even successful first-pair auth in that window cannot establish full HiCar: WiFi/TCP negotiated session, encrypted connection/key ownership and DMSDP/media are not yet implemented/validated here. Proceed with runnable FE36 I/O/trust join, then dependency-ordered WiFi/TCP and DMSDP/media slices rather than expanding broker demos.

No device/USB/SSH/identity/credentials/radio/power/Showcase/BAA/install/restart/helper/pin action occurred. Theos rootless DEB/Dopamine/GitHub macos-15/ldid -S route is unchanged.

## Exact commit boundary and preservation

Only bridge/build.gradle.kts; new Fe36AuthSessionBridge.kt; the 11 new commonMain hicarauth files; five new commonTest hicarauth files; new scripts/hicar-auth-sim-fixture.m; four existing scripts (check-scan-owner-apple.sh, scan-owner-sim-fixture.m, test-fe35-cli-inbound-simulator.py, test-fe35-cli-smoke-simulator.sh); and this report are eligible. Existing script hunks only add the compile unit, actual handoff invocation, mandatory four-case marker and source manifest. No production native owner/UI/control/backend source changes.

Before edits, 16 pre-existing tracked dirty paths were hashed in Temp/openhc-auth-preservation-20261128.json. All 16 still matched byte-for-byte before handoff updates. HANDOFF-CURRENT.md and docs/RESUME-CHECKPOINT.md will receive prepend-only state updates and remain unstaged, with original bytes retained as suffixes. All other pre-existing dirty paths/untracked work remain outside the index; verify hashes and exact index list before commit. Local logs, reference hash input and receipt are not staged.

## Reference source SHA256 inputs

Paths below are relative to upstream core/auth/src/main/kotlin/io/github/gcbond/openhc/core/auth unless prefixed test/.

| Reference file | SHA256 |
|---|---|
| AccessoryAuthenticator.kt | 22c5c960b3589763c0ad3aafb11edc00560062afeeb7cc97d982cbf266bfd234 |
| HiCarAuthSession.kt | 056a43d7a87f62cf0610a2fc7d7f2c10267368ea71a435616635ce438ec8a67e |
| KotlinAccessoryAuthenticator.kt | c872d045506cec8bfb004bd60d5e8df290013f4f6b1fc62c54708f81a4d7b359 |
| HcError.kt | 5d5c2a75a2d3a0aba427b3e315b970527acef37e0ed969d7749d2d3946ff750d |
| TrustStore.kt | 7c49d6c637c41bda2731ebf1e8c92edf376f160677850ea0b14e85a9ec8a6c6a |
| AuthJsonFramer.kt | 1cfa37e25d81872db6640aec725d7d4a4edb46047a92fb51586ae2f19fb0c215 |
| hichain/HiChainMessages.kt | 6c83e52065e80bf001be69d5a3e0282eb82520b184d5b4fbf7b715df936ca77b |
| hichain/JsonValues.kt | 573aa1a65c8791c46e12054fd7706ccb643437209f3353606c8bc0c35c34e445 |
| hichain/KeyAgreement.kt | ce060c7cbc3cb526b4cf840a805781af75d06cbf1011787f991f63ce0164fa62 |
| test/TestSupport.kt | 03165a09db640a020df6855a852155b4aef23c3e14f59f6c8fbaf2476117291d |
| test/CVectorsTest.kt | a6ed6d157a86ee0a918a834e9f07725fdff43e260cf4c08eac055c0553d1fca2 |
| test/RoundTripTest.kt | 32370913441ae1147d99888039b6f357004597f9b6bd6aa5e394c6d8408d57f8 |
| test/HiCarAuthSessionTest.kt | 2a9b431e5bf0370009cec38e0a575efa1a860abe14d88ddbe1e7107b073b0ac4 |
