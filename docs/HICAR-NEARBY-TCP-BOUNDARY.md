# Authenticated FE35 continuation to owned TCP boundary

2026-11-28. Baseline dcde42a5c02a51ba4767badb6cb1d6a2121bcc2f / run46100533355
was independently audited by the coordinator. This change has new source and requires its own
combined owner CI; the baseline does not establish the new runtime path.

## Implemented boundary and ownership

The existing C accepted-CID transport now has an explicit
openhc_btstack_scan_wifi_inbound opt-in. The production owner exposes
configureContinuingAuthentication:trust:network:boundary: as an alternative to bounded
configureAuthentication:trust:keySink:. Neither has a deployed config/network provider.
Default FE35-only and existing bounded-auth behavior remain explicit.

Same-PIN real authentication still uses the existing Fe36AuthSessionBridge and crypto backend.
After ordered auth SENDs verify, C confirms the auth-CID close and unregister processing barrier.
The original FE35 CID remains owned and open. The existing owner executor drains endpoint Stop/
background/EOF, ticks the original owner/common state, and privately copies the one-shot session
key into OHCNearbyWifiTransport. The captured minimum owner/common absolute deadline is retained;
no new lease, guard, generation, connection incarnation or 240-second budget is created.

NearbyWifiJoin extends the SAME Fe35NearbyControlSession/cipher/stream decoder, through the
exported Fe35ControlBridge methods. Network readiness may remain pending. Resource-layer WiFi
request receives the pinned acceptance (channel3, role1, actual network frequency), or BUSY before
authentication / NO_CHANNEL for unsupported negotiation. Phone result confirmation gates the
injected provider's TCP listen operation. Only then is peer MAC requested; valid non-busy MAC
gates exactly one connection-info send with the actual bound TCP port. Duplicate successful result/
MAC do not create a second listener/info send. A duplicate request repeats the selected frequency.
Malformed negotiation fails closed; no raw capability/auth/network payload is logged.

C polls FE35 and the nonblocking TCP listener together. FE35 EOF/Stop wins before acceptance,
including when both descriptors are ready. Accepted TCP must match the trusted network provider's
explicit IPv4 association, then pass another serialized owner/common fence before its borrowed
key/TCP callback. FD and key cannot grant detached authorization. Replay and cancellation revoke
the private key; a volatile wipe clears the retained key and callback copy. Provider methods run
outside state locks and owner executor. Providers must be nonblocking and report actual cleanup
certainty, including partial listener creation; no implementation is enabled in deployment.

The TCP callback is synchronous, borrowed, and deliberately bounded: it does not transfer a live
TCP lease. C closes accepted TCP, provider listener/network, FE35 CID and registrations before
successful completion. Cleanup failure returns status failure plus cleanup_confirmed=false and
delegates the guard, even if the TCP boundary was previously observed. Boundary observation is
not final success and cannot mean absence of live resources. The existing exact-once guard/fence
semantics and production deny-all admission are unchanged.

## Protocol provenance and implementation limit

Read-only reference HEAD8132399bea6aa86d68da6d3e1d9e3e001c0a7643:

- core/session WirelessReceiverSession.kt: auth success/network readiness, resource request/result,
  startWifiPhase, onWifiControlListening, onPeerMac and PhoneConnected (~630-815).
- core/nearby NearbySession.kt: resource commands1/2/7 (outer4), WiFi tags1/2/3/5/6 (outer33).
- core/nearby DataChannel.kt: copied codec, with only unavailable raw-hex diagnostic removed.
- core/nearby WifiConnectionInfo.kt / WifiChannels.kt and WifiSetupTest: existing local port reused.
- core/session ControlLink.kt / ReceiverSession.kt: next encrypted WiFi control dependency.

This slice establishes the actual owned TCP accept boundary and retains Bluetooth until that
boundary. It immediately terminates afterward, so it implements neither upstream's continuing
post-TCP Bluetooth-close policy nor encrypted TCP ControlLink/ReceiverSession, business20, DMSDP
or media. Those require the next session/lease ownership integration. The borrowed callback must
not be advertised as transferred long-lived HiCar success.

## Validation and evidence

Executed locally on Windows:

- JDK17 / Gradle8.13 offline impacted JVM tests:80, failures0/errors0/skips0, including12 new
  NearbyWifiJoin tests and45 retained real-auth tests; log D:/orcafile/810-jvm.log.
- Portable real-loopback negotiation-driver matrix10 cases,219 assertions. Framing adapters
  are explicitly injected here; this is harness execution, not C/ObjC/Native runtime evidence.
- Negative terminal regression:7 close-command checks,12 INFORM checks,3 real-loopback proxy cases.
- Existing failure-evidence unit tests:6 passed. Python bytecode/shell syntax/diff checks passed.
- Zig strict C11 -Wall -Wextra -Werror compile of current production and Simulator C branches
  to Linux objects only. Narrow ObjC block/borrowed16-byte nullability declaration reproduction
  compiled to a macOS object, without Apple Foundation SDK. No POSIX/Apple runtime claim.
- Workspace notifier tests49 assertions: actual strict ok=true/result.messageId string receipt,
  invalid/empty/numeric/old/malformed/nonzero/ambiguous receipts, no fresh resend, atomic state
  locking, fixed150-minute model-failure deadline and30-minute gates. No real send was performed;
  the already delivered baseline notification was not resent.

Pending new CI: current-source Native tests/frameworks, strict deployment SDK compilation,
existing FE36 CID21 and10 new full Simulator cases (same-PIN crypto -> owner/C/ObjC/Native Nearby
packets -> loopback TCP boundary), retained process/owner/UI/QR/package checks. Markers:
FE36_CID_TRANSPORT_AUTH_CASES_OK=21, FE36_NEARBY_TCP_TRANSPORT_CASES_OK=10,
OWNED_TCP_CONTROL_BOUNDARY and BTSTACK_NEARBY_TCP_BOUNDARY_CLEANED. Cases cover readiness,
duplicates, Stop, original expiry, malformed/unsupported negotiation, wrong TCP association,
FE35 disconnect and provider cleanup failure. They have not run locally. Failure evidence is
persisted before assertions using existing finally paths and safe typed phases.

The Simulator uses a separately coded ObjC synthetic phone, same actual crypto port as baseline,
synthetic BTstack daemon/config/admission/lease, injected network and ordinary127.0.0.1 TCP proxy.
Advertised127.0.0.2 is synthetic phone network info; no alias/interface is configured. This is
software transport integration, not vendor peer, Bluetooth, Honor phone or iPad evidence.

## Preservation and next field gate

16 pre-existing tracked dirty files (14 unrelated plus two histories) retain exact SHA256 from
D:/orcafile/preservation-810-start.json. Both history suffixes remain byte-identical; histories
were not edited/staged. No upstream writes or identity/assets reads. Crypto sources/backends,
dependency pins, crypto-only reuse inputs and validation scripts unchanged; current frameworks
must rebuild with input tracking. No old framework reuse. Inert rootless DEB/macOS15/ldid -S route
and synthetic deployed provider remain unchanged.

Shortest software continuation: port encrypted ControlLink/ReceiverSession control processing and
explicit ongoing TCP/FE35/owner lease ownership, with revocable key use and the supported post-join
Bluetooth-close policy. Then business20/DMSDP/media follow. Before any real iPad field session,
the coordinator must authorize a concrete target window for trusted provider/config/BD_ADDR,
secure trust persistence, actual rootless owner launch/FD provenance/native Trial/guard recovery
proof and bounded device I/O. No device cooperation or hardware action was used in this slice;
production remains deny-all and no mobile-UID/PONG shortcut is introduced.
