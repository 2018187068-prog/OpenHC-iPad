# Owner cleanup completion at the STOPPING boundary

Run46139195651 failed owner-ready_timeout because the fixture equated confirmed
native cleanup with a timely owner completion. The native INCOMING_TIMEOUT was
intentional; cleanup was confirmed. Stop began at1169120ms, its fixed phase
deadline was1170120, and the completion tick1170137 correctly delegated recovery.
The fixture rejected that valid delegation. Earlier run46136123466 completed
before the same fixed boundary and requested restoration. The cause of the
additional native completion delay remains unknown.

The test fixture now validates its guard decision against the existing bounded
OWNER_PHASE/OWNER_EXPIRY observations at typed completion. Confirmed cleanup
before the deadline requires one restoration and no delegation. Confirmed cleanup
after delegation requires an actual STOPPING expiry at/after the recorded phase
deadline, before the single delegation, and no restoration. Uncertain cleanup
still requires delegation. Missing, stale-generation, nonmonotonic, contradictory
or duplicate evidence fails. Native cleanup/status/readiness/revoke/close checks
remain; synthetic lease effects also assert exact-once restore or delegation.
The Python driver independently validates the native decision and trace order.

Effect logging samples time separately from the actual state-machine tick.
Timely completion therefore uses RESTORING phase_deadline minus its existing
3000ms phase duration; it does not assume the later log sample precedes STOPPING
expiry. Late completion requires the actual expiry tick and unchanged STOPPING
deadline. Reading this existing log occurs once after worker return, outside the
native packet path; it introduces no packet-loop write or timing adjustment.

Actual C core regressions cover completion before/exactly-at/after STOPPING
deadline, both direct completion tick and tick-first ordering, immutable deadlines,
stale/duplicate callbacks, no reversal or double restoration/delegation, and
release only after independent verified recovery and worker return/execution
exit in either order. The same native fixture C evidence predicate is extracted,
compiled and executed against injected valid/invalid numeric observations;
Python checks agreement, missing expiry, wrong generation/clock/state/deadline,
duplicates, missing/truncated evidence and conflicting native decision markers.
Private-process recovery can remain pending in the app trace: the existing host
broker/guard recovery assertions still run separately; a missing release is not
silently treated as verified recovery. Synthetic recovery requires release.

Production runtime, protocol, crypto, lease and every original timeout remain
unchanged. This corrects a source-proven fixture expectation, not the unknown
native delay or historical CID cleanup_failure/wifi_pending. Host Maven Central
HTTP429 is a separate dependency-resolution failure with no repository/mirror/
retry change. Local Windows C execution and strict Darwin object compilation
are not Apple Simulator or phone acceptance. The single correction CI must
independently validate Native/C runtime, full39, UI/QR and App/rootless packages;
required or unrun layers remain pending until exact artifact audit. Production
admission stays deny-all/injected; no HiCar/DMSDP/media interoperability claim.

Local review: actual Windows C owner core retained551 adapter/122 common-terminal
checks and added390 STOPPING deadline/lifetime checks; production deny-all passed.
The actual compiled fixture predicate and Python validator passed27 regressions
and agreed on24 archived owner cases across runs46136123466/46139195651. The
existing failure-evidence23, diagnostics16, matrix13 and cancellation4 suites
passed. Ten strict C11/Wall/Wextra/Werror Darwin object compilations passed for
aarch64/x86_64: owner core and tests in production/test modes, plus the extracted
native fixture predicate. These are cross-compiles on Windows; full Apple
framework compilation, linking and runtime remain CI gates.
