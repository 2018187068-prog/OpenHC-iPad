# Common terminal to owner revocation correction — 2026-11-27

Task task_b7ad6bf52c6e / ctx_6c10c29efdf1, parent
9f64a15cba54561ca990c7ccdc58942c7886cddf, stage0-auth-validation.

## Exact prior failure and evidence boundary

Coordinator's completed audit: run46012096688 failed owner-apple/required;
focused-host succeeded. No new App package. Existing local ZIPs were hash
checked again without network fetch, directory
C:/Users/quesi/AppData/Local/Temp/openhc-run-46012096688:

- host.zip / artifact15203309822 SHA256
  c2c2ac342df38e136bc65e9631846888a46999b419a1932424694bab0fa3fb71.
- owner.zip / artifact15204394152 SHA256
  5a3e440e30dd7a84d60d71449e87bad1c7448f56116787909f19baf6d5e317f3.

The archived owner-deadline_wait/scan-events has common CLEAR, CLOSE, STOPPED
before native FAILED/CLEANED, completion 1,0,1 and counts 0,1,1,1. The exact
violated old fixture line80 predicate is !coreClear at common CLOSE. Final
completion/count expectations match. Before native FAILED, the owner only saw
TICK; its 240000ms lease has not expired when common's 2000ms scan expires.
consume forwarded the terminal batch without revoking owner authority.
RFCOMM_LISTEN is the cancellation-stage status, not a separate root cause.

Prior-SHA evidence: Linux GCC deny-all/551, JVM47, Native45, Darwin551, both
deployment SDK compilations, 3 FE35/190 assertions, 8 native and first8 owner
cases passed. Owner deadline_wait failed ninth; ready_timeout, cleanup_failure,
UIKit and package were not reached. Device compilation was not device execution.

## Exact production correction and bounded paths

- theos/scan-owner/ScanOwner.c/.h: internal ohc_owner_common_event permits only
  same-owner-generation CLOSE_CONTROL_TRANSPORT to invoke existing STOP logic.
  Stale events, accepted CLEAR, CLEANED and unrelated kinds cannot cancel or
  supply cleanup/guard authority. This portable selector makes the production
  contract directly executable in local strict-C regression tests.
- theos/scan-owner/ScanOwnerRuntime.m: consume first fences the captured owner
  generation and preflights same-common-generation events for the whole batch
  before forwarding any event. Thus owner CLEAR/cancel precede common terminal
  CLEAR/CLOSE and actual native cleanup, even for the shorter common budget.
  Calls occur on the existing executor after core operations return, outside
  effect handlers; no queue sync or effect-handler reentrancy was added.
- scripts/scan-owner-tests.c: all original 551 assertions untouched; add startup,
  ready and accepted-state common expiry, stale generation, CLEANED immunity,
  ordinary accepted CLEAR, one-shot cancellation, immutable lease and no premature
  recovery assertions. Accepted CLEAR alone preserves the existing same-PIN
  one-shot handoff; a terminal batch after ACCEPTED cancels before any handoff.
- scripts/scan-owner-sim-fixture.m: 31 named assertion sites replace opaque
  invalid writes and strengthen owner-revoke-before-common-clear coverage.
  Static diagnostic labels only; no QR/PIN/key/identity values. All completion,
  ready/count/lifetime/timeout expectations remain unchanged.
- scripts/test-fe35-cli-inbound-simulator.py: necessary harness diagnostic join
  includes the archived named trace on fixture failure, and asserts owner CLEAR
  once before common CLEAR/CLOSE. Original protocol assertions remain.
- This new report; no mixed existing document is staged.

Lease deadline, sole heartbeat, independent guard decisions, worker callback
lifetime, typed completion and CLEANED semantics are unchanged. No lease budget
was lengthened or shortened to conceal the defect. The stop pipe writer remains
nonblocking; native clears its cancellation polling binding before cleanup.
The runtime session/binding/sink still survive through typed return. Successful
ACCEPTED has no common CLOSE, so it is not terminal.

Remaining cases reviewed together (not claimed executed locally):

| Case | Ready / clear / close / CLEANED | Typed return | Guard decision |
| --- | --- | --- | --- |
| deadline_wait | 0 / 1 / 1 / 1 | true, false, 1 | delegate |
| ready_timeout | 1 / 1 / 1 / 1 | true, true, 1 | request verified restore |
| cleanup_failure | 1 / 1 / 1 / 1 | true, false, 1 | delegate |
| success | 1 / 2 / 1 / 1, same-PIN handoff once | true, true, 0 | request verified restore |

All paths require owner core-clear exactly once before common close; common
accepted CLEAR plus terminal CLEAR account for success's two common clears.
Native FAILED/STOP after common expiry remains idempotent, and final CLEANED
cannot become cleanup success. Expiry during accepted/handoff is terminal;
common's existing expiry-before-operation contract returns no PIN, while the
owner adapter cancels on that batch before downstream callbacks.

## Actual local validation

Windows with existing Zig, python scripts/test-scan-owner.py exited0:
production deny-all; legacy SCAN_OWNER_TEST_ADAPTER_CHECKS=551; additional
SCAN_OWNER_COMMON_TERMINAL_CHECKS=122. A temporary mutation removing only the
new selector's STOP call strictly compiled, preserved legacy551, then failed
the new revoked/cancelled/STOPPING assertion as expected. This is actual C
execution, not Objective-C/Apple runtime validation.

Crypto reuse synthetic unit tests: 6/6. Existing Git Bash -n passed each of
the combined Apple, FE35 Simulator and UIKit shell entries; Python harness AST
parses. Source checks confirm unchanged expected cleanup/ready/status arrays,
2000ms/15s fixture limits, all invalid writes diagnosed, and generation-fenced
preflight before event forwarding. The initial ad hoc source check misspelled
dateWithTimeIntervalSinceNow's case; corrected check passed with no code change.
git diff --check passed. No local GCC or Apple SDK execution is claimed.

## One focused follow-up, not production activation

Commit only the six source/test paths above and this report with [skip ci],
push the current feature branch once, verify remote SHA and dispatch
workflow431974121 validation_scope=owner once. Initial receipt and exact SHA/run
will be recorded locally in this report and latest HANDOFF/checkpoint sections;
mixed HANDOFF/checkpoint history stays unstaged. No polling or automatic rerun.

The unchanged workflow performs current host checks and GitHub macos-15
compilation/Simulator checks via check-scan-owner-apple.sh. Current frameworks
and Native inputs are rebuilt/input-checked; only pinned crypto ZIP reuse is
permitted. Original 3 FE35 + 8 native + 11 owner, CPU QR/system decoder, UIKit
and actual App archive gates remain. No legacy/helper build or new package pin.

Production stays deny-all; root-controlled caller launch/connection policy and
target-native Trial independent guard actor remain missing. Rootless Dopamine/
Theos DEB/ldid -S unchanged. No device/USB/SSH/identity/credential/radio/power/
Showcase/BAA operation. No phone connectivity, stable-device or full-S0 claim.
