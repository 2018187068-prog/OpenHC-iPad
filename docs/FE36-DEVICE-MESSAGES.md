# Receiver device messages and explicit HiSight boundary

This increment extends the existing preauthenticated business20/channel3/DMSDP
receiver. It does not provide a HiCar-capable package or a media sink. Production
admission remains deny-all, with the same original owner/generation/connection,
absolute deadline and private PAKE session key. No new identity source is used.

## Implemented closure

The existing ScanReceiverConfig supplies HostIdentity and Bluetooth address; the
existing authorized bridge input supplies the device ID. getsockname/getpeername
on the accepted Nearby connection supply the actual IPv4 endpoints. Configuration
is accepted once, before start, only for the same device ID.

Encrypted control payloads accept bounded `$` records: unsigned BE32 module, signed
BE32 type, BE16 data length. The entire payload is framed before applying commands,
with a 32-record limit. Module3/type-1 handles EA commands101..105. Device101 uses
strict UTF-8/JSON, integer deviceType, optional object properties, and a stable peer
ID within the connection. The first valid101 gets exactly one encrypted local101
with the pinned field order and only model property2003. Service102/103 are
validated without advertising local services; request104 requires a four-byte
mask and produces no102 because display, speaker and microphone are absent.
Command105 validates the four-byte notification and does not invent disconnect
semantics. Events use fixed names; JSON errors omit peer text and causes.

Encrypted SET_PARAMETER with TimeServerPort, TimeUsHigh, TimeUsLow and decimal
CSeq receives an encrypted CSeq-only200 on the same control connection. This is
an ACK, not a running UDP time service or a synchronized media clock. Existing
zero-body, duplicate-header and Content-Length checks remain. No deadline changes.

Module5/type-1 EA101 plus an exact EA port1..65535 emits DMSDP_HISIGHT_REQUIRED,
then the bridge clears its private key and the native owner closes endpoints.
Missing configuration and unsupported capabilities also terminate. Processing
stops at that boundary even with coalesced records/control frames. No display
capability, HiSight connect, PLAY, video-ready or audio-ready is fabricated.

## Actual reference interfaces

Read-only OpenHC revision8132399bea6aa86d68da6d3e1d9e3e001c0a7643:

- core/dmsdp/src/main/kotlin/io/github/gcbond/openhc/core/dmsdp/DeviceMessageHandler.kt:
  handle, onDeviceInfo, localDeviceObject, parseService, parseDisplayPort.
- The same directory's DmsdpConfig.kt: default null display/speaker/mic; explicit
  caller identity/IP and property2003. Framing.kt: DeviceRecords header/size.
- DmsdpSession.kt: onDeviceRecord, isTimeSyncRequest, rememberPhoneTime, sendText,
  sendRecord. Only its control ACK is implemented here; no audio clock is claimed.
- core/session/src/main/kotlin/io/github/gcbond/openhc/core/session/ReceiverSession.kt:
  beginHiSight requires the original key, business20 remote host and actual
  sinkAdapter; handleHiSight gates video/remote connections and PLAY.
- core/hisight/src/main/kotlin/io/github/gcbond/openhc/core/hisight/HiSightReceiver.kt
  requires AccessUnitSink, explicit HiSightConfig, control/video/remote lifecycle.
  HiSightConfig.kt requires actual dimensions/fps/dpi; inputs default disabled.

Showcase revisionce9d1d50758f67307deb3f00c901a8e82894930c, daemon.c515-537 and
socket_connection.c321-332 retain serialized ownership/ordered dispatch. This
increment introduces no second owner or detached connection lifecycle.

## Validation and next dependency

Common tests exercise byte headers, malformed/fragmented records, identity/config
binding, one101/no echo,102..105, strict JSON, encrypted time ACK, unchanged lease,
display-port validation and termination before later coalesced messages. The JVM
real three-socket peer uses Python/OpenSSL to verify encrypted101/no102/no repeat101,
time ACK and explicit display boundary. Common tests also run on Native in owner CI.
The existing47-case native matrix stays intact; its no-export-key DMSDP peer does
not claim to cover encrypted device messages. No synthetic run is device acceptance.

Next is a real Apple AccessUnitSink/decoder/render surface with explicit supported
screen/video dimensions, fps and dpi, plus the pinned HiSight control/crypto/video
protocol port. JVM java.security/SecureRandom/TimeZone/synchronized dependencies
cannot be copied into commonMain as if Apple implementations existed. Before
advertising display service, prove sink initialization/error/backpressure/shutdown
and same-owner socket/key cleanup. iPad validation then needs read-only OS, Dopamine,
device/screen and relevant API capability evidence; supply an audited run/SHA/BUILD
and exact DEB digests before separately authorized installation or wireless work.
The foreground acceptance sequence remains FE35 dual-ready -> same-session QR/PIN
-> Honor scan -> Nearby/FE36 -> WiFi/TCP -> DMSDP -> real HiSight media.
