# FE36 auth disconnect fixture correction

Run 46141656304 at 571c85569e1e73a09d05ca186c0dcdbab72fdb51 failed only
auth_disconnect in the 39-case FE36 matrix. Exact artifact identity was
verified from both job BUILD records and GitHub's artifact digests. The archived
case reached the real Native authentication stream, received a remote auth-CID
close, and completed the cleanup command exchange. Its typed completion was
returned=1, cleanup_confirmed=0, status=1; Owner consequently delegated to the
independent guard. All 38 other FE36 cases and the focused Linux/JVM job passed.

The Objective-C fixture's expected-uncertainty list omitted auth_disconnect,
so it incorrectly required confirmed cleanup and prohibited delegation for an
exchange aborted by a remote disconnect. The correction adds this scenario to
the fail-closed delegation expectations. Production C/ObjC/Kotlin behavior,
deadlines, protocol, keys, and trust behavior are unchanged. Failure remains a
failure; no HiCar or device acceptance is implied.

The case retains checks for typed status, revoked pairing, one terminal close,
final executor barrier, and no key delivery. The next exact owner CI run must
verify the corrected Apple Simulator case and all downstream required gates.
