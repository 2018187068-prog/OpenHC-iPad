# FE35 bridge length correction

Prepared on 2026-11-28 from base
466c2e4b700302513e6972040d663c8b100f31c5, branch stage0-auth-validation.

## Prior run evidence

Coordinator audit of run46048100313 attempt1 at 466c2e4 reports final
FAILURE. Host failed on Kotlin 2.1.20 plugin/BOM Maven Central GET/HEAD 429,
so JVM did not execute. macOS strict compilation failed in
fe35-control-bridge.m:105 at the signed int32_t uuid.size versus unsigned
sizeof(out->uuid) comparison (-Werror=sign-compare). Do not report that run
as passing or as a source logic failure in the host; this correction changes
the source SHA, so no old-SHA job is repeated.

## Correction

theos/Fe35BridgeBounds.h adds one shared checked signed-length conversion:
it rejects a null output, negative values, and values beyond capacity before
conversion to size_t, and only writes the result after validation.
theos/fe35-control-bridge.m uses that helper for both Native UUID and frame
arrays before indexing/copying. This makes the frame's previous implicit
negative-to-large-unsigned rejection explicit as well.
scripts/fe35-control-bridge-test-stub.c exercises negative, zero, exact
capacity, over-capacity and null-output behavior through the same helper used
by production. Existing transport socket harness compiles this stub under
strict C warnings. scripts/check-scan-owner-apple.sh explicitly includes the
new helper in its before/after source manifest, so current-source artifact
integrity covers this dependency.

No nullability warning, Werror, assertion or bounds check is disabled. Focused
review of bridge/owner comparisons found no other signed-size versus sizeof
issue in the newly strict-compiled sources; other Kotlin array lengths are
already checked for nonpositive values and bounded before casts/chunk copies.

## Local evidence and limitations

Windows existing Zig toolchain compiled and ran the shared production helper
tests with C11/Wall/Wextra/Werror: negative, zero, exact-capacity,
over-capacity, INT32_MAX-to-SIZE_MAX and null-output cases passed. The existing
owner script passed production deny-all and 551 owner + 122 common checks; the
owner process script passed 308 portable lease protocol checks and strictly
cross-compiled POSIX sources, explicitly reporting process runtime pending on
Windows. Crypto reuse validation's six tests passed using synthetic archive
unit inputs; these do not inspect or restore the pinned production ZIP. The
pinned crypto source and reuse rules were not changed. Python bytecode,
combined Apple entry/simulator shell syntax, strict C translation-unit builds
and git diff whitespace checks passed.

The host 429 means JVM was not validated on the previous SHA; current SHA's
JVM gate is pending. The transport socket integration runner was attempted but
cannot start on this Windows image: it requires an installed clang executable
and creates its temporary workspace under /tmp. It exited before any socket
case. No Apple SDK/Foundation/Kotlin framework compile or Simulator execution
is claimed. The shared helper test does not replace actual ObjC bridge/SDK
validation; that remains required in the next owner run. The prior run's new
FE36-CID21 cases and UI/package stages were not reached and remain pending.

## Submission and remaining joins

This correction is bridge hardening only. Production admission remains
deny-all and the deployed receiver provider remains synthetic. Before a field
window the owner still needs a trusted provider, fixed root-controlled
configuration and local BD_ADDR source, proven Dopamine launch/private-FD peer
provenance, and a deployed independent native Trial recovery actor. Actual dual
FE35 readiness must feed the same-generation foreground QR/PIN and revoke it
on Stop/background/deadline. FE36 transport authentication success and a
borrowed key do not hand off the bounded owner lease or create a persistent
authenticated session. The next protocol work is an explicit authenticated-
session lease transfer with cancellation and trusted secure-persistence
adapter; then actual WiFi/TCP session setup and DMSDP/media entrypoints must be
implemented and validated. No phone, device or HiCar acceptance is established
by this change.

The crypto-only archive source and digest rules remain unchanged; no stale
framework restoration or signing route change. GitHub macOS 15 current-source
build/simulator gates and Theos rootless DEB/ldid -S remain the validation path.
