# FE36 accepted CID → same-PIN authenticator → trusted key interface

Task task_9f2311e79281 / ctx_6784337e4000, original run run_25334cb0a007.
Baseline: 8c463b50028603e7dfcf5c4b3c8f43e70a5e94cb, audited run46035355129.
This change is a software transport integration; it is not phone/device evidence.
Current new GitHub macOS compilation/simulator results are pending submission.

## Actual code path and authority

1. A future trusted owner explicitly calls
   OHCScanOwnerRuntime.configureAuthentication:trust:keySink: before Start.
   Missing/partial configuration rejects configuration. The existing initializer
   and openhc_btstack_scan_inbound remain explicitly FE35-only: their protocol
   status cannot create an authentication/key callback. No default identity,
   config loader, credential file or client-configurable authentication switch exists.
2. Actual FE35 incoming/open acknowledgement goes through scan notify ACCEPTED.
   Owner revocation/CLEAR precedes the actual common takeAuthHandoff call.
   consume: forwards this one-shot original PIN to OHCFe36AuthTransport.handoff.
   It captures min(owner.deadline, common.deadlineMillis), using the same
   CLOCK_MONOTONIC time domain. The previous expiry is never reset to 240 seconds.
3. The runtime retains this adapter through synchronous native return and calls
   openhc_btstack_scan_auth_inbound. The original four-field fe35_scan_transport
   ABI and legacy call sites remain unchanged. fe36_auth_transport is a separate
   borrowed typed vtable, not a public socket grammar or authorization mechanism.
4. btstack-probe.c retains the control incoming peer bytes privately and verifies
   the corresponding OPEN peer, listener, CID, incoming flag and MTU. FE36 needs
   a separate incoming event on the registered auth channel and a new nonzero CID.
   OPEN must match its CID, listener, peer bytes and control ACL handle, with
   negotiated MTU in 1..512 (the actual local registration limit).
   These are BTstack daemon event associations, not caller/app authorization.
   The existing strict/reference OPEN-length profiles remain supported.
5. Exactly one auth incarnation (1, local to this invocation) is bound to the
   captured common/owner generation. A reused daemon CID is not an incarnation.
   Duplicate accepts/opens, another peer/listener/CID, unowned input or lifecycle
   events cannot feed or promote a key. Unknown pending connections/stale opens
   retain cleanup uncertainty; known resource removal is not remote absence proof.
6. auth_stream demultiplexes control bytes back to the real Fe35ControlBridge and
   only owned FE36 bytes to the real exported Fe36AuthSessionBridge. Incoming
   BTstack packets are <=512 bytes and must fit negotiated MTU; the adapter copies
   <=4096-byte chunks into the existing arbitrary-fragment JSON framer. Existing
   65536 total-input and bridge action/output bounds remain. No RFCOMM-packet=JSON
   assumption or new HiCar wire envelope was introduced.
7. step computes Native actions while serialized, unlocks, then performs SEND in
   order. auth_send fully writes each bounded packet on the auth CID, splitting
   by actual MTU, through existing bounded/cancellable daemon writes. SEND failure
   cancels the adapter; AUTHENTICATED remains only a candidate until all preceding
   SEND effects have succeeded. Native takeSessionKey is not a diagnostic event.
8. After verified crypto, this bounded worker intentionally closes both owned CIDs
   and unregisters both SDP/RFCOMM listeners using existing processing barriers.
   Only confirmed cleanup permits commit. The owner serial executor drains queued
   Stop/background/EOF, checks generation/state/deadline and the common clock,
   then takes the key once and calls the trusted typed sink with owner generation,
   common generation and incarnation. Key bytes are borrowed for callback duration
   and the native copy is wiped. No key appears in stdout, diagnostics or events.
   Final STOP/CLEANED and returned/cleanup_confirmed retain separate meanings.

## Lifecycle policy and deliberate boundary

Read-only reference HEAD 8132399bea6aa86d68da6d3e1d9e3e001c0a7643:
core/session/.../WirelessReceiverSession.kt onAccepted/onData/onClosed.
Its control listener remains reserved until auth accept; onData demultiplexes
control versus auth; control closure before phoneOnWifi is fatal even while auth
is in progress. Auth closure before verified success is fatal. This integration
follows that failure policy: FE35 close while authenticating is not tolerated as
an expected successful Nearby disconnect. FE35 HANDSHAKE_COMPLETED and
listenerReady still mean only the auth-listener/control response, never auth success.

This bounded scan worker has no WiFi stage. After verified authentication it
enters intentional teardown before exporting its result; this is not the reference's
ongoing post-auth network session. Unlike reference removal on auth acceptance,
the two service registrations remain reserved until this bounded teardown, while
every second connection is rejected and retains uncertainty. No additional
connection is accepted, nor can a channel be recycled during auth. Target daemon
pending-connection/removal behavior still needs validation before activation.

The key callback is not a radio grant or lease transfer. It must not start WiFi or
media: current owner completion still delegates/restores through its existing guard
contract. The next real network slice needs an explicit trusted session/lease
handoff and the control connection retained into WiFi, rather than pretending
this worker's already closed CIDs are a live HiCar session.

Stop, background, endpoint EOF, original common/owner deadline, clock reversal,
socket failure and unknown cleanup revoke a pending candidate. Ordinary accepted
CLEAR is not terminal cancellation. Failure paths revoke before teardown; success
was already CLEARed at control acceptance and keeps cancellation polling active
during cleanup. Unexpected lifecycle/data during processing barriers fails closed
instead of silently swallowing it and promoting a candidate.

## Runnable acceptance and evidence boundaries

scripts/fe36-cid-sim-fixture.m uses the actual production owner, C transport,
ObjC adapter and Kotlin/Native authenticator. The existing fake daemon harness
performs real FE35 Nearby/control framing, real FE36 incoming/open acknowledgements,
and relays raw auth bytes to a separately coded ObjC upstream-derived TestPhone.
The phone uses actual backend PAKE, AES-GCM, signatures and key derivation; it
verifies the server response signature and compares the derived key privately to
the actual trusted callback. It is not an independent Huawei/Honor implementation.
The loopback proxy's four-byte length is exclusively test plumbing, never FE36.

Twenty new transport scenarios are required by the existing combined entry:
success, wrong_pin, forged_signature, wrong_peer, wrong_open_peer, wrong_cid,
control_cid_reuse, extra_connection, malformed_open, wrong_data_cid, reopened_cid,
wrong_listener, control_close, auth_disconnect, stop, background, deadline,
send_failure, cleanup_failure, pending_stop. Requests and replies cross many
JSON boundaries at negotiated MTU 37. A separate exact adapter SEND-rejection
check injects a failed send callback and verifies cancellation/no key; the socket
reset case exercises real C socket/cleanup failure without assuming whether a
particular OS reports the reset in send or receive. Cleanup failure and pending
Stop occur after a full valid crypto exchange and must suppress the key callback.
All negative cases require no key. Wrong PIN/forged identity cannot commit trust.

New markers: FE36_CID_TRANSPORT_AUTH_CASES_OK=20,
FE36_ADAPTER_INJECTED_SEND_FAILURE_OK, and per-case CID_COMPLETION.
Only fixtures record the static TRUSTED_KEY_CALLBACK occurrence, never its data.
Per-case static traces/status/result are archived even on failure. Existing
3 FE35 + 8 native scan + 11 owner + 3 process Simulator cases and four standalone
ObjC auth socket cases remain; existing owner551+122/protocol308/process32,
full JVM/Native, UI/system decoder and actual App/inert archive gates remain required.

Local Windows execution, 2026-11-28:

- JDK17/Gradle8.13 offline selected Fe36AuthBridgeTest and HiCarAuthSessionTest:
  XML 28 tests, zero failures/errors/skips, BUILD SUCCESSFUL.
- python scripts/test-scan-owner.py: production deny-all, 551 + 122 passed using
  installed Zig on Windows (not GCC).
- python scripts/test-scan-owner-crypto.py: six tests passed.
- Installed Zig strict C11 -Wall -Wextra -Werror compiled btstack-probe.c for
  aarch64-linux-musl with production and Simulator-test macros. These are objects,
  not executable Linux/macOS/iOS runtime passes.
- Python compile checks and bash -n for both affected shell entries passed;
  git diff --check passed. Windows has no Apple SDK; new ObjC/SDK/Simulator runtime
  claims must wait for the single current-SHA GitHub macOS compilation/simulator run.

Local JVM log: Temp/openhc-fe36-cid-jvm.log. Local preservation snapshot:
Temp/openhc-fe36-cid-preservation-20261128.json, including all fourteen unrelated
dirty file digests and byte backups for both mixed-history suffixes. Both histories
are prepend-only and unstaged. Submission SHA/run receipt is recorded in the local
delivery report and newest handoff, not fabricated into this pre-commit document.

## Precisely bounded files and reuse

- theos/btstack-probe.c: optional auth event pump, peer/CID/MTU/lifetime fences,
  dual-CID cleanup and deferred typed result.
- theos/fe35-control-bridge.h, theos/Fe36AuthTransport.h,
  theos/fe35-control-bridge.m: separate C vtable and actual serialized ObjC binding.
- theos/scan-owner/ScanOwnerRuntime.h and .m: trusted configuration, original
  handoff/minimum-deadline capture, cancellation and owner-fenced key sink.
- scripts/hicar-auth-sim-fixture.m: reuse existing real TestPhone algorithm via
  test-only proxy; retain all four previous direct socket cases and assertions.
- scripts/fe36-cid-sim-fixture.m and scripts/test-fe36-cid-simulator.py:
  actual-code integrated auth/negative/cleanup fixtures.
- scripts/fe35-cli-smoke-runner.m, scripts/test-fe35-cli-inbound-simulator.py,
  scripts/test-fe35-cli-smoke-simulator.sh: narrow routing/linkage/diagnostic capture.
- scripts/check-scan-owner-apple.sh: manifest additions and both-SDK strict
  production compilation of the modified ObjC bridge, with no test admission macro.
- This report only. Existing workflow/required aggregator are unchanged.

No native/crypto or scripts/build-crypto-backend.sh input changed relative to
the pinned crypto source 6d1731813d95e8e60f7628a7a06f95848668c6f2. Crypto-only
ZIP validation remains unchanged; no old frameworks are restored. Current source
frameworks/full JVM/Native/package checks retain input-aware Gradle behavior.
No healthy helper build or installer/pin change is included.

## Shortest remaining real joins

1. Replace the deployed syntheticDemoProvider only after trusted native receiver
   launch/FD provenance and native Trial guard recovery have target evidence.
   A root-owned fixed configuration must supply the true in-memory FE35/auth
   config and secure TrustStore adapter; actual local BD_ADDR comes from the
   existing guarded native query, not mobile identity/path claims. None is loaded
   or read in this task. Rootless launch/channel provenance remains unsupported.
2. Connect actual RFCOMM+SDP acknowledgements to PAIRING_READY and foreground QR/PIN,
   with Stop/background/expiry revocation. This runtime now joins real accepted
   FE36 bytes to the same-PIN authenticator, but no installed provider activates it.
   Native target launch policy and native Trial effects remain disabled/deny-all.
3. In a separately authorized device window, first verify launch/peer provenance,
   independent guard lifetime/restoration and cleanup; then actual dual-ready,
   same-session visible QR, Honor HiCar scan/Nearby/control and real FE36 crypto.
   Software TestPhone success cannot establish vendor interoperability.
4. Implement platform secure trust persistence and a post-auth session/lease
   handoff retaining required control lifetime; port/validate reference WiFi/TCP
   coordination and then DMSDP/media in runnable dependency order. The current
   callback deliberately provides no network/media success stub. A platform-only
   or request-arrival window cannot establish full HiCar.

Dopamine rootless/Theos DEB, GitHub macos-15, TARGET_CODESIGN=ldid/-S are unchanged.
No device, identity/credential/assets, Bluetooth/WiFi/power, installer/helper or
official Apple signing operation was performed or enabled.
