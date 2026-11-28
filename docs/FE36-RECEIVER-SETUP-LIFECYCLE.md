# Preauthenticated WiFi ReceiverSession setup slice

This is a software lifecycle/protocol increment, not a media receiver or device
acceptance. Production admission stays deny-all, with no network provider,
identity discovery, installation, helper/pins or radio operation added.

## Prior diagnostic gate

Run46150577638 attempt1 at c57f58848f5878c5996ea0cf6ba6ca088e6bc20a
was audited from its two published-digest-matched ZIPs and exact BUILD identities:
required host/owner/aggregate success, alternate app route intentionally skipped,
JVM117 and Native110 clean, FE36 43/43 passed and independently safely isolated.
Known auth peer close recorded final native facts 1,1,0,0,1,1,1,1,1,0 and typed
completion 1,1,1,0. Four injected close/barrier failures recorded their precise
stage5/3/7/10 facts and completion 1,0,1,1. CPU/system QR, UIKit70, actual SDK
deployment compiles, App DEB and inert owner DEB passed. This validates the current
distinction between protocol failure and cleanup uncertainty; it does not explain
the historical intermittent cleanup input in run46141656304 or prove real HiCar.
Full local evidence is D:/orcafile/ci-evidence-46150577638/audit-complete.json.

## Shortest implemented closure

The existing live owner continuation now recognizes only an encrypted,
handshake-complete business20/channel3/exact ASCII DMSDP request with TCP support.
Business19, other channel/tag and non-TCP remain refused. No second authentication,
owner, detached key or deadline is created. The existing single-use PAKE key
remains private in the original NearbyTcpControlBridge and is used directly for
DMSDP AES128-CTR; root material remains confined to Nearby framing.

The original worker creates a real nonblocking DMSDP_SESSION IPv4 listener on the
same local address as its accepted Nearby TCP. Only a successfully bound/listening
socket supplies the port response; up to eight pending duplicate requests receive
that same port, retaining their original message/resource outer type. Each accepted
endpoint must match the original TCP peer address and is single-incarnation.

Actual business20 bytes use the pinned 0x7f/EA/module1/16-byte/CRC16-ARC negotiation.
Only after the separate real DMSDP_CONTROL listener exists does the session reply
with its port. Control accept sends plaintext OPTIONS advertising TCP keepalive
only. A valid plaintext selection receives plaintext 200 before CTR switches;
CTR uses fresh 16-byte IVs and the original key. TCP keepalive follows the pinned
one-second/ten-miss semantics without extending the original absolute deadline.

Nearby EOF/disconnect is terminal until business20 listener readiness and port
response. Afterwards Nearby is shut down but its descriptor stays owned by C
until final close, while the same worker/lease continues DMSDP. Session EOF is
allowed only after a complete negotiation and control-listener readiness; partial
EOF and pre-media DMSDP control EOF terminate. Extra connections, wrong peers,
malformed CRC/framing, unsupported UDP selection, stale owner/time and Stop all
fail closed. Bounded queued writes retain offsets through EAGAIN and are wiped;
every bounded worker I/O turn revalidates on the original serialized owner.
Cancellation revokes the key and closes both endpoint pairs; any close uncertainty
feeds the existing native cleanup result and delegation, never inferred success.

## Explicit next dependency

Device/service binary records and non-keepalive encrypted messages terminate with
the fixed DMSDP_CAPABILITY_REQUIRED boundary and key revocation. No service,
display, audio or media readiness is announced. The next software join is pinned
DeviceRecords/DeviceMessageHandler time-sync/device-info/service routing with
explicit already-authorized identity/config inputs, then DisplayPortAnnounced to
HiSight and real media sinks. This slice is not the complete upstream ReceiverSession.
No iPad interaction is required to audit the current software gate.

Actual hardware acceptance remains: same-session FE35 dual-ready -> QR/PIN ->
Honor scan -> Nearby/FE36 -> trusted WiFi association -> TCP -> DMSDP/media.
When software reaches that boundary, preserve an exact audited package SHA and
run/BUILD, ask the user to identify iPadOS/Dopamine/BTstack API versions through
read-only local evidence, then perform only explicitly authorized foreground
same-session steps. Capture fixed stage/result/cleanup booleans rather than keys,
PINs, identities or packet payloads, and stop on unsupported platform/API facts.
Neither of the current inert/synthetic packages is an operational HiCar package.

## Actual pinned reference reads

OpenHC8132399bea6aa86d68da6d3e1d9e3e001c0a7643, under
core/session/src/main/kotlin/io/github/gcbond/openhc/core/session/: ControlLink.kt
30-33 and52-54 transfer one key into preauthenticated channel3; ReceiverSession.kt
230-255 associates real accepted DMSDP endpoints,492-506 gates business/channel/tag
and defers port responses,531-540 permits control-close continuation only after
listening/answer,344-356 separates session/control EOF,583-607 routes the real
control listener and later DisplayPortAnnounced. WirelessReceiverSession.kt354-359
distinguishes authenticated auth EOF from auth failure.

OpenHC core/dmsdp/src/main/kotlin/io/github/gcbond/openhc/core/dmsdp/:
Framing.kt13-100 defines session wire/CRC/negotiation; DmsdpSession.kt342-437 defines
session/control parsing and plaintext-ACK-before-encryption,566-585 defines OPTIONS
and CSeq; KeepAlive.kt5-56 defines TCP keepalive; AesCtr.kt8-17 specifies same
16-byte key, random IV and full 128-bit big-endian counter. DmsdpConfig.kt46-53
allows disabling UDP and defaults platform0/retry160. These files were read for
this implementation; local reference repositories remain clean.

Showcase ce9d1d50758f67307deb3f00c901a8e82894930c:
btstack-rootless/platform/daemon/src/daemon.c515-537 removes per-client owned
RFCOMM resources; socket_connection.c321-332 dispatches ordered type/channel/length.
Neither supplies a new owner lease or a remote-cleanup guarantee for TCP/DMSDP.

## Build and verification boundaries

The pinned OpenSSL archives, original native/crypto adapter and reuse guards stay
unchanged. A small current-source adapter uses CommonCrypto AES-ECB with explicit
full BE128 CTR carry, following pinned common/crypto/AesCtr.kt46-72 and120-126;
it is built for both actual Apple SDKs before K/N linking. JVM uses JCE AES/CTR. Common tests include an
independent NIST SP800-38A F.5 vector, protocol/fragments/duplicates/EOF/generation/
deadline/crypto-rejection/capability tests. The existing JVM real-socket suite now
also runs an independent Python/OpenSSL peer through two real listeners, retains
DMSDP after Nearby EOF, verifies plaintext OPTIONS/200 and encrypted keepalive,
and independently checks key/socket/thread cleanup. These are synthetic peers.

The consolidated owner CI retains all43 cases and adds four real C/ObjC/Native
socket cases: setup/control EOF, Stop, malformed session CRC and duplicate session
connection (47 total,12 live). Native common tests validate the same CTR vector.
Actual production socket-helper loopback tests cover both endpoints, backpressure,
wrong peer, duplicate and failed close; the production C pump also proves detached
Nearby EOF retains the original expiry. Windows Zig crosscompiles are compile-only.
SDK/CommonCrypto/ObjC/Native, POSIX runtime, QR/UI and DEB evidence for the new SHA
must be audited from the single owner run; no prior SHA's gate transfers to it.
