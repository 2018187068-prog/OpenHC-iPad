# FE35 pre-accept timeout diagnostic (not a production repair)

Scope: run46163621763/source d1199b6eb6d1a3d850f2da35e42466072c21c4af failed in owner-success while the strict peer expected0xf444 but saw kind1/channel0/size7; native reported INCOMING_TIMEOUT and independent cleanup-unconfirmed. That archive did not record the actual opcode or peer timing. A size7 packet alone does not identify its opcode or prove a scheduling cause.

## Diagnostic contract

Only owner-success in the existing Simulator carrier collects IncomingBoundary. It keeps at most32 in-memory entries with allowlisted stages and numeric typed header/opcode/length (unknown opcode/length is -1), then writes incoming-boundary.json once in the final evidence block, including failure exits. It removes stale status evidence before launching this case. No payload, keys, identity text or arbitrary native text enters this certificate. The original strict read_command assertion remains; observing an unexpected fixed command prefix does not accept it, drain payload, retry or extend its timeout.

Native test builds emit one BTSTACK_FE35_INCOMING_BOUNDARY record at completion after cleanup, only if the incoming wait was entered. Eight numeric fields are incoming-start-ms, original-deadline-ms, receive-end-ms, receive-result, cleanup-start-ms, cleanup-end-ms, protocol-result, cleanup-confirmed. receive-result -3 means not called, -1 timeout/IO, -2 rejected,0 received; cleanup-confirmed -1 means no completed certainty calculation. Existing primary-stage and ten cleanup-facts fields remain independent. Capturing values during the receive loop performs no log/file writes. Device production builds do not include these new diagnostic clocks/output.

Peer times are monotonic nanoseconds; native times are monotonic milliseconds. Use intervals within each clock domain. Do not subtract native and Python absolute timestamps or assume their epochs are equal. There are no changes to the production25000ms incoming deadline, test150ms incoming deadline, query/cleanup bounds, protocol allowlist or cleanup predicate.

## Actual C/socket regression

Run python3 scripts/test-fe35-incoming-boundary.py with clang on Linux/macOS, or supply --executable for a separately built carrier. The existing test-btstack-transport-socket.py invokes this suite on its existing host/owner routes. The carrier includes the actual btstack-probe.c and uses its connect, receive, command, timeout, unregister, barrier, close and cleanup-certainty implementation. Bridge/owner callbacks are explicit injected test effects; no crypto, device or owner admission success is claimed.

Eleven cases: prequeued incoming/open then remote close; missing incoming with confirmed cleanup; delayed incoming with confirmed cleanup; delayed incoming plus barrier EOF; original drive_peer with controlled delay and its unchanged strict header failure; barrier wrong channel; barrier timeout; one injected SDP-remove send failure; one channel-remove send failure; one barrier-send failure; one final close failure. Fault modes inject one EIO at the syscall boundary; close-failure mode closes the real socket before reporting failure to avoid leaking it. Other cases use actual OS socket outcomes.

The controlled-delay original-peer case reproduces the old error shape and independently records actual0xf431/length4 before the original assertion rejects it; C then records the same pre-accept primary stage and unconfirmed cleanup facts. This proves a possible causal path, not the cause of the old CI run. Exact future owner-success evidence is still needed before choosing any repair.

The optional OPENHC_WINDOWS_SOCKET_TEST adapter requires _WIN32 plus both test carrier macros. It maps OS calls to real Winsock/WSAPoll/QPC, rejects fd truncation, and contains no protocol or cleanup implementation. Windows execution does not establish Darwin/POSIX socket ABI, SIGPIPE behavior or Apple runtime correctness. Darwin/Linux cross-compilation is compile-only when performed on Windows. Neither path establishes VideoToolbox decoding, UI/QR, dual DEB production, radio or live HiCar acceptance.

## Fixed reference mapping checked from source

Showcase ce9d1d50758f67307deb3f00c901a8e82894930c, btstack-rootless/src/btstack_defines.h:190 and203 defines SDP_UNREGISTER_SERVICE_RECORD0x31 and RFCOMM_ACCEPT_CONNECTION0x44. btstack-rootless/platform/daemon/src/daemon.c:1070 reads a16-bit CID for accept; :1109 reads a32-bit handle for SDP unregister. socket_connection.c:562-565 constructs the six-byte LE type/channel/size header. Thus accept has command body3+2=5 bytes, unregister3+4=7; this mapping does not identify the unrecorded historical opcode.

No production protocol repair, timeout adjustment, admission enablement, device operation or new workflow is included. The HiSight video gate must pass actual Apple runtime acceptance before control/media integration resumes.
