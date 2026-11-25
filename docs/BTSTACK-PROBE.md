# Bounded daemon protocol probe

Version 0.3.1 adds `--btstack`. This validates a prerequisite for live Bluetooth work, not the FE35/FE36 gate or a real HiCar handshake.

The client only connects to the now device-confirmed `/tmp/BTstack`. It sends two daemon query commands: GET_VERSION (opcode 0xf404) and GET_STATE (0xf401), validates complete version/state events, then closes its socket. It does not send power, discoverability, pairing, RFCOMM or SDP commands. A state value of zero is allowed: responding while powered off is a successful daemon query, not radio readiness. Results are numeric metadata and success/failure markers only; packet bytes and credentials are never printed.

Wire format was reviewed directly from the read-only Showcase revision `ce9d1d50758f67307deb3f00c901a8e82894930c`: `platform/daemon/src/socket_connection.c` (6-byte LE type/channel/length), `src/btstack_defines.h` (OGF/OCF/event codes), and `platform/daemon/src/daemon.c` (version event and GET handlers). The probe is independently written and does not copy the BTstack implementation. Installed daemon identity remains unpinned; a returned version is not a source-commit attestation.

The socket is nonblocking, each connect/query has a four-second monotonic deadline, replies are capped at 1024 bytes and 32 frames per query, short I/O and EINTR are handled, and SIGPIPE is suppressed per socket. Unknown events can be skipped within these bounds. No raw socket is exposed as a generic command channel.

Important source-observed lifecycle behavior: daemon client disconnect performs per-client cleanup, updates discoverability from remaining clients, and can schedule power-off when no client requests power; with no clients it disconnects HCI connections. Therefore this query is not claimed to be entirely side-effect-free. Run the manual probe when there is no active Showcase/CarPlay/HiCar Bluetooth session. Do not run an arbitrary terminal netcat test against this socket.

CI compiles the same C code for macOS with a test-only socket-path argument and a synthetic Python Unix server. Cases cover fragmented replies, unrelated events, peer EOF, oversized frames, invalid event length, wrong channel, timeout, event flood and missing socket. These are mock tests, not a real BTstack run, simulator radio test or physical-device pass. The shipped command has a fixed socket path and no path injection option.

After installing the CI-built 0.3.1 DEB with Sileo:

```sh
/var/jb/usr/bin/openhc-bridge-check --version
/var/jb/usr/bin/openhc-bridge-check --btstack
```

Version must show `OPENHC_STAGE0_VERSION=0.3.1`. Success includes `BTSTACK_VERSION=...`, `BTSTACK_REVISION=...`, `BTSTACK_STATE=...` and `BTSTACK_QUERY_OK`. Failure emits `BTSTACK_QUERY_FAILED=CONNECT`, `VERSION` or `STATE` and exits 1; do not silently treat a socket connection as a protocol pass. Both success and failure close the client socket.

Remaining gate: actual FE35/FE36 SDP records, assigned/negotiated RFCOMM channels, no forced link authentication, dual-channel send/receive and clean close/reopen, followed separately by real HiCar handshake and hotspot/AP evidence. None is implied by a query success.

## Physical result (2026-11-26)

User reports `btstack_version=1.1`, then `reversion=3257,state=0.query_ok`. Accept the latter as the user's transcription of revision/state/query-success fields. The C client emits version/state only after validating both responses, so record a user-reported physical GET_VERSION/GET_STATE pass. Do not invent exact raw stdout, exit status, package version or binary hash. Fixed-reference `src/hci_cmd.h` defines HCI_STATE_OFF=0 and HCI_STATE_WORKING=2; state 0 is compatible with this probe never requesting power. It does not mean Apple's system Bluetooth switch is off, nor that controller initialization failed. The daemon version/revision is protocol metadata, not provenance for the installed binary.

Before a powered test, audit controller ownership/recovery: Showcase `source/carplay_bt.m` around 1517 explicitly assumes Apple Bluetooth was already unloaded by Showcase before requesting BTstack power. That assumption has not been established on this target. Do not copy its launchd unload/kill sequence blindly. A dual-channel probe must separate daemon-side registration/SDP evidence from actual radio/channel I/O, retain a client power lease for its bounded session, and cleanly restore any altered platform state. Real HiCar handshake evidence additionally requires a compatible peer phone; a generic RFCOMM client can only test transport.

## 0.3.2 local service registration probe

`--btstack-services` requires a confirmed daemon connection and HCI state OFF (0); it fails explicitly if the observed state is not OFF. It never powers the controller, requests discoverability, modifies system Bluetooth daemons, pairs, accepts channels or transmits peer data. It transiently registers two RFCOMM listeners and independent SDP records with UUID16 FE35/FE36 (Bluetooth-base UUID compression), and prints their actual local channels and daemon-issued record handles. This is a daemon API experiment, not the complete HiCar service record or discovery advertisement.

Channels are selected from temporary candidates 16..23; only a specific channel-already-registered status 0x71 is skipped. No persistent channel database is altered. Only successfully acknowledged owned channels/SDP handles are explicitly unregistered. The daemon creates record handles; parameters use the reviewed LE daemon command format and BE SDP data elements. Records include ascending ServiceClassIDList, ProtocolDescriptorList (L2CAP plus RFCOMM and its assigned channel), and BrowseGroupList attributes. There is no claim that a local registration acknowledgement proves radio-visible SDP or no link authentication on the installed binary.

Two cycles use independent daemon socket connections and the same selected channels: register FE35 and FE36 simultaneously, unregister both SDP handles/listeners, query state as an ordered-processing barrier, close, reconnect and repeat. Unregister commands have no acknowledgements in the fixed reference; the barrier is not a remote SDP-absence query. Successful local re-registration proves channel reuse, not physical peer-channel close/reopen. Timeouts/malformed replies cannot attest complete cleanup; print failure and close so the fixed-reference daemon can run per-client cleanup. Daemon behavior/version remains a target of verification, not an assumed guarantee. Run outside active Showcase/CarPlay/HiCar sessions because disconnect cleanup has the lifecycle effects described above.

The synthetic server tests independently parse SDP elements, check UUIDs/protocol/channel mapping, verify cleanup only targets owned resources, and require channel reuse across two connections. Additional cases test busy channel skipping/exhaustion, state-not-OFF refusal, allocation failures, first/second SDP failures with partial cleanup, and mismatched registration replies. They do not replace physical `--btstack-services` execution.

Install the 0.3.2 DEB and run:

```sh
/var/jb/usr/bin/openhc-bridge-check --version
/var/jb/usr/bin/openhc-bridge-check --btstack-services
```

Expect version `OPENHC_STAGE0_VERSION=0.3.2`, local channel/handle metadata for both UUIDs, `BTSTACK_LOCAL_SERVICE_CYCLE_OK=1`, `=2`, then `BTSTACK_LOCAL_SERVICES_OK`. A failure prints `BTSTACK_SERVICES_FAILED=<stage> STATUS=<last_registration_status>`; the status is diagnostic and can refer to a preceding operation. Do not request a phone pairing attempt from this probe.

The physical prerequisite was subsequently reported passed on 2026-11-26: FE35 channel 16 / handles 65537 and 65539, FE36 channel 17 / handles 65538 and 65540, with both cycle markers and `BTSTACK_LOCAL_SERVICES_OK`. Treat this as local daemon evidence only. The next probe must exercise actual peer-visible SDP and negotiated channels, then bounded two-channel I/O and close/reopen; it must not infer those results from local registration.

The user identifies the intended real HiCar peer as Honor 20 Pro, HarmonyOS 4.0, HiCar supported. Record this as user-provided compatibility information, not a tested handshake result. The peer is not required for the local registration probe; actual role/direction/channel selection for later connection tests must follow OpenHC's negotiated flow, not assume both sides always listen.
