# Original FE35 case process-isolation correction

The exact audited run46133905801 / 9517f6935a0484340c375bfccd117d68380db873
failed when the third original FE35 case's simctl launch exceeded30 seconds.
Its artifacts establish JVM117/Native110 and Darwin listener8/TCP pump3 passed,
but do not establish why launch stalled. Only the first two original FE35 cases
completed; scan8/owner11/process3, full FE36 matrix39, UI/QR and packages were
unrun. The last status log matches the preceding negative case and is not
evidence of incoming_timeout execution. No production or infrastructure cause
is inferred from that failure.

The source-proven isolation gap is separate: the fixture writes its result just
before returning from main, while the first three run_case callers previously
accepted result publication plus peer completion without observing process exit.
This correction makes that invariant explicit without claiming it caused the
old launch stall. The existing full CID matrix already conservatively observes
the exact simctl-reported host PID; the original three cases now follow the same
strict output shape and signal-zero observation semantics.

After a successful launch, only the exact bundle-id: PID output is accepted.
Result publication retains its existing bounded polling. Once the result exists,
the exact PID must be observed exited and the peer must finish within ONE
monotonic eight-second allowance shared with the original thread join. The
deadline is never reset. A PID still present, reused/reappearing PID, missing
PID, EPERM or any observation failure fails closed. ESRCH is the only observed
exit indication. Process observation is Darwin-only; Windows tests explicitly
inject process states and are not an Apple process-lifecycle claim.

Finally records redacted evidence before teardown, closes the host listener and
accepted sockets, joins within the remaining allowance, and records the final
isolation certificate. Socket closure is not an app-exit certificate. Exact PID
exit, stopped thread and successful host-socket closure are all required before
the case can succeed or allow the caller to launch another case. A final
certificate is written before deleting the guard or printing CASE_OK. Failure
of either evidence write still runs socket/thread cleanup and remains nonzero.
No app termination, relaunch, launch retry or automatic matrix continuation is
used to manufacture isolation. PID reuse cannot be identified reliably and is
conservatively treated as presence/failure.

Stale status/result files are reset before each original-case launch. Safe
diagnostics retain fixed phases and elapsed times, return code, strict PID
shape, stdout/stderr byte sizes, fixed stderr labels and before/after process/
thread/socket states. Partial TimeoutExpired output is classified but never
serialized verbatim. Arbitrary exception messages, launch arguments, payloads,
frames, keys, PINs, credentials and real identities are excluded from the new
JSON. If launch never reports a PID, app state stays unproven and the suite
aborts. Existing protocol/status/heartbeat/assertion requirements remain.

Local verification: failure-evidence23 regressions cover live-to-exited,
never-exits, missing PID, permission/observer error, result-before-exit,
PID reappearance, live thread, partial-output launch timeout, stale attribution,
before/after evidence-write failure and actual-main prevention of later launches
or success markers. Real host loopback tests prove accepted-socket closure and
thread settlement; process states are injected. Retained matrix13,
cancellation-order4, WiFi diagnostics6 and loopback negotiation-driver10/221
also pass. Python syntax and bounded diff checks pass. Existing Zig strict
C11 -Wall -Wextra -Werror compiles current production/Simulator/transport/pump
sources for aarch64/x86_64 Darwin; this Windows preflight is compile-only.

Only the two Python harness/test paths and this report belong to the change.
No production code, protocol/crypto/lease rules or macros change;30s launch,
6s peer I/O, original result polling,8s total teardown/join and under10s
post-launch assertions remain.16 unrelated dirty hashes, both history suffixes,
unrelated untracked files and an empty unrelated index are preserved.

The single consolidated owner CI validates this isolation invariant and
captures missing launch evidence. Native, actual Apple process observation,
full39, UI/QR and rootless package acceptance for the new SHA remain pending
until audited. Production stays deny-all with injected providers. No device,
identity, radio, installation, helper, pins, Trial, tools or signing work is
performed. This is neither real HiCar acceptance nor proof of the old launch
root cause; iPad cooperation is not needed for this software gate.
