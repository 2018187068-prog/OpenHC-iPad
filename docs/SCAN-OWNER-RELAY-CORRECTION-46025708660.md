# Darwin test relay bootstrap correction — 2026-11-27

Original run `run_25334cb0a007`; task `task_7691887abe03`, dispatch
`ctx_4312ce46a76b`. This is a test bootstrap compatibility correction, not
production activation or real HiCar acceptance.

## Prior run and actual failing layer

Run `46025708660` attempt 1, source
`856d913b0e1e16d40f2e836af787e1e85e138257`, completed with focused-host success,
owner-apple failure and focused-required failure. The existing verified
`owner.zip` contains `artifacts/scan-owner/process/stale_generation/broker.log`:

```text
PROCESS_ASSERT=!getsockopt(input,SOL_SOCKET,SO_ACCEPTCONN,&listening,&n) line=162
```

The subsequent Python fragmented ARM write raised BrokenPipe. The native
bootstrap assertion precedes it; no errno was captured and none is inferred.
The coordinator's verified host artifact passed actual Linux POSIX 21 cases,
protocol 308, owner 551+122 and JVM 47. Its Apple artifact passed framework
build/Native 45, owner 551+122, protocol 308 and the first eight main process
cases. Later process cases, deployment compile loop, current Simulator/UI and
App/inert packaging were not reached. These are prior-SHA results only.

Existing artifacts (not downloaded again):

- host artifact `15212028219`, SHA256
  `22b8bbd9e44065900ab039a3137391604c035ff778e573717064a4a462340ae3`.
- owner artifact `15212118512`, SHA256
  `ed831c40f5e20f29a4789f75ad6047acdd0c9698660946c6ee427c0c6cf1cded`.

## Exact source boundary

1. `scripts/scan-owner-process-fixture.c`: replace listener guessing with the
   explicit test-only `relay-connected` / `relay-listener` modes; reject other
   modes before guard spawn. Validate SO_TYPE and returned option size, local
   family, connected Unix peer, and IPv4 loopback/nonzero-port addresses.
   A listener proves its listening state by actual nonblocking accept, with
   only EAGAIN/EWOULDBLOCK entering the existing bounded 45-second launch wait.
   Validate both accepted endpoints and stream type, then close the inherited
   listener. Preserve descriptor flags while setting CLOEXEC/NONBLOCK. Add
   static component/operation/actual errno diagnostics (semantic failures use
   errno=0); no protocol data, QR, PIN, key or identity is logged.
2. `scripts/test-scan-owner-process.py`: Broker chooses mode from the socket it
   created; a nonzero broker exit now fails explicitly. Retain all 21 prior
   process cases. Add nine pre-guard rejection cases (old/invalid mode,
   nonsocket, datagram, unconnected Unix, wrong families, nonlistener,
   connected-as-listener and nonloopback listener), one fragmented loopback
   lifecycle/one-shot listener case and one connected EOF/death/delegation
   case: 32 process cases total when executed on POSIX. Invalid bootstraps
   assert no guard exec evidence/lock/fence; guard inheritance leakage and
   parent-exit recovery assertions remain.
3. `scripts/test-fe35-cli-inbound-simulator.py`: immediately close Python's
   listener copy after publishing its numeric test port. This directly
   necessary three-line lifecycle fix prevents a parent-held listener from
   surviving the broker's one-shot accept. All three existing process
   Simulator cases use Broker's new mode. The final close remains harmless
   and idempotent. No Simulator protocol/assertion/deadline was relaxed.
4. This new correction report. No production, guard, common, crypto, workflow,
   installed demo, helper, installer, pins or Trial sources changed.

## Review and local evidence

Executed on Windows using existing tools, all exit 0:

```text
python scripts/test-scan-owner-process.py --output artifacts/scan-owner/relay-correction-local
  SCAN_LEASE_PROTOCOL_ASSERTIONS=308
  POSIX_PROCESS_RUNTIME_PENDING=Windows-cross-compile-only-no-Linux-or-Apple-runtime
python scripts/test-scan-owner.py
  SCAN_OWNER_PRODUCTION_DENY_ALL_OK
  SCAN_OWNER_TEST_ADAPTER_CHECKS=551
  SCAN_OWNER_COMMON_TERMINAL_CHECKS=122
python scripts/test-scan-owner-crypto.py
  Ran 6 tests, OK
python artifacts/scan-owner/process-local/check-sources.py
  Python AST 3, workflow shell blocks 12, shell files 2, synthetic archive cases 8
  deployment test macros absent; production factories deny-all
git diff --check
```

The last Python command is the retained local source-check helper, not a newly
staged source dependency. It parses both changed Python harnesses, checks
`check-scan-owner-apple.sh` and `test-fe35-cli-smoke-simulator.sh` with bash -n,
checks workflow shell blocks, package negative fixtures and unchanged deny-all
factories. Strict C uses `-std=c11 -Wall -Wextra -Werror`; protocol/owner run
as Windows executables, four POSIX programs cross-compile as Linux ELF only.
No local GCC, Darwin/Apple SDK or POSIX-process runtime pass is claimed.

Reviewed the remaining owner process assertions and all three process
Simulator call sites, `scan-owner-sim-fixture.m` callback/ARC lifetimes,
`ScanProcessLeaseAdapter.m` serialized I/O, guard parent relationship and FD
allowlist, deployment compilation source lists, inert Theos package inputs and
combined failure propagation. No additional source fix was justified. Guard
spawn remains after listener accept, preserving the independent 3-second
READY budget. The inherited relay input cannot survive guard exec; only the
guard's private channel and directory reach descriptors 3/4. No new authority
is derived from a socket mode, local peer, successful accept, PONG or marker.

## Preservation and single focused submission

Before editing, captured names/status/HEAD and SHA256 of all 16 pre-existing
tracked dirty files (no identity/config contents) in
`C:/Users/quesi/AppData/Local/Temp/openhc-relay-correction-preservation-20261127.json`.
All 14 unrelated files must retain exact hashes; HANDOFF and checkpoint
receive prepend only and remain unstaged with exact original byte tails.
Untracked identity/tools/mock files are neither read nor staged. The reviewed
index allowlist is exactly the three scripts above and this report; staged
diff and hashes are retained beside that snapshot.

One bounded `[skip ci]` commit, one feature-branch push with exact remote SHA
verification and one workflow `431974121` dispatch with `validation_scope=owner`
are authorized. Initial receipt goes in local submission JSON and latest
unstaged HANDOFF/checkpoint; no polling, duplicate dispatch or automatic rerun.
Before receipt this correction is locally checked, with corrected-SHA POSIX
and GitHub macOS compilation/simulator/package validation pending. Combined
entry remains `bash scripts/check-scan-owner-apple.sh /absolute/pinned-source.zip`: crypto-only
reuse and input-aware current frameworks, original 3 FE35 + 8 native + 11 owner
+ 3 process Simulator cases, UI/system-decoder and actual packages; host owns
full JVM validation. Required failures continue to propagate.

## Production and final-goal limits

Production broker/owner admission, descriptor adoption and adapter factory
remain deny-all. Actual rootless restricted launch/FD provenance into nonroot
UIKit and native independent Trial recovery effects remain unverified/missing.
Real OS exec/IPC/filesystem/parent lifetime execute only in the POSIX fixture;
admission and recovery/hardware effects are injected inert effects. No test
channel activates a deployed provider or grants mobile/root authority.

Next real joins remain restricted production provider/config/local BD_ADDR ->
owner/native FE35 dual acknowledgements -> same-generation visible QR/PIN ->
Honor scan/Nearby -> same-PIN authentication/FE36 -> WiFi/TCP -> DMSDP/media.
AUTH_HANDOFF notification and crypto vectors are not a completed authentication
session. This correction neither reads identity nor operates any device,
radio, power, Showcase, installed helper or pins. Dopamine rootless Theos DEB
and macos-15/ldid -S remain unchanged; no official Apple signing migration.
