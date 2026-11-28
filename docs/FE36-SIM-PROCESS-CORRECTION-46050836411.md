# FE36 Simulator process diagnostic gate after run46050836411

2026-11-28; original run_25334cb0a007, task_2c1e2918b195 / ctx_b632aaea5527.
Base 220f4be47620196d44120c6355397b6cda0dfe5c, stage0-auth-validation.
This is an explicitly coordinator-authorized diagnostic gate, NOT a claimed
root-cause fix, Simulator acceptance, or real Honor HiCar acceptance.

## Verified prior evidence

Binary-safe subprocess artifact downloads were checked before extraction:
owner artifact15224074697 SHA256
bafcf8a4959175d2f15c506af290fa5cf1fe41e9486c887c109c828b54c26c5e;
host artifact15223878134 SHA256
c163b7d60caaa0db4b43c514eb7e6c36c3f7c4e610daa4a8cad88ad656ff0e11.
Retained at C:/Users/quesi/AppData/Local/Temp/openhc-run-46050836411;
BUILD SHA/run matched exact base/run. Coordinator log is
D:/orcafile/ci-46050836411-failed.log. Run ended FAILURE, not success.
Local XML audit of those archives: JVM92 and Native90, each zero failures,
errors and skips. Prior macOS owner551+122/protocol308/POSIX34, strict both
SDK compilations and owner/common11 passed; these are prior-SHA evidence.

First failing process Simulator case is ready_stop. Its archived guard events
show GUARD_LOCKED_PRIVATE_FDS, ARM_IMMUTABLE, DELEGATE_ONCE,
PARENT_EXIT_OBSERVED, INERT_RESTORE_ONCE, INERT_RECOVERY_COMPLETED, and NO
INERT_TAKEOVER. Broker log has relay-listener bootstrap and inherited-FD EOF.
Python asserted result-file existence before copying Simulator status/scan trace,
so the archive cannot distinguish ARM ACK transmission/validation failure from
owner phase expiry or another pre-worker cancellation. Warnings do not establish
root cause. No syscall errno, exact timing or Simulator exit status is invented.
FE36-CID21, UI and package stages were not reached and remain unaccepted.

## Exact bounded changes and preserved policy

- theos/scan-owner/ScanLeaseChannel.c: test-build-only operation/generation/
  sequence/monotonic-now/original-deadline and write/read/ACK validation labels;
  records actual errno and individual reply mismatch predicates. The same finite
  I/O bounds and fail-closed checks remain. errno=0 means no syscall errno was
  reported, not proof of successful I/O.
- theos/scan-owner/ScanOwner.c: test-build-only absolute/phase/reversed-clock
  expiry labels; original stop/delegate logic, comparisons and budgets retained.
- theos/scan-owner/ScanOwnerRuntime.m: test-build-only effect/state/deadline and
  ARM callback receipt labels on the existing serial executor; no reentrancy,
  new callback, lifetime or authority changes.
- scripts/scan-owner-process-fixture.c: relay operation/stage/errno and spawn/FD
  allowlist monotonic timestamps, preserving current bounded relay stages.
- theos/scan-owner/ScanGuardProcess.c: test guard records input metadata,
  protocol acceptance/rejection/overdue state and ACK write outcome. Independent
  recovery/fence/effect semantics are unchanged. Diagnostic file writes add
  test-only observation overhead; no lease deadline or timeout is increased.
- scripts/scan-owner-sim-fixture.m: explicit bounded-completion exit95 marker
  flushed before the existing immediate exit; borrowed callback state remains
  retained until process exit.
- scripts/test-fe35-cli-inbound-simulator.py: copy evidence before bounded-result
  assertion and unconditionally in finally; preserve launch receipt, peer errors
  and broker exit/cleanup errors. Original assertions and case ordering remain.
  Host broker exit on failure is cleanup evidence, not successful owner recovery.
- scripts/test-simulator-failure-evidence.py: four deterministic launch/result
  failure regressions including process mode, injected launch/thread/socket/
  broker only; real filesystem copies execute. Not a Simulator/process pass.
- .github/workflows/scan-app-focused.yml: add that failure-evidence regression
  to owner host suites with existing failure aggregation.
- scripts/check-scan-owner-apple.sh: include the new regression in source manifest.
- This report only. No crypto/auth/transport protocol, timeout, signing, pin,
  provider, installation or production authority changes.

## Deterministic notifier and model deadline (workspace only)

D:/orcafile/check-current-ci.ps1 and ci-notifier.ps1 now query exact run/SHA/repo
only when pending and due; every query attempt advances nextCheckAt by 30min.
State replacement is atomic and uses a shared exclusive lock across query/send;
new submissions use Publish-CIState under that same lock. notify_sending is
persisted before send. Success stores complete JSON receipt/request ID;
failure/ambiguous/crashed sends stop automatic retries and preserve diagnostics
for manual receipt/retry-request recovery. No fresh-ID retry loop exists.
The precheck always exits nonzero, so it cannot launch a model after notification.

Automation477f4a65-f486-486c-b049-b85abeb79d91 was read enabled=false and is
unchanged. No second timer, watcher or model/provider/credential change. Because
it is disabled there is currently NO scheduled completion wake; coordinator must
invoke the deterministic checker or separately authorize a non-agent runner.
Manual automation Run bypasses precheck and must not be used. No real notifier
send/query or model request was used in tests.

Register-CIModelFailure preserves first actual failure time and fixed +150min
deadline, grants at most one retry per30min, and marks model_retry_expired /
automationDisabledRequired at deadline; expiry never reopens on clock reversal.
It is a state-policy helper, not a model launcher or a way to constrain an agent's
internal reconnect loop. Such internal reconnects cannot be controlled here;
the agent-backed automation stays disabled. No active old model chain is resumed.
CI-NOTIFIER.md describes the required writer lock, receipts and these limits.

## Actual local validation

All commands ran on Windows with existing tools; no installation:
- python scripts/test-scan-owner.py: production deny-all, owner551 + common122.
- python scripts/test-scan-owner-process.py --output
  D:/orcafile/process-diagnostics-46050836411: protocol308 actually executed;
  strict Zig C11/Wall/Wextra/Werror Linux-musl binaries compiled only. Explicit
  POSIX_PROCESS_RUNTIME_PENDING; no Linux/macOS runtime claim.
- python scripts/test-scan-owner-crypto.py: six reuse-rule tests passed with
  synthetic archive test inputs; no claim of freshly executing crypto on device.
- python scripts/test-simulator-failure-evidence.py: four tests passed.
- powershell.exe -NoProfile -NonInteractive -File
  D:/orcafile/test-ci-notifier.ps1:34 assertions passed in Windows PowerShell5.1,
  real temp atomic file/lock operations, injected GitHub/Orca adapters. Includes
  inactive/notdue/pending/completed/SHA mismatch/network/send/ambiguous failure,
  no duplicate send, concurrent replacement lock, fixed150min/30min/next-day
  expiry and no reopen. No remote calls or real message.
- Python bytecode and Git Bash -n scripts/check-scan-owner-apple.sh passed.
- Current source reviewed for unchanged assertions/bounds; git diff --check is
  required before staging. No Apple SDK/Foundation/ObjC/Simulator local pass.
Common Kotlin/crypto inputs unchanged; JVM92/Native90 are archived prior-SHA
results, current framework/JVM/Native/Simulator gates remain CI requirements.
Crypto source diff from pinned6d1731813d95e8e60f7628a7a06f95848668c6f2 for
native/crypto and scripts/build-crypto-backend.sh is empty; reuse gate unchanged.

## Next evidence and real-session joins

One current-SHA owner CI is authorized as a diagnostic gate, not an automatic
rerun loop. Correlate LEASE_IO request/write/read/validated-ack with RELAY_REQUEST/
RELAY_REPLY, GUARD_REQUEST/ACK and OWNER_ARM_RESULT/OWNER_EXPIRY plus the now
preserved scan/status/exit evidence. Distinguish startup/FD-allowlist latency,
channel failure/ACK rejection, clock/deadline/phase expiry and pre-worker failure
before choosing a control-flow correction. Original budgets remain fixed.

Production remains deny-all and deployed provider synthetic. Actual target
rootless launch/private-FD provenance, trusted provider/fixed config/local
BD_ADDR and independent native Trial recovery/secure persistence remain gated.
After this failure is resolved, next meaningful protocol slice is authenticated
post-auth control/session/lease ownership into WiFi/TCP; FE35 must stay until
phone on WiFi. DMSDP/media remain subsequent runnable dependencies. No phone,
radio or full HiCar session is established by synthetic daemon/config tests.
Route remains GitHub macOS compilation/simulator checks, Theos rootless DEB,
ldid -S, with no official Apple signing or device operations.

## Preservation and workspace file digests

Fresh pre-edit snapshot: D:/orcafile/preservation-46050836411.json. Index was
empty. Fourteen unrelated dirty files must retain these exact SHA256 values;
both mixed histories get only a prepend and stay unstaged, checked against
byte-for-byte retained prior suffixes in history-*-46050836411.bin.

- docs/PLAN.md: cef16ec0d9e5959276ebb515ecdcf7c02a89de4d3a265114419a389258406579
- docs/BTSTACK-OWNERSHIP.md: 5d08cae2c3215f48321ab2375f7d6a829273b6853b57299ccfbf66cf1b327924
- HANDOFF-CURRENT.md: 84cfff652103ec4a4b0bfc0c17ebe07a5e17bf184e8ed0e284c473b1ac376e77 (preserved historical suffix)
- docs/SCAN-APP-FOCUSED-VALIDATION.md: 9880dbb4539143f58d08859274bd50932871478a7f71d59ea419730ab1dc0eb9
- docs/TECHNICAL-ROUTE-HANDOFF.md: 5b1c7158cab0dc08287cb39b0e1c2821df800d595e00832c292e25e8313ea355
- scripts/capture-btstack-session-evidence.py: 6d34b741c23bc94c1fec4ee37a41d204509f8b8584407778d4b0846c8a4125f3
- scripts/install-scan-demo.py: c845ab530082a6e05766a403c6f8965c1c99dafcea1d208f1a0b8f0bd5c6f23c
- scripts/btstack-power-trial.py: 52ca929a8251109f7d5bb52e3a9d73510c5d9cdf34d2ab016d5f1470cb975fa0
- scripts/test-btstack-power.py: e7d1aa33e93344a6876c4e7d5b95224755653e2412bfefe42cf9334bee21031f
- docs/SCAN-OWNER-CORRECTION-46010768572.md: b5f60c82bdc2e9d3b40015793eb54147d237a7770462845285482192b4def342
- docs/RESUME-CHECKPOINT.md: 14af12bc42ee83ee0e815877382c6077dfc3a03a997ae34bc7c36e8850eeaf6d (preserved historical suffix)
- docs/SCAN-OWNER-INTEGRATION.md: 836f5511760a5f938af27683f4f83aeb15e9c8c8f2a8120cd7b2b1e2d414e8e5
- docs/SCAN-STARTUP-IMPLEMENTATION.md: 47c4386a0ff5c98ba0dafe822ab80281a9074ce5e68d8086631963fd68de9ba8
- docs/SCAN-OWNER-PRIVATE-GUARD-SLICE.md: bbaf85bab0c8fc7063b7e76ceb6adab2c79c4af8bef0e9b7a4d2eb2abb77f05b
- scripts/test-capture-btstack-session-evidence.py: 40d6fe5d1bda317e0e0699b1d083bb205aca1c11c5238e9d8ecdac2e513fa258
- docs/SCAN-OWNER-TERMINAL-CORRECTION-46012096688.md: 7e0576de713412a239c8108a5c03a5f82fa6ccbdc80c3cca75df031603f51123

Workspace notifier file SHA256 (not part of shared repo commit):

- D:/orcafile/check-current-ci.ps1: 036084e3f2f8c224899434843bf7dd0b4b0fbf9712fde60b75c316cf1c340f48
- D:/orcafile/ci-notifier.ps1: a2b4b6329700c775c48186a4a25cc884032a885b3c27991b42f6579c5c0337e6
- D:/orcafile/test-ci-notifier.ps1: 6619754b2b1cfcb198ea744d38c377288e69f288d8059f59e6d20744e86e5d4e
- D:/orcafile/CI-NOTIFIER.md: 94faa93db3f5320320fdca2f1e98c657a87a30b41408b828634ae79f8758f69d
