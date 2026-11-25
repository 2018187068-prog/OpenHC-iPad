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
