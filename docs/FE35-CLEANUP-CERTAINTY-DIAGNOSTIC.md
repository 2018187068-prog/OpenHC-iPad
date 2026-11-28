# FE35 cleanup certainty diagnostic gate

This change is diagnostic, not a demonstrated production fix. Run 46141656304
at 571c85569e1e73a09d05ca186c0dcdbab72fdb51 returned (1,0,1) and
CLEANUP_UNCONFIRMED after AUTH_STREAM; run 46145038014 at
b763c780be3f1c8e5bebe16938ca375182e43fa2 returned (1,1,1) and AUTH_STREAM.
Both archived proxy traces reach the same cleanup command sequence and
daemon-finished. Those observations do not prove which final C cleanup input
failed in the earlier run.

The production confirmation expression is unchanged and shared through
Fe35CleanupCertainty.h. The C executable tests the actual shared predicate:
confirmed resource cleanup, cleanup/barrier failure, fd close failure, pending
registration, existing uncertainty, unsettled control/auth CIDs, and unowned CIDs.
These are predicate tests, not socket teardown tests.

The existing Simulator socket matrix retains its safety assertions and adds
four injected failures: auth close ACK, auth listener barrier, control close
ACK, and final cleanup barrier. The known auth-CID peer-close case requires
protocol failure with confirmed cleanup only when its precise native inputs
match the independently injected complete cleanup transaction. It cannot pass
by accepting either cleanup boolean. Each new failure case requires its exact
native inputs, failed typed completion and guard delegation. Pending-stop and
the existing cleanup-failure cases remain required. All 43 matrix cases retain
process/thread/socket isolation certificates and nonzero failure propagation.

One completion-boundary record prints only numeric flags and a fixed stage:
cleanup_ok, close_ok, registration_pending, cleanup_uncertain, control CID
owned/opened/disconnected, auth CID owned/disconnected, first cleanup failure
stage. Stages 1/2/3 are auth SDP/listener/barrier; 4/5 auth close write/ACK;
6/7 control close write/ACK; 8/9/10 control SDP/listener/barrier; 11 fd close.
Zero means no recorded cleanup operation failure. No payload, identity or key
is logged; no packet-loop file writes or production deadline changes occur.

Actual reference source reads, clean pinned repositories:

- OpenHC 8132399bea6aa86d68da6d3e1d9e3e001c0a7643,
  core/session/src/main/kotlin/io/github/gcbond/openhc/core/session/:
  WirelessReceiverSession.kt:354-359 distinguishes auth close before/after
  authentication; ControlLink.kt:30-33 transfers a key once and :52-54 builds
  the preauthenticated WiFi link; ReceiverSession.kt:492-506 gates DMSDP by
  business/channel/tag and queues a request until its real listener is open,
  :531-540 gates control-close continuation, :344-351 routes DMSDP closes.
- Showcase ce9d1d50758f67307deb3f00c901a8e82894930c,
  btstack-rootless/platform/daemon/src/daemon.c:515-537 removes owned RFCOMM
  services/CIDs on client teardown and :1611-1625 tracks open/close ownership;
  socket_connection.c:321-332 dispatches parked packets by type/channel/length.
  None of these makes an auth failure itself proof of cleanup completion.

Local Windows uses Zig to execute the shared C predicate. Darwin arm64/x86_64
and Linux arm64 strict transport builds are compile-only. Full POSIX transport,
Native/ObjC/Simulator, SDK, QR/UI and DEB gates require the single owner CI run.
Production admission remains deny-all. ReceiverSession/DMSDP wiring is deferred
until this diagnostic gate is audited; no iPad or actual HiCar acceptance is
claimed. The later connection point is the authenticated WiFi channel-3
business-20/TAG_DMSDP request and listener/connection lifecycle under the same
owner lease.
