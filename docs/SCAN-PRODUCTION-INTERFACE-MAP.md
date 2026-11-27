# Scan entry: production interface review (2026-11-27)

## Latest implemented map — owner slice, not deployed or Apple-validated

This section supersedes the historical missing-join descriptions below where
software now exists. Production activation is still deny-all; restricted owner
caller policy and the target-native Trial lease actor remain missing. Keep the
Dopamine/rootless Theos DEB/ldid route; no Developer certificate/profile/Team ID
is required. Full evidence and commands: SCAN-OWNER-INTEGRATION.md.

| Boundary | Current implementation | Authority / remaining validation |
| --- | --- | --- |
| Foreground Start/Stop/background | ScanOwnerForeground.m, dedicated connected fd, fixed bounded grammar, main-thread presentation, local revoke before close | Not wired to installed synthetic demo; does not connect/deploy itself or infer authority |
| Peer / endpoint freshness | ScanOwnerPeer.c: getpeereid + full LOCAL_PEERTOKEN, nonce, root-owned canonical endpoint/ancestors, dev/inode/policy epoch; compare every tick/read | Darwin source not yet Apple-compiled; LOCAL_PEERTOKEN last_pid lookup is not immutable per-message credential/initial exec proof |
| Admission / serialized fence | ScanOwner.c: one generation/connection, bounded partial/idle framing, stale evidence cancels; production admit=false | Test-only injection is compile-time; same UID, PONG, role, guard marker insufficient; target launch/connection capability policy absent |
| Lease / independent guard | OHCScanLeaseAdapter trusted in-memory protocol; core emits arm/takeover/one heartbeat/restore/delegate effects with bounded acks and immutable deadline | Mirrors Trial semantics; only fake effect actor in fixture. No native root lease daemon, controller implementation or deployed plist |
| Native/common worker | ScanOwnerRuntime.m: serial common access, dedicated worker queue and stop pipe, captured owner/common generations, retained binding/session/sink | Real openhc_btstack_scan_inbound and fe35_scan_notify; fresh bridge from trusted internal config, never endpoint identity/path |
| Pairing and scan handoff | Actual RFCOMM + SDP callbacks and common PAIRING_READY required; actual takeAuthHandoffGeneration preserves PIN | PONG cannot ready; AUTH_HANDOFF is not completed authentication; no production identity loaded |
| Revoke / return / recovery | CLEAR before cancellation; typed returned/cleanup_confirmed/status, independently known worker execution return, deadline and verified guard recovery gate release | CLEANED has no recovery power; unknown delegates once/stops heartbeat, retains fence and sink; no concurrent OFF/restore |
| Offline integrated fixture | scan-owner-sim-fixture.m + original FE35 transport harness: foreground socketpair, actual native/common, UIKit CPU QR rendering, 11 cases | Only OS admission/daemon/lease effects fake. Prepared for Apple, not compiled/run here; Python mock is not substituted |

Actual local execution: Windows/Zig production deny-all and 551 owner assertions,
6 crypto-reuse tests, JDK17 offline common session 12 tests with zero failure/
error/skip. Linux native/owner strict C11/Werror cross-compilation is compile
evidence only. Apple collector/runtime, native transport integrated cases and
UI lifecycle remain pending. Combined entry check-scan-owner-apple.sh rebuilds
current frameworks and runs affected Darwin/native/common/UI checks, retaining
original FE35/scan/QR assertions; does not build or replace the healthy helper.
No CI/push/device/identity/radio operation occurred.

## Historical interface review (before the integrated owner source)

Decision: **production connection is blocked by missing caller policy and owner/lease adapter**.
This review does not enable a backend or extend the fixed PING helper. It is a
source/interface review of the dirty working tree, not device or Apple validation.

## Actual paths and missing joins

| Boundary | Existing source and actual contract | Missing production join |
| --- | --- | --- |
| UIKit Start | `theos/scan-ui/ScanDemo.m`: `syntheticDemoProvider` constructs the hardcoded synthetic host/address; `start` starts a local common session, then a one-second timer calls synthetic `ready` | No production provider, owner request, or real listener callback |
| UIKit helper | `ScanDemoController.probeIndependentHelperWithCompletion` calls `ScanHelperClient.pingWithTimeout` on a utility queue, returning to main | PONG is diagnostic only; it does not call ready or grant authority |
| Root socket | `theos/scan-supervisor/main.c`: root runtime/lock/socket checks, `getpeereid` mobile UID/GID, exact five-byte PING/PONG; fixed launchd plist | No accepted Start/Stop protocol or app-specific authorized-caller policy; any qualifying mobile-account process is in the PING trust scope |
| Owner observation | `theos/session-owner-probe.c`: socket owner/inode checks and kernel peer PID (`LOCAL_PEERPID` on Darwin) | This connects to observe a socket server, not authenticate an accepted UIKit client; no executable/signature policy or lifetime-bound caller authorization |
| Mock coordinator | `scripts/scan-supervisor.py`: callers supply `peer_identity` and `role` to `serve_peer`; synthetic mode routes dual-ready/cancel/cleanup actions, disabled rejects before Start side effects | No OS acceptor or lease actor consumes these actions; Python names, mode and scope are not security boundaries |
| Lease entry | `scripts/btstack-power-trial.py`: host-side `Trial.preflight -> arm -> takeover -> PowerProtocol.run(on_working)` | No on-device owner daemon or app lifecycle handle; this SSH driver must not be imported/executed by UIKit or the PING service |
| Guard ownership | `Trial.arm` takes `REMOTE_BASE/active`, creates root-private state, writes a fixed 240-second deadline, loads independent recovery job; `Trial.heartbeat` alone updates every two seconds | A future actor must preserve this one owner/recovery model and current ownership/session checks; UI must not write guard files, renew the absolute deadline, select run_dir, or signal services |
| FE35 worker | `theos/fe35-control-bridge.h`: borrowed `fe35_scan_binding` and `fe35_scan_transport`; `fe35_scan_notify` synchronously calls the common model and sink | Owner must retain binding/session/sink through worker return, serialize calls, and foreground-deliver only its current generation; no app/root event channel exists |
| Real readiness | `btstack-probe.c:transport_inbound` registers RFCOMM, checks status/channel, then registers FE35 SDP/status/handle before each ready callback | `openhc_btstack_scan_inbound` has only a Simulator fixture caller in this tree; root-owner production binding absent |
| Cancellation | `scan_poll` checks `stop_fd`/tick during bounded transport waits; teardown clears thread-local current_scan before unregister/close | No app IPC Stop/background/disconnect to this fd; thread-local recursion protection is not a process-wide single-owner lock |
| Recovery | `PowerProtocol.run` releases its lease unless `LeaseUncertain`; `Trial.run` stops heartbeat and delegates uncertain remote exit to guard; normal path requests `Trial.restore` and verifies restoration before disarming | Native typed completion now exists; no authorized owner adapter maps it to lease/guard actions |

## Critical completion and authentication distinctions

- `btstack-probe.c:guard_ready` reads READY/result/deadline markers using the supplied
  path. It is neither caller authentication nor a root-owned path/lease capability
  verifier. Its use is scoped to the trusted CLI/fixture caller today. A future
  acceptor must never accept this path or guard-ready truth from a UI frame.
- Native `transport_inbound` revokes pairing before cleanup and returns failure
  when cleanup is unconfirmed, but **always emits CLEANED before returning**, even
  for `CLEANUP_UNCONFIRMED`. This currently means worker teardown completed, not
  that every remote resource release was confirmed. The Simulator fixture even
  requires this notification in its cleanup-failure case.
- Mock `ScanSupervisor` uses CLEANED to request guard restoration. Directly wiring
  these two identically named events would lose cleanup certainty. An adapter
  now receives `fe35_scan_completion` by value from `openhc_btstack_scan_inbound`:
  `returned` is true only on the caller side of a synchronous return, `status`
  preserves the former protocol result, and `cleanup_confirmed` is independent.
  A zero-initialized result is not a completed worker; if it never returns, the
  owner must handle that uncertainty independently. This does not claim remote
  process exit or grant permission to release power/restore. No production
  restoration policy/adapter is implemented here.
- `cleanup_confirmed` means the existing teardown of known resources succeeded,
  with CID close acknowledgement/ordered unregister barrier where applicable,
  no unresolved initial registration, no uncertain bridge-listener operation,
  and successful local socket close. It is not a remote SDP absence, radio-close
  or process-exit proof. False includes rejected/not-attempted/uncertain cleanup.
  CLI status and cleanup commands are unchanged. The fixture checks returned
  true/cleanup true for ready_stop and ready_timeout, and returned true/cleanup
  false for cleanup_failure and pending registration cancellation; its existing
  pairing/close/count/protocol assertions remain intact. The Python socket
  harness separately checks the typed trace occurs after CLEANED.
- Host `run_inbound_transport` confirms SSH process exit separately; timeout,
  SSH loss, output overflow before exit or cancellation becomes `LeaseUncertain`.
  Host exit status is not a substitute for a future native cleanup result.
- The dirty synthetic patch hides injection methods from the production header
  and makes factory naming explicit. Objective-C visibility is API hygiene, not
  OS authorization. Python read-only properties/scope tags are also not authority.

## Smallest safe follow-up implementation and focused acceptance

1. Resolve and implement a separate restricted owner endpoint caller policy using
   target-supported OS peer evidence and an explicit app admission rule. The
   repository does not establish an app-signature/entitlement rule; do not invent
   one or treat mobile UID, executable name, client role, synthetic scope or PONG
   as sufficient. Bind admission to connection lifetime; reject before lease
   creation, with root-owned endpoint/ancestor checks and one owner. Start/Stop
   only, no arbitrary paths, commands, identity contents, or service names.
2. Before transport is connected, provide a lease actor adapter preserving the
   existing exclusive lock, ownership/session preflight, independent guard, sole
   heartbeat writer and fixed deadline. It must expose bounded cancellation and
   explicit confirmed/unknown completion; no UI callback owns restoration.
3. Then connect one off-main serialized common session/native worker: captured
   generation, dedicated stop fd, memory-only event sink, confirmed RFCOMM+SDP
   readiness, and typed teardown result. Stop/background/disconnect/expiry revoke
   QR before cancellation; unknown exit stops heartbeat and delegates to guard,
   never a concurrent OFF/restore. No production identity is assumed or loaded
   by this review. Backend remains disabled until these joins are validated.

Focused tests required for that slice: unauthorized same-UID caller; forged
role/guard/path; changed socket inode or executable policy evidence; disconnect
and PID reuse; competing owner/reconnect; worker lifetime through final callback;
Stop during each partial registration and fragmented read; stale generation;
PONG never ready; both actual registrations required; CLEAR before teardown;
CLEANED plus cleanup failure cannot authorize release; timeout/exit unknown
delegates once; failed guard readiness never starts transport; immutable absolute
deadline, sole heartbeat, no duplicate recovery. Use injected OS/lease adapters
offline, then actual Darwin peer/worker tests and UIKit lifecycle in the next
authorized combined Apple validation. Mock tests alone cannot validate OS policy.

Review evidence: existing synthetic supervisor 15-test suite passes locally on
Windows; new UIKit delayed-PONG assertions remain uncompiled/unrun on this host.
The follow-up completion slice changes the native header/worker, Simulator fixture
and host harness, plus a common-session comment clarifying CLEANED. Strict C11
Werror Linux cross-compilation/link and Simulator-define C compilation pass on
Windows with existing Zig; no Linux or Apple runtime pass is claimed. Apple
ObjC/common integration and all eight socket cases still require actual runtime
validation. No commit/push/CI, device, credentials, identity, radio or Showcase
action occurred.
