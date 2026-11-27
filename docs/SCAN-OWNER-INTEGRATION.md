# Owner/native/common integration — local delivery 2026-11-27

## Coordinator-approved combined CI submission

Follow-up task_2cb1a94ca569 / ctx_9a3b90f1d70e authorizes one bounded commit,
one feature-branch push and one workflow_dispatch after local review. The old
implementation-only prohibition below is historical. Production remains
deny-all and no device acceptance is authorized by the CI result.

Workflow 431974121 (.github/workflows/scan-app-focused.yml) keeps default
validation_scope=app and adds owner. Owner skips the entire legacy framework
reuse job, downloads artifact15145905964 once, uses only the pinned crypto
preparer and builds current arm64/Simulator frameworks and Native tests. Linux
owns the affected socket suites, owner core/crypto-reuse tests and **full JVM**
suite; the Apple entry no longer repeats JVM tests. The aggregator requires
host plus the selected Apple job, and explicitly requires the other scope's
job to be skipped. No helper package is built.

The same single Apple command below remains valid, but now covers Apple/Native
only; pair it with the workflow's Linux/full-JVM job. Existing 3 FE35 + 8 scan
+ 11 owner cases, PONG isolation, CPU QR/system decoder/UI lifecycle and package
audits remain required. SDP cancellation now synchronizes Stop to a host marker
written after the actual SDP request, eliminating the main-queue race without
removing the revoke-before-late-ack assertion. Successful per-case traces and
last-failure Simulator traces are archived; all build/compile stderr is logged.
Artifacts always include available exact SHA/run/scope/reuse metadata, source
manifest, Native/JVM reports, UI evidence and the actual App DEB, even on failure.

This follow-up's local checks: workflow structure/choice/owner-isolation checks
and Bash syntax for all 12 workflow run blocks; shell -n for both edited Apple
entries; Python compilation of the edited fixture harness; repository-config
diff check; 8 actual shell executions of required-job scope/failure propagation;
source-manifest input resolution and diagnostic file whitelist checks. All
passed. A fresh pre-submit snapshot verifies only the four intended existing
code files changed in this follow-up: combined Apple entry, owner fixture,
Simulator Python harness and Simulator shell entry. Owner core, crypto and common inputs were unchanged,
so the previous 551/6/12 execution evidence was not redundantly rerun. Apple
compilation and runtime remain pending until the submitted run produces evidence.

Approved index boundary (28 exact paths, no broad add):

    .github/workflows/scan-app-focused.yml
    bridge/src/commonMain/kotlin/io/github/gcbond/openhc/bridge/ScanReceiverSession.kt
    docs/SCAN-OWNER-INTEGRATION.md
    docs/SCAN-PRODUCTION-INTERFACE-MAP.md
    docs/TECHNICAL-ROUTE-HANDOFF.md
    scripts/check-scan-owner-apple.sh
    scripts/fe35-cli-smoke-runner.m
    scripts/prepare-scan-owner-crypto.py
    scripts/scan-owner-sim-fixture.m
    scripts/scan-owner-tests.c
    scripts/scan-transport-sim-fixture.m
    scripts/scan-ui-tests.m
    scripts/test-fe35-cli-inbound-simulator.py
    scripts/test-fe35-cli-smoke-simulator.sh
    scripts/test-scan-owner-crypto.py
    scripts/test-scan-owner.py
    theos/btstack-probe.c
    theos/fe35-control-bridge.h
    theos/scan-owner/ScanOwner.c
    theos/scan-owner/ScanOwner.h
    theos/scan-owner/ScanOwnerForeground.h
    theos/scan-owner/ScanOwnerForeground.m
    theos/scan-owner/ScanOwnerPeer.c
    theos/scan-owner/ScanOwnerRuntime.h
    theos/scan-owner/ScanOwnerRuntime.m
    theos/scan-ui/Makefile
    theos/scan-ui/ScanDemo.h
    theos/scan-ui/ScanDemo.m

Pre-submit dirty-code snapshot:
C:/Users/quesi/AppData/Local/Temp/openhc-owner-ci-preexisting-20261127.json.
HANDOFF/checkpoint history, installer, Trial/evidence scripts, tools, identity
status notes and Python mock remain outside the index. Installer/helper pins
are unchanged. The final run receipt belongs in the local handoff/checkpoint
and follow-up result; pending is never a successful Apple acceptance.

## Original implementation delivery

Scope: task_a4d42c852831 / ctx_902dd4957055, baseline
72a11ae004e800d30db41550cdbb5d5ac0f5676f. Uncommitted software only;
production admission remains **deny-all**. No CI, commit, device, identity,
credentials, controller, Showcase or BAA action was performed.

## Executable path and boundaries

The new path is foreground Start -> bounded connected descriptor -> serial
ScanOwner state -> lease effects -> real openhc_btstack_scan_inbound -> existing
fe35_scan_binding/common ScanReceiverSession -> framed foreground QR/PIN ->
Stop/background/disconnect/expiry -> native return -> guarded recovery decision.
It is not connected to the installed synthetic demo or a deployed root daemon.

- ScanOwner.c is the production state machine, also executed locally. START,
  STOP and BACKGROUND are the entire request grammar; 12-byte frame storage,
  64 bytes per read, 1-second partial and 2-second idle admission bounds. No
  client paths, identity, commands, role, PID claims or guard truth are accepted.
- ScanOwnerRuntime.m owns one serial executor and a separate native queue. A
  dedicated stop pipe and captured owner/common generations fence callbacks.
  Binding/session/sink and the owner fence survive final callback and worker
  return. Accepted descriptors and stop pipe are close-on-exec. The runtime
  does not terminate a blocked worker or infer exit from CLEANED.
- ScanOwnerForeground.m operates an already-connected dedicated descriptor;
  it does not deploy or discover a root service. Local Stop/resign-active
  immediately invalidates presentation before async cancellation. Replies are
  length-prefixed JSON, <=4096 bytes each / <=8192 queued, generation checked,
  published on main. No automatic reconnect or PONG-based readiness exists.
- RFCOMM_READY and SDP_READY originate from the actual native registration
  acknowledgements. Both and the same common session's PAIRING_READY are needed.
  Common ACCEPTED revokes pairing before one-shot takeAuthHandoffGeneration;
  the handoff preserves the original PIN. This is not completed authentication,
  TrustStore establishment or phone connectivity.
- The simulator fixture uses those production sources, existing C transport,
  ObjC bridge, Kotlin session and CPU QR renderer. Only daemon, OS admission
  evidence and lease/guard effects are synthetic. The encrypted success path
  reuses the existing fragmented FE35 peer. No hardware controller is involved.

## Completion / Trial-shaped recovery contract

The existing native typed result remains
fe35_scan_completion { returned, cleanup_confirmed, status }. CLEANED is only
the final worker-tail callback before return; it is not cleanup success,
process exit, lease release or restoration evidence.

The owner requests the independent guard's restore only after a synchronous
worker return, cleanup_confirmed, independent execution-return knowledge,
understood status (0 success / 1 failure-or-cancel), and before the immutable
deadline. Failure status 1 alone does not prohibit a safely confirmed cleanup;
unknown status does. Restoration itself must still be independently verified.
Unknown return/cleanup/execution, missed bounded acknowledgement or deadline
stops the sole heartbeat and delegates to the guard exactly once; it never
issues concurrent OFF/restore. Recovery verification cannot release a live or
unknown worker. Session/binding/sink and the fence remain until worker return,
execution exit and verified recovery, including late return after delegation.

OHCScanLeaseAdapter mirrors the existing Trial arm/takeover/heartbeat/restore/
delegate responsibilities; it is not another power controller. Guard readiness,
takeover and restore acknowledgements have 3-second bounds, cancellation a
1-second grace, heartbeat one serial writer every 2 seconds, maximum immutable
monotonic deadline 240000 ms. A deployment actor must translate that once to
the existing guard's absolute deadline, never renew it or let UI write it.
No on-device implementation of this lease actor is supplied or enabled.

Existing source being adapted: scripts/btstack-power-trial.py Trial.arm takes
the exclusive active lock and arms independent recovery; Trial.heartbeat is
the only writer; Trial.run/run_inbound_transport handle LeaseUncertain by
stopping heartbeat and delegating, while Trial.restore verifies recovery.
UIKit never imports or executes the host SSH Trial driver.

## Admission: evidence is not authority

ScanOwnerPeer.c samples a fixed root-controlled endpoint and full kernel audit
token: getpeereid plus SOL_LOCAL/LOCAL_PEERTOKEN, server connection nonce,
canonical ancestor ownership/modes and endpoint dev/inode before/after. Every
tick/read compares the complete snapshot, including pidversion, endpoint and
policy epoch. Unsupported APIs fail closed. This Darwin source is not yet
Apple-compiled or target-validated.

Official contract reviewed: Apple XNU xnu-8019.80.24 bsd/sys/un.h,
bsd/kern/uipc_usrreq.c LOCAL_PEERTOKEN case, osfmk/kern/bsd_kern.c.
LOCAL_PEERTOKEN queries the socket's last_pid task; it is not immutable
per-message XPC credentialing and does not establish initial exec provenance.
The fixed proposed endpoint is /var/jb/var/run/openhc-owner/control.sock.
No listener/plist is installed by this change. Same mobile UID, process name,
client role, token availability, guard marker or PONG grants no authority.

Production admit() unconditionally returns false. Test admission/evidence
injection exists only under OPENHC_SCAN_OWNER_TEST at compile time, with no
environment or wire activation switch. It is not linked into a shipped helper.
The runtime must be a singleton inside the exclusive root lease actor; one
object's fence is not a substitute for the existing process-wide active lock.

Exact activation blockers:

1. The restricted owner caller policy is not deployed. Need an explicitly
   reviewed root-controlled launch/connection capability and lifecycle policy
   appropriate to Dopamine, with evidence freshness, exec/PID-reuse and endpoint
   replacement tests. A root-brokered private channel is a possible architecture,
   not an implemented authorization claim. Do not invent trusted executable
   hashes, entitlements, signing identities or grant mobile root.
2. No target-native adapter yet owns Trial's exclusive lock, private run state,
   independent guard, sole heartbeat and independently verified recovery. The
   existing CLI marker probe alone cannot supply that authority.
3. New ObjC/Darwin collector and integrated simulator execution remain unverified.

The established deployment remains rootless Theos DEB / Dopamine / macOS CI /
ldid -S. No Apple Developer certificate, profile, Team ID or App Store route is
required or introduced by this work. Threat scope does not claim protection
against an attacker already controlling root.

## Actual local evidence

Windows, existing Zig and JDK17; no new environment installed:

| Command / check | Actual result |
| --- | --- |
| python scripts/test-scan-owner.py | Production deny-all binary ran; test-adapter binary ran, 551 assertions |
| python scripts/test-scan-owner-crypto.py | 6 synthetic tests passed |
| Python py_compile on new scripts and modified simulator harness | Passed |
| Git Bash -n on combined Apple and modified simulator entries | Passed; syntax only |
| Zig strict C11/Werror Linux native probe + stub link, aarch64 native/owner compilation | Passed cross-compilation only; no Linux execution |
| JDK17 cached offline :bridge:jvmTest --tests '*ScanReceiverSessionTest' | Actual JVM execution: 12 tests, 0 failures/errors/skips |
| git diff --check | Passed |

An exploratory check overriding core.autocrlf=false failed by treating existing
Windows CRLF as trailing whitespace across prior dirty files. The repository's
normal configured git diff --check was then rerun successfully; no global line
ending conversion or unrelated whitespace edit was made.

Owner tests cover unauthorized same UID, forged role/guard/path/PONG, token/PID/
pidversion/nonce/endpoint/policy change, competing connection/reconnect, bounded
fragmented framing, guard failure, stale callbacks/generation, dual readiness,
same-session one-shot handoff, CLEAR-before-cancel, CLEANED with cleanup failure,
unknown status/exit, late return, exactly-once delegation, recovery fence,
immutable deadline and sole heartbeat. These are production C state tests with
test-only evidence/effect injection, not OS-authentication runtime tests.

The prepared 11 integrated Apple cases are success, ready_stop, background,
disconnect, rfcomm_failure, sdp_failure, stop_rfcomm_wait, stop_sdp_wait,
deadline_wait, ready_timeout, cleanup_failure. Original 3 FE35, 8 native scan
and CPU QR/system-decoder/lifecycle assertions are retained. The new integrated
cases have **not** been Apple-compiled/run locally; no green result is claimed.

## One combined Apple entry, prepared only

With the existing macOS toolchain (Xcode, JDK17, Gradle8.13, Theos, ldid, dpkg),
existing THEOS and a private RUNNER_TEMP:

    bash scripts/check-scan-owner-apple.sh /absolute/path/to/pinned-source.zip

Only crypto archives can be reused from run45875853812/artifact15145905964:
source 6d1731813d95e8e60f7628a7a06f95848668c6f2,
ZIP SHA256 aef52fb49f3d3737e190703b195a9ce5b39ec0ca7dbb2a898d1077a4fb86a60c.
The actual local ZIP at C:/Users/quesi/AppData/Local/Temp/openhc-run-45875853812/apple-artifact.zip
was verified into a private temporary destination. Crypto source changes or
untracked crypto inputs reject reuse. No old framework/App/helper is restored.

Verified archive hashes:

- iosArm64/libcrypto.a: 104872be4dc8240c73f825e401a1799c6b03fcae49932b29cdb43781b823e3c8
- iosArm64/libopenhc_crypto.a: 7d4af63fdba2cbacad6759038a244d5e406643670cfea851179f4de1a5fc1277
- iosSimulatorArm64/libcrypto.a: 985527ef672637e8b865cbc5ddd6ecb5711af5fe65fb8bc5fb84f7dfd5a3dfac
- iosSimulatorArm64/libopenhc_crypto.a: e62d3d9e72700f014c00f0e0a48bd200c7af6ed7867c2c5d107e0ca7af2a8ed9

Gradle builds current device/Simulator frameworks and current Native tests;
full JVM runs once in the workflow's Linux job (original standalone preparation
also ran it on Apple, removed in the approved CI follow-up).
its input tracking may cache only matching inputs. Both deployment ObjC/C SDK
branches, Darwin host owner and existing affected C suites then compile/run,
followed by all FE35/owner cases and UIKit/CPU QR/real App DEB checks. Makefile
receives the fresh device framework directory. A targeted input hash manifest
is compared before/after execution. Missing validation fails the set -euo
pipefail entry. It is focused validation, not complete S0. No helper build.

## Exact task file boundary

New code: theos/scan-owner/{ScanOwner.h,ScanOwner.c,ScanOwnerPeer.c,
ScanOwnerRuntime.h,ScanOwnerRuntime.m,ScanOwnerForeground.h,ScanOwnerForeground.m}.
New test/validation: scripts/{scan-owner-tests.c,test-scan-owner.py,
scan-owner-sim-fixture.m,prepare-scan-owner-crypto.py,test-scan-owner-crypto.py,
check-scan-owner-apple.sh}.
Modified for integration: scripts/fe35-cli-smoke-runner.m,
scripts/test-fe35-cli-smoke-simulator.sh,
scripts/test-fe35-cli-inbound-simulator.py, theos/scan-ui/Makefile.
Documentation: this report, HANDOFF-CURRENT.md, docs/RESUME-CHECKPOINT.md,
docs/SCAN-PRODUCTION-INTERFACE-MAP.md (history retained).

Prior dirty-code status/hashes were captured before editing in
C:/Users/quesi/AppData/Local/Temp/openhc-owner-preexisting-20261127.json.
Pre-existing typed completion, synthetic isolation, installer/crash diagnostics
and unrelated Trial/evidence edits were preserved. No App/helper pin changed.
Healthy helper remains 34a3c3ca5d85d4e3863ff7631acec6dce8c636423be68b49edfe356810a6fc55.
User-confirmed synthetic QR and ~60-second expiry are historical field evidence;
old/temp CoreImage crash attribution and stable current-build acceptance remain
unresolved. No real phone connection or full authentication is claimed.
