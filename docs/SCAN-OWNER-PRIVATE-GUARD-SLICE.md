# Native private channel / independent guard software slice — 2026-11-27

Task task_d131b12e8d15 / ctx_e0860070065d, original run_25334cb0a007.
Baseline bb7b1d20efcb2f640344c01a4033ef46da673fd6 on stage0-auth-validation.
This advances the dependency for real FE35 startup. It is not real HiCar, a
deployment authorization, a phone connection, or a device recovery acceptance.

## Runnable boundary and deliberate production denial

- `ScanLeaseProtocol.{h,c}`: fixed 40-byte, versioned, bounded internal
  ARM/TAKEOVER/BEAT/COMPLETE/RESTORE/DELEGATE frames. Server fixes one generation,
  monotonic sequence and immutable absolute deadline <=240000ms. No wire string,
  path, executable, role, service name, identity, guard marker or policy option.
- `ScanLeaseChannel.{h,c}`: bounded fragmented I/O on a connected descriptor,
  CLOEXEC/nonblocking ownership, generation/sequence/deadline reply fencing.
  One serialized adapter queue is the heartbeat writer. No retry/reconnect can
  restart or extend the lease; errors poison and close that channel.
- `ScanGuardProcess.c`: independent native executable. In the explicitly
  compiled software fixture it validates private directory/socket descriptors,
  holds an exclusive flock plus unresolved fence, and acknowledges ARM only
  after these gates. Only its injected **inert** recovery implementation writes
  `restore.once` with O_EXCL and removes the fence. There are no hardware or
  launchctl commands. Deadline/heartbeat/unknown state while execution remains
  live retains the fence; it never authorizes concurrent OFF/restore.
- `ScanProcessLeaseAdapter.{h,m}` implements `OHCScanLeaseAdapter` on its own I/O
  queue, outside owner/common and main executors. Runtime records the typed
  worker return before a queued restore request. CLEANED does not call this
  hook. Lost guard I/O asynchronously revokes/cancels then delegates and keeps
  the fence; callbacks do not re-enter the core from an effect. Session/binding/
  sink still outlive the actual worker return.
- `ScanBrokerProcess.c` and `+productionAdapter` unconditionally refuse
  deployment (exit78 / nil). `ohc_lease_production_available()` is always false;
  production `ohc_lease_adopt()` always refuses. These are separate from the
  existing owner admission deny-all, which is unchanged. Runtime arguments,
  same mobile UID, root/name/PID claims, PONG, markers or inherited sockets
  cannot enable any of these branches. There is no public listening endpoint.

The guard's executable loop uses the shared protocol and actual POSIX process/
file/IPC code, but its runnable bootstrap and inert service effects are included
only by OPENHC_SCAN_OWNER_PROCESS_TEST. The production package is intentionally
inert, **not** a deployed native Trial actor. No new code implements a second
power controller or invokes the host SSH Trial.

## Concrete launch/private-descriptor proposal and missing target proof

The proposed deployment boundary is a root-controlled launcher, not a
mobile-accessible root service. That launcher alone would create an unnamed
socketpair and fixed private owner-domain directory capability, then launch
exactly one owner and one independent guard. Guard gets only fd3 (private channel)
and fd4 (directory); all other nonstandard descriptors are closed and standard
streams carry no authority. Both become CLOEXEC immediately after bootstrap.
The test broker also redirects the guard's standard streams to /dev/null,
starts a separate session, and proves an intentionally inherited unrelated pipe
reaches EOF while the guard is alive. No secret token is placed in env/argv.

This is a proposal with an executable **test broker**, not a claimed Dopamine
launch primitive. The production launcher does not yet exist. Missing evidence:

1. Which target-supported root-controlled launch/connection mechanism can bind
   the specific installed receiver instance and transfer the private descriptor
   into that non-root UIKit process, without a public mobile-UID grant or
   arbitrary launch request. No Apple certificate/Team ID/profile is required or
   proposed. Rootless Theos/ldid -S remains the route.
2. Verified descriptor provenance, one-shot handoff, parent/endpoint freshness,
   process incarnation across exec/PID reuse, and closure on foreground process
   death/connection replacement. A socketpair alone is insufficient. Current
   LOCAL_PEERTOKEN last_pid evidence is not this authorization.
3. A fixed root-owned owner-domain directory under the rootless runtime tree,
   with one global lock/fence across all attempts (not one independently
   lockable directory chosen by each client). Test cases use a private temporary
   owner domain and competing attempts share that exact directory capability.
4. Target-native baseline preflight, guard registration/READY, bounded takeover,
   verified restore and unresolved-fence recovery implementing existing Trial
   semantics. No paths, marker truth or restore commands come from UIKit.
   A guard crash leaves a persistent unresolved fence; a new owner must not
   remove it just because flock was released. Filesystem power-loss durability,
   target launchd persistence and service recovery are not established here.

Test guard independently observes its **kernel parent relationship** changing,
not a supplied PID, a kill(pid,0) probe or EOF alone. This avoids interpreting
PID reuse or exec-induced descriptor closure as proven exit. If only the channel
is lost while its parent is alive, it delegates once and waits without restoring;
at an unresolved absolute deadline it exits with the fence retained. This
relationship is proven only for the native host owner/guard fixture, not for
UIKit/rootless launch on the target. The Simulator relay's guard parent is the
host test broker: its exit proves **host broker** exit, not UIKit process death.

## Actual process and integrated software acceptance

`scripts/test-scan-owner-process.py` builds strict C11/Wall/Wextra/Werror.
Windows actually executes the portable protocol tests (308 assertions); it
cross-compiles four Linux ELF programs and explicitly reports POSIX runtime
pending. It does not execute Linux, GCC or an Apple SDK. No environment install.
On Linux/macOS the same entry really executes:

- deployment denial despite forged argv/environment/same-account process;
- production owner core -> real private channel -> guard READY -> inert takeover
  -> worker boundary -> Stop or disconnect -> CLEAR before cancel -> typed
  completion -> independent inert restore once;
- actual owner process exit with surviving detached guard and independent
  parent-exit observation; missing READY never starts owner work;
- killed guard leaves a fence and blocks a new owner after flock disappears;
- lost heartbeat while owner lives delegates without restore;
- cleanup unknown and execution unknown retain the fence while owner lives;
  late completion cannot revoke delegation or cause a second restoration;
- CLEANED alone cannot mark worker return, verified recovery or release;
- competing owner, stale generation, forged role/flags/opcode/path/READY/PONG,
  fragmented frame timeout, replayed heartbeat sequence, immutable budget and
  real monotonic expiry; no unknown live worker is restored concurrently;
- inherited unrelated fd closure and invalid bootstrap descriptor rejection.

The native owner fixture injects admission/peer evidence, service effects and
worker completion. Its owner state machine and guard/process/IPC/files are real.
The existing Simulator fixture additionally uses the new ObjC adapter through
an explicitly **test-only loopback relay**, joining actual foreground -> owner
runtime -> native FE35 C -> Kotlin common -> typed return to the actual host
guard process for ready_stop, disconnect and cleanup_failure. Synthetic daemon,
root/admission provenance and hardware effects remain injected. The relay port
file exists only in the fixture; no production factory reads it. Original
551+122 owner assertions, 3 FE35 + 8 native + 11 owner cases, same-PIN handoff,
70 UI checks / 3 system QR decoders and actual App package gates remain intact.

Evidence files: native broker/guard `events`, owner.log and broker.log under
focused-results/owner-process (Linux) and artifacts/scan-owner/process (macOS).
Simulator source/event/status evidence remains under artifacts/scan-owner.
All are archived on failure; exact SHA/run/scope/source manifest is retained.
No QR/PIN/key/identity is added to diagnostic logs.

## Inert packaging and combined command

`theos/scan-owner/Makefile` builds two arm64 rootless tools with ordinary Theos
and ldid -S. Package `com.gcbond.openhc-scan-owner-inert` contains only the two
disabled tools under /var/jb/usr/libexec/openhc-owner-inert, mode0755, root0:0.
There is no setuid bit, launch plist, postinst, enabled job, configuration,
installer hook or healthy PING-helper change. `check-scan-owner-package.py`
audits xz/layout/owners/modes/no links/no maintenance scripts/arm64 without
extracting it; combined Apple entry additionally checks ldid/lipo/otool.
Buildable does not mean deployable. Nothing is installed in this task.

Local commands:

```text
python scripts/test-scan-owner-process.py --output artifacts/scan-owner/process-local
python scripts/test-scan-owner.py
python scripts/test-scan-owner-crypto.py
```

Combined GitHub macOS compilation/simulator tests (one owner dispatch):

```text
bash scripts/check-scan-owner-apple.sh /absolute/pinned-source.zip
```

The combined entry uses only verified crypto from artifact15145905964, ZIP
SHA256 aef52fb49f3d3737e190703b195a9ce5b39ec0ca7dbb2a898d1077a4fb86a60c;
never restores old frameworks. Gradle uses current input-aware framework/Native
tasks, Linux owns full JVM checks, both SDKs compile deployment branches without
test admission macros, macOS executes actual native process cases and Simulator
integration, retained UI/App package gates run, then the inert package is built.
No healthy helper or legacy stage0 build. Required failure propagation remains.

## Exact next real HiCar joins and shortest evidence gates

1. **Receiver production Start/config/launch:** installed ScanDemo.m still calls
   `+[OHCScanDemoProvider syntheticDemoProvider]`; its automaticReady timer
   remains synthetic and is not changed or redeployed here. A separate real
   provider must use only the verified root launcher/private channel, never
   upgrade this timer or PONG. Root owner constructs OHCScanOwnerRuntime with
   `ScanReceiverConfig` and `fe35_bridge_input` from a fixed, root-owned validated
   configuration provider and the actual local BD_ADDR observed under its lease.
   Mobile supplies neither identity contents nor an address/path. That trusted
   configuration/BD_ADDR provider and launcher-to-UIKit descriptor transfer are
   not implemented or validated here; no real identity was read.
2. **Actual initial FE35 ready/presentation:** `launchWorker` retains session/
   binding/sink and invokes `openhc_btstack_scan_inbound`. Only actual same-
   generation RFCOMM_READY + SDP_READY feed common `ScanReceiverSession` and
   PAIRING_READY; owner generation fencing forwards QR/PIN to
   OHCScanOwnerForeground main-thread presentation. A production provider must
   wire those publications to the receiver UI and invalidate on CLEAR, Stop,
   background, disconnect and deadline. The code exists at this boundary, but
   the installed synthetic provider is not connected to it.
3. **Scan/auth:** native ACCEPTED revokes pairing; common
   `takeAuthHandoffGeneration` provides the one-shot same PIN to the trusted
   runtime sink. Runtime currently counts/notifies AUTH_HANDOFF; it does not
   construct a complete authentication session from that PIN. Existing
   `fe35_bridge_start/feed/listener_ready` -> Fe35ControlBridge ->
   Fe35NearbyControlSession handles bounded Nearby/control and later auth-
   listener requests. `listenerReady` here is FE36/auth, NOT initial FE35 ready.
   AuthProbe/AuthVectors/SpekeMathProbe/AuthBackend are arithmetic/backend
   probes, not a completed real phone authentication/TrustStore port. Missing
   entrypoints are the same-PIN auth-session coordinator, target FE36 listener
   and payload I/O, peer verification/TrustStore persistence, and their bounded
   cancellation/result wiring. Notification and vectors are not authentication.
4. After this IPC/guard software result, next code milestone is the restricted
   production provider plus fixed configuration/BD_ADDR and target-native Trial
   effect adapters, still fail-closed behind unproven target launch support. A
   separately authorized device window first verifies rootless launch/peer/fd
   provenance and independent guard lifetime/unknown recovery, then actual dual
   ready -> Honor HiCar scan -> Nearby request arrival. That window alone cannot
   establish full HiCar. At a blocked platform join, continue offline with the
   same-PIN FE36 authentication coordinator/protocol port, not more demo layers.
   Subsequent dependency-ordered runnable slices must implement/validate real
   authentication+TrustStore/FE36 -> WiFi/TCP session transport -> DMSDP/media/
   control. These are not proven ported by scan, crypto, Simulator or package CI.

Final acceptance remains actual HiCar on the target Dopamine iPad with the Honor
phone. No official Apple signing migration, device/USB/SSH/identity/radio/power/
Showcase/BAA operation, install/restart or pin change occurs here.

## Local validation and submission receipt

Actual Windows / existing Zig results:

- `test-scan-owner-process.py`: **308** portable protocol assertions executed;
  strict cross-compilation of guard-deny, broker-deny, guard-test and broker-test
  to Linux ELF passed. POSIX process execution is explicitly pending. WSL was
  queried read-only and is not installed; no environment was installed.
- `test-scan-owner.py`: production deny-all, original **551** and terminal
  **122** assertions actually passed on Windows/Zig.
- `test-scan-owner-crypto.py`: **6** synthetic crypto-only archive tests passed;
  their generated ZIP digest is not the pinned production source ZIP digest.
- Modified Python AST, **12** workflow shell blocks, **2** affected shell
  scripts, production macro isolation/factory-denial checks passed. Synthetic
  inert-package audit had **8** positive/negative cases (layout, maintenance
  script, symlink, owner, setuid/mode, CPU and compression). An initial source
  audit caught a malformed Python byte literal in the new package auditor;
  it was corrected and the affected source/archive checks passed on rerun.
- No GCC, Apple SDK, POSIX guard-process runtime, Simulator or real package
  execution is claimed locally. Baseline run46014840762 belongs to bb7b1d20,
  not this new source. Current source needs the single focused owner run.

Exact bounded staging set (24 paths):

```text
.github/workflows/scan-app-focused.yml
theos/scan-owner/.gitignore
theos/scan-owner/Makefile
theos/scan-owner/control
theos/scan-owner/ScanOwnerRuntime.h
theos/scan-owner/ScanOwnerRuntime.m
theos/scan-owner/ScanLeaseAdapter.h
theos/scan-owner/ScanLeaseProtocol.h
theos/scan-owner/ScanLeaseProtocol.c
theos/scan-owner/ScanLeaseChannel.h
theos/scan-owner/ScanLeaseChannel.c
theos/scan-owner/ScanBrokerProcess.c
theos/scan-owner/ScanGuardProcess.c
theos/scan-owner/ScanProcessLeaseAdapter.h
theos/scan-owner/ScanProcessLeaseAdapter.m
scripts/scan-owner-process-fixture.c
scripts/scan-owner-process-tests.c
scripts/test-scan-owner-process.py
scripts/check-scan-owner-package.py
scripts/scan-owner-sim-fixture.m
scripts/test-fe35-cli-inbound-simulator.py
scripts/test-fe35-cli-smoke-simulator.sh
scripts/check-scan-owner-apple.sh
docs/SCAN-OWNER-PRIVATE-GUARD-SLICE.md
```

Runtime/header edits are only the extracted lease protocol and typed-return /
unavailable hooks. Existing harness edits add process lease cases, not weaken
old assertions. Workflow adds Linux process evidence; combined entry adds real
macOS process checks, both SDK compile inputs and inert packaging; its manifest
excludes generated .theos/packages/build trees. All other paths are new native
components, their focused tests or this report.

Pre-existing tracked dirty files were snapshotted before edits in
`C:/Users/quesi/AppData/Local/Temp/openhc-process-slice-preservation-20261127.json`.
Twelve of fourteen hashes still match exactly; HANDOFF/checkpoint were changed
concurrently by the coordinator's explicit final-goal update before this worker
edited either. Their latest bytes are captured before this task's prepend and
retained as an exact tail; both remain unstaged. Concurrent TECHNICAL-ROUTE-HANDOFF
edits are also preserved and unstaged. No installer/helper pin, Trial/evidence/
mock/tools or identity-related file is included.

Commit/push and the single pending run receipt are appended locally after the
authorized submission; a queued/in-progress run means WAITING_CI, not acceptance.
