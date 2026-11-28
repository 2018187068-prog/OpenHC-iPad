# HiSight video leg and Apple sink

This is a real video-data-path increment, not full HiSight or HiCar activation.
The DMSDP device/service gate at revision89950ed was audited separately. Its
empty display/audio service list and DMSDP_HISIGHT_REQUIRED boundary remain in
force: the original owner has no HiSight control/SETUP/PLAY socket assembly yet.
The new pure protocol and sink objects cannot open sockets or admit a session.
No synthetic test is phone interoperability or on-device acceptance.

## Actual implementation

The fixed OpenHC8132399bea6aa86d68da6d3e1d9e3e001c0a7643 AccessUnit and
video/VideoDepacketizer are ported to commonMain. They parse BE32-sized RTP packets,
CSRC/HiSight byte-counted extensions, marker-completed PES, its nonstandard PTS and
optional0x8e header, and ES-only IV16/AES-CTR ciphertext. They preserve unsigned
timestamps, the64999 sequence wrap and whole-frame resynchronization after gaps.
Packet/PES size remains bounded at10MiB. copyInto replaces JVM arraycopy, the
existing platform op14 implements BE128 CTR, and explicit close wipes key/scratch.
Borrowed decrypted ES is cleared after the synchronous consumer returns.

HiSightVideoStream is a synchronous pure adapter, not a new ReceiverSession or
owner. It accepts at most65536 bytes per call, rejects partial EOF and terminates
on parser/sink failure; reentrant cancellation prevents a later coalesced frame.
Its raw key constructor is a protocol-library input, not an admission mechanism.
Live assembly must occur inside the original receiver owner using its private key,
original generation/connection/absolute deadline, and revocation/close ordering.
That assembly is deliberately not claimed by this increment.

OHCAppleVideoSink implements the actual exported HiSightVideoConsumer. Its caller
provides an AVSampleBufferDisplayLayer and explicit maximum decoded dimensions;
there is no assumed iPad screen profile. The shared production C Annex-B parser
validates the whole AU before decoder changes, bounds NAL count256 and rejects
malformed lengths/types. SPS/PPS make a CMVideoFormatDescription; actual dimensions
must fit the supplied limits before VideoToolbox creation. After initialization,
format changes or gaps, non-IDR frames are safely dropped until a new IDR.

Each accepted slice unit is converted to AVCC and passed to a real synchronous
VTDecompressionSessionDecodeFrame with both asynchronous and temporal flags clear.
The actual decoded CVPixelBuffer is size-checked and wrapped in a ready image
CMSampleBuffer. Only a nonfailed, ready display renderer is enqueued; backpressure
is counted as a drop. Decode/enqueue/drop counters are distinct: a true callback
does not mean an image was displayed. No fake pixel buffer or media-ready event.
DisplayImmediately renders available frames without pretending that the prior
DMSDP time ACK established a synchronized media clock.

close is idempotent, invalidates the decoder, releases retained format/image and
clears the layer; failed input is sticky. No asynchronous decode callback outlives
DecodeFrame. A receiver must still observe its original cleanup protocol; sink
close is not an independent proof of socket/listener/barrier cleanup certainty.
The synchronous platform call cannot be preempted by a Kotlin deadline check;
on-device decode latency/cancellation needs evidence before live activation.

## Source and API evidence

Read the actual fixed source, not citations alone:

- core/hisight/src/main/kotlin/io/github/gcbond/openhc/core/hisight/AccessUnit.kt:
  borrowed buffer contract, NAL types and90kHz PTS.
- The same directory's video/VideoDepacketizer.kt: feed/finish, parseFixedHeader,
  beginPayload/onSequenceGap, deliver, grow and10MiB bounds.
- crypto/AesCtr.kt: authentication key reused without derivation, IV16 and BE128
  increment. This port calls the already audited CommonCrypto adapter.
- HiSightReceiver.kt: ANNOUNCE/crypto, capabilities, SETUP, required connections,
  PLAY, feedVideo and shutdown. Those control/input pieces are NOT ported here.
- HiSightConfig.kt and ReceiverSession.beginHiSight/handleHiSight: actual explicit
  capabilities, original business20 peer/key, sinkAdapter and ordered connections.
- Fixed Showcasece9d1d50758f67307deb3f00c901a8e82894930c per-client resource cleanup
  and ordered parked-packet dispatch remain the ownership basis; no new owner.

Official Apple API documentation was fetched and read for DecodeFrame flags,
AVSampleBufferDisplayLayer, AVSampleBufferVideoRenderer and the queued-rendering
protocol. With both decode flags clear, the output callback completes before
DecodeFrame returns. The queued-rendering protocol does not expose status, so the
sink queries the actual renderer/layer status separately. iOS15 legacy layer
wrappers isolate only the relevant deprecation warnings; iOS17+ uses its renderer.
Exact downloaded documentation and source hashes are retained in the external
delivery evidence, not copied into a payload diagnostic.

## Verification and explicit gaps

Common tests retain the reference33 video vectors:29 prototype comparisons with
original split/error expectations and hashes; four known prototype gap cases are
handled by the reference's dedicated gap tests, not unconditionally accepted.
Tests also cover700kB frames, timestamp/SSRC corruption, wrap, partial EOF, consumer
failure, cancellation and borrowed-buffer clearing. Synthetic test encryption is
not an independent cipher oracle; the original golden bytes/hashes and NIST/carry
tests supply that independent check.

The actual production Annex-B header runs as a Windows executable locally and as
a Darwin executable in owner CI. Strict Darwin/Linux cross-compiles are compile-only.
Apple tests run inside the existing UIKit validation carrier, with no new demo UI:
the system encoder generates valid32x32 H.264, an independent system CTR peer wraps
real RTP/PES, and Native protocol code feeds the real VideoToolbox/display sink.
They require actual decoded dimensions/PTS and at least one actual display enqueue,
gap-to-IDR recovery, oversized-format denial, malformed Annex-B failure and late
data rejection after close. They do not prove physical display refresh, sustained
frame rate, phone interoperability or target iPad hardware decode support.

The existing scan70 assertions, QR and47 FE36 cases remain. The existing App carrier
links the sink and Apple frameworks for compile/package coverage; its UI remains
synthetic, no service is advertised, and no production provider/admission changes.

Next shortest software closure: port HiSight control framing/RTSP/crypto negotiation
and precise supported capabilities; assemble original-owner outbound control/video
(and only required remote-control) sockets, retain key until the actual sink is
initialized, and gate PLAY on actual connection readiness. Only then enable an
accurate display service using target capability evidence. H.264 only here: no
audio, HEVC, touch/input, synchronized media clock or live HiCar projection claim.
No iPad action is required for this software gate. Before later device validation,
audit the new exact SHA/run/BUILD and DEB digests, obtain read-only iPadOS/Dopamine/
model/screen/API capability evidence, then obtain separate authorization for install
and the same-session FE35 -> QR/PIN -> Honor -> FE36 -> WiFi/TCP -> DMSDP -> media
sequence. Production deny-all and macOS/Theos rootless/ldid -S remain unchanged.
