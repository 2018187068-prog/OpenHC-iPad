# Local correction prepared for consolidated submission

Status: **CONSOLIDATED_CORRECTION_READY_FOR_SUBMISSION**, 2026-11-28, base
25bd5cf1d28bf195db978e356d1016ebf94228b4, branch stage0-auth-validation.
The local preparation phase performed no commit, push or CI action. Coordinator
message msg_324c7dcab825 subsequently supplied the final macOS failure and lifted
the hold for this combined correction: one commit, push and focused owner run.
The exact new SHA/initial receipt belongs in the local delivery record and
unstaged history update; this document is committed with the corrected sources.

## Existing evidence and bounded diagnosis

Coordinator-supplied run46046227986 host evidence: artifact15222101961,
SHA256 7f86c310c918ecd8c8e2d6bef6044275fe5b0dabc3613bcbf5810fc7cb56d245;
JVM92 passed with zero failures/errors/skips. The process suite failed at
missing_ready, test-scan-owner-process.py:240, fence-absence assertion.
Archive events contain the prior inert effect and restore.once; fence was
absent at artifact collection. This does not establish its exact state at the
failure instant. No artifact was downloaded again and no CI was queried.

The source orders INERT_RESTORE_ONCE before unlinkat(fence) and fsync(dir).
An observer waiting on that earlier record can run before those later calls.
This is a concrete observation-order defect; the supplied evidence supports
this race, rather than proving target recovery safe or an exact syscall error.

Coordinator final audit: run46046227986 host/owner-apple/required all FAILURE;
required ended 2026-11-27T18:06:59Z (2026-11-28 02:06:59 Shanghai).
Owner artifact15223431120 SHA256
5200d6a6d6d452a59ab69389b4a5f07aceb93c0792b757767f8e123b269c7c49.
Native90 also passed, but macOS compilation failed at Fe36AuthTransport.h:10:90
and ScanOwnerRuntime.h:8:75 with Werror/nullability-completeness-on-arrays.
The new CID20 Simulator cases, UI and packages were not reached. These failures
are not superseded by JVM/Native successes. Existing local failure log was read;
no CI query or repeat artifact fetch was needed.

## Exact patch and semantics

1. theos/scan-owner/ScanGuardProcess.c: retain restore.once exclusive creation
   and the original INERT_RESTORE_ONCE effect record. Append
   INERT_RECOVERY_COMPLETED only after successful fence unlink and directory
   fsync; only then set restored and permit RESTORE OK. All implementation and
   new fault arguments remain inside OPENHC_SCAN_OWNER_PROCESS_TEST; deployment
   still unconditionally denies. Existing lease/protocol semantics unchanged.
2. scripts/test-scan-owner-process.py: all seven former effect-marker waits
   use wait_recovery, which checks exactly one effect, exactly one final
   record, effect-before-final ordering and fence absence. The two reply-based
   success observers also use this helper. Effect-count assertions remain.
   Add two actual-process cases, yielding 34 planned cases (previous 32 retained):
   finalize_hold waits at an explicit private release-file gate after the
   effect but before unlink, and finalize_fail fails at the same boundary.
   Both assert prior effect + fence present + final record absent. Hold then
   releases explicitly and requires OK + final completion + absent fence;
   failure requires DENIED, retained fence and no second effect/completion on
   parent-exit retry. No existing timeout or assertion is relaxed.
3. scripts/scan-owner-process-fixture.c: pass only these explicit test
   scenarios as test-guard options; preserve private-FD allowlist and parent
   relationship. A clean RESTORE reply must also observe fence absence in C.
   Existing live-unknown/crash checks still require unresolved fence and no
   prior restore; the failure case preserves a fence even though an inert
   effect has occurred. These tests do not simulate kernel/filesystem failures
   of unlink/fsync itself or prove crash durability on target storage.
4. scripts/test-fe35-cli-inbound-simulator.py: its three process integration
   cases now wait for final completion, retaining original effect count and
   lease/parent-exit assertions. No Simulator case is removed.
5. theos/btstack-probe.c: focused FE36 review found that the final control-CID
   close loop skipped unexpected packets and could still confirm a subsequent
   close ACK, allowing a verified candidate to reach commit. Mark opt-in auth
   cleanup uncertain upon any such packet; legacy FE35-only behavior unchanged.
6. scripts/test-fe36-cid-simulator.py and scripts/fe36-cid-sim-fixture.m:
   add late_cleanup_data after the full real synthetic-peer crypto exchange,
   injecting control-CID bytes before close ACK. Require failed typed result,
   cleanup uncertainty, delegation and no key. All previous 20 cases remain;
   21 are now planned. This uses real C/ObjC/Native with explicitly synthetic
   daemon/phone/config/lease effects.
7. theos/Fe36AuthTransport.h and theos/scan-owner/ScanOwnerRuntime.h:
   explicitly annotate both key array parameters as key[_Nonnull 16]. Preserve
   the borrowed 16-byte callback lifetime, block signature and zeroization.
   Audit call sites/definitions: local arrays are real stack buffers and matching
   block parameters inherit the typed callback contract; no nullable-key route
   is added and no warning is disabled.

Review also covered adapter sends outside locks, owner-executor cancellation
and commit rechecks, original handoff PIN/generation and minimum deadline,
one-shot borrowed key delivery and cleanup ordering. No other evidenced defect
was changed; crypto, Kotlin/Native API and signing were not rewritten.

## Executed local validation

All following validation commands exited zero on Windows using existing tools:

- python scripts/test-scan-owner-process.py --output [private-temp-directory]:
  portable protocol **308 assertions actually executed**, four POSIX production/
  test executables strictly cross-compiled with Zig for x86_64-linux-musl.
  Explicit output: POSIX_PROCESS_RUNTIME_PENDING. No Linux/macOS process pass.
- python scripts/test-scan-owner.py: production deny-all and owner **551+122**
  checks actually executed as Windows binaries built with Zig.
- python scripts/test-scan-owner-crypto.py: **6 tests passed**. Its tiny archive
  payloads are synthetic unit inputs, not the pinned production crypto ZIP.
- Strict Zig Linux-target C11/Wall/Wextra/Werror object compilation of
  theos/btstack-probe.c, both production and test/short-timeout profiles:
  compile-only, not target SDK or transport-runtime evidence.
- Python py_compile of all three changed Python harnesses; bash -n of the
  combined Apple entry and smoke Simulator shell script; git diff --check.
- Extract the two exact callback declarations into minimal local headers and
  compile Objective-C blocks with existing Zig/Clang and both nullability
  warnings plus Werror: corrected declarations pass. A negative control removing
  only both explicit qualifiers reproduces both array-nullability diagnostics.
  This is a real compiler check of the declarations, not Foundation/Kotlin
  headers, an Apple SDK build or ObjC runtime execution. The initial attempt to
  combine Zig's driver with fsyntax-only was rejected for its implicit unused
  -c; object compilation was used, keeping Werror. A main-file-only negative
  control did not emit the header diagnostic; included headers reproduce it.
- Existing JDK17/Gradle8.13, offline:
  :bridge:jvmTest --rerun --tests '*Fe36AuthBridgeTest' --tests '*HiCarAuthSessionTest' --offline --no-daemon.
  Test task actually reran: **28 tests, zero failures/errors/skips**; unchanged
  compile dependencies up-to-date. No unrelated full local suite rerun.

Logs in C:/Users/quesi/AppData/Local/Temp/:
openhc-finalization-process.log, openhc-finalization-owner.log,
openhc-finalization-crypto.log, openhc-finalization-jvm.log.
Local cross-compiled executables: openhc-finalization-local-process-20261128/bin.

All new process cases, corrected Linux/macOS process regression, SDK compilation,
Native/ObjC transport integration21, retained Simulator/UI/package gates are
**pending consolidated CI**, not local passes. This report does not update the
running macOS conclusion or claim a new App package.

## Preservation and next action

Fresh before-write snapshot:
Temp/openhc-guard-finalization-preservation-20261128.json.
Verification and exact patch hashes:
Temp/openhc-guard-finalization-delivery-20261128.json.
Fourteen unrelated tracked dirty files must retain their exact byte hashes;
both mixed histories are prepended only and remain unstaged. Index remains
empty at preparation; base HEAD unchanged before the authorized commit. No
installer/helper/pin, Trial, identity, tools, mock, evidence or upstream files
were edited. New report plus nine code/header/test files are the precise
correction candidate; two history prepends are not candidates.
Native crypto inputs and reuse-validation script are unchanged; diff against
pinned source6d1731813d95e8e60f7628a7a06f95848668c6f2 for native/crypto and
scripts/build-crypto-backend.sh is empty. No old framework was reused.

Submit the combined correction once under coordinator authorization, verify
remote SHA, dispatch workflow431974121 validation_scope=owner once and read one
initial receipt. Report WAITING_CI or RUN_ID_PENDING without polling; coordinator
audits completion. Retain every existing required gate and current SDK/framework
build, crypto-only reuse and ordinary hosted-runner route.
Production admission and native Trial effects remain unavailable/deny-all.
Real rootless launch/FD provenance, trusted config/local BD_ADDR/provider and
dual-ready/QR joins, secure trust persistence and actual FE36 I/O remain gated;
then WiFi/TCP and DMSDP/media must be implemented and validated. Software inert
recovery and synthetic-peer authentication are not Honor/iPad interoperability
or a HiCar session. Route remains Theos rootless DEB/macOS15/ldid -S.
