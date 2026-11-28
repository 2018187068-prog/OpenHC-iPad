# Owned encrypted Nearby TCP control slice

Baseline dcfe9e8d95b892b8abbca159c97481c892301ca6 / run 46130175327 was
artifact-audited before implementation. Published owner/host ZIP SHA-256 and BUILD
identities match; JVM105/Native103 have zero failure/error/skip, all21 auth+10
Nearby cases passed with process/thread termination certificates, actual Darwin
listener8 passed, retained owner/common/process gates, UI70/QR3 and App/inert
rootless DEB layouts passed. This proves synthetic software acceptance, not a phone
or deployed provider. The former intermittent background/ready_stop cause remains
unproven even though these cases passed in this exact matrix.

## Protocol and ownership

Read-only reference: OpenHC 8132399bea6aa86d68da6d3e1d9e3e001c0a7643:

- core/nearby/.../NearbySession.kt start: WiFi sends plaintext connectId then
  TLV1(version2), TLV3(device text), TLV5(encryption on). No Bluetooth-address TLV7.
  Same root/const frame cipher, fragment decoder and socket codec as FE35.
- core/session/.../ControlLink.kt wifi/takeSessionKey and ReceiverSession.kt
  preAuthenticated setup: PAKE key is separately retained for business20/DMSDP;
  it is not the Nearby frame cipher key. No WiFi reauthentication.
- ReceiverSession.kt socket selection/start listener: a business20 acceptance
  needs the real DMSDP listener and session. This slice rejects business19/20 and
  unavailable socket businesses with exact status1/port0/protocol0 responses.
- NearbySession.kt handleWifiLink: tag5 disconnect sends tag6 ACK before ending.
- WirelessReceiverSession.kt onClosed/onIoError and PhoneConnected routing:
  remote FE35 closure after WiFi join is settled; joining does not proactively
  close Bluetooth. Before join the existing fatal-close behavior is retained.

configureLiveAuthentication is an internal opt-in alongside the unchanged
configureAuthentication and borrowed configureContinuingAuthentication APIs.
The existing native worker owns accepted TCP, FE35 and provider resources until
protocol disconnect, Stop/background, foreground EOF, TCP peer death, original
expiry or failure. There is no detached fd, key callback, lease or fresh budget.
Owner generation, common generation/incarnation and immutable original absolute
deadline remain authoritative; each live batch drains owner cancellation on its
serial executor and C polls cancellation before network writes. The private PAKE
key moves once from auth to adapter to NearbyTcpControlBridge; source copies are
wiped, live mode denies the borrowed sink, and all terminal/revoke paths close
the cipher and zero the retained key. Stale generations/incarnations, replay,
time reversal, malformed framing and original expiry terminate the session.

Remote FE35 close is consumed exactly once after TCP join; later cleanup does
not issue another close for that already confirmed CID. Its registration still
uses the existing unregister/query barrier. Otherwise final FE35 close still
requires its typed ACK. TCP close/network-provider failure or uncertain daemon
cleanup cannot produce success and delegates the independent guard as before.
No power, trust, authentication, admission or lease safety rule is relaxed.

## Validation and boundary

Local Windows actual runtime: JVM117 (prior105 + common7 + JVM socket5), zero
failure/error/skip. Includes real owned loopback TCP, fragmented/coalesced frames,
encrypted business rejection/disconnect ACK and key cleanup on owner cancellation,
peer EOF and original expiry. One test runs the independent Python/OpenSSL phone
driver over the real JVM production bridge socket; it checks exact WiFi start and
encrypted wire replies using the existing pinned synthetic key material.

Portable matrix13, cancellation-order4, failure-evidence6, negative-command7 /
INFORM12 / loopback3, WiFi diagnostics6, existing negotiation-driver10/221 and
listener8 passed. Syntax/diff and dirty preservation checks are required. Existing
Kotlin expect/actual/cinterop warnings remain visible; Native is disabled on the
Windows host and is not reported as run locally.

Existing Zig strict C11 -Wall -Wextra -Werror preflight compiles current production,
Simulator and transport C modes for aarch64/x86_64 Darwin and aarch64 Linux-musl.
The new actual-production tcp_control_stream/batch test also cross-compiles for
Darwin/Linux. This is compile-only, not Apple SDK/native runtime evidence.
The Apple gate runs its real-loopback C pump cases (backpressure/cancel, settled
FE35 plus ACK, rejection/closed peer), current Native framework/common tests,
ObjC generated API and full isolated Simulator matrix: original31 plus8 live
cases (disconnect, post-join FE35 close, TCP EOF, Stop, background, owner EOF,
original expiry, malformed CRC). Failed/unrun cases remain nonzero with safe
metadata/evidence; no suite success is printed for partial acceptance.

## Remaining join and field gate

This is a continuing owned encrypted Nearby ControlLink subset, not a full
ReceiverSession, DMSDP/media implementation or transferred ongoing TCP lease.
The shortest next software join is the pinned preauthenticated ReceiverSession
business20 listener/DMSDP lifecycle under this same owner/deadline/key, then its
supported HiSight/media dependencies. No fabricated business20 listener is used.
The deployed network/provider, root-only admission/FD provenance, real identity/
trusted config/secure persistence and native recovery integration remain field
blockers. Production still denies admission and has no enabled hardware provider;
no iPad cooperation is needed for the current software gate. Rootless Theos,
GitHub macOS15 and ldid -S remain the packaging route. No device/identity/radio/
installation/helper/pins/Trial/tools work occurred.
