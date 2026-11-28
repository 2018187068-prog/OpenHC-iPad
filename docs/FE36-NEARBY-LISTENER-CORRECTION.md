# FE36 Nearby listener correction

Baseline: `02a2c29c5ef3e3f16039ba751688dd2d2372d87e`, audited run `46122252555`.
All 31 isolated cases ran: original auth21 passed, Nearby malformed/unsupported
passed, eight remaining Nearby cases closed before the first MAC request. The
old background intermittency remains unexplained.

The confirmation is valid: resource command7 value `EA(3) EA(1)` omits an optional
detail TLV, as permitted by pinned OpenHC `8132399bea6aa86d68da6d3e1d9e3e001c0a7643`
`DataChannel.parseResult`. `WirelessReceiverSession.onDataChannelResult` confirms
negotiation, starts the WiFi listener and requests MAC after listening. The actual
Python/OpenSSL driver's fixed synthetic encrypted frames now independently feed
the exported common bridge at every confirmation split, including the actual
17-byte split, and reach that same order and the bounded TCP boundary.

The production ObjC adapter instead required `getsockopt(SO_ACCEPTCONN)` before
calling `wifiListening`. Apple XNU `xnu-11215.1.10` `bsd/kern/uipc_socket.c`
`sogetoptlock` supports `SO_TYPE` but has no `SO_ACCEPTCONN` getter; unknown
options return `ENOPROTOOPT`. `solisten` sets the internal accept state and
rejects connected sockets; `bsd/netinet/tcp_usrreq.c::tcp_usr_listen` reasserts
TCP listen state. Thus a valid injected listener fails the old platform check,
returning NULL, causing the C worker to close control before MAC. The archives
did not capture errno: this is source evidence for an incompatible check, not
a claim that the old run recorded a specific errno.

Correction: validate the same provider-owned socket's IPv4 address/port, stream
type and nonblocking flags, then reassert `listen(fd,1)` with kernel error
checking. Only then report listening to common. No new socket, connection,
provider, key, lease or authorization is introduced. C still accepts and checks
the actual peer, owns the bounded TCP descriptor and enforces final cleanup.
Auth-close/unregister barrier, immutable authority/deadlines, cancellation,
one-shot secret transfer and the entire strict31 matrix remain intact.

Regression boundaries:

- Windows Python checks actual socket listen/relisten/accept, connected and UDP
  rejection, ownership/port stability and original unbound/blocking preconditions.
  Actual phone/OpenSSL frame vectors are shared as fixed inputs with common tests.
- JVM runs the exported common bridge with real cipher and fixed driver frames,
  all 20 confirmation split points, duplicate result, MAC, info and TCP boundary.
- The Apple owner gate compiles/runs the actual production C listener helper
  with `-Wall -Wextra -Werror`: valid/repeated listener, actual loopback accept,
  connected socket, wrong address, blocking, datagram, unbound and invalid input.
  This POSIX runtime and the full Simulator31 remain pending until exact CI audit.

Production remains deny-all with injected network effects. This remains a borrowed
bounded TCP boundary, not a live ControlLink/ReceiverSession or HiCar/device proof.
No device action is required for this software gate.

Follow-up test timing correction (audited `ecbf252e24e39e9a40354924ed3e64dd99e1ad5f`,
run `46124629009`): Darwin's accepted nonblocking socket returned EAGAIN at the
Python test's immediate receive. This occurred before the production C helper
runtime and Simulator31; it establishes a test readiness assumption, not a
production listener result. Both listener tests now use bounded readiness with
monotonic deadlines, explicitly nonblocking accepted sockets, and exact reads.
They force accept EAGAIN before connecting and receive EAGAIN before each of two
one-byte fragments, then check exact `XY`, EOF, unchanged port, nonblocking
ownership and connected-socket rejection. No sleeps or production timeout changes.
Unready accept/read tests also exercise bounded failure. Subsequent socket suites
already set bounded listener/accepted-socket timeouts and loop over framed reads;
their single-byte reads check one-byte data or EOF. The C helper runtime remains
an Apple CI gate; Windows Python is real local socket evidence only.

Strict-C portability preflight (audited run `46127594253`, SHA `2bb9eff`):
Python listener8 passed, then the C test failed to compile because its explicit
`_POSIX_C_SOURCE=200809L` hides Darwin's `INADDR_LOOPBACK` extension. The test now
checks `inet_pton(AF_INET,"127.0.0.1",...) == 1`, asserts host value `0x7f000001`
and network bytes `{127,0,0,1}`, and passes that same address to every bind. The
feature macro, strict warning flags, production helper and negative checks remain.
Existing Zig 0.17.0 with bundled Darwin headers reproduces the original failure
and compiles the corrected complete C test for macOS arm64/x86_64 and Linux musl;
the standalone actual production header and the next five Darwin C gate inputs
also compile under C11/Wall/Wextra/Werror. This is cross-compile-only evidence,
using bundled headers rather than Xcode16.4's SDK. Actual Apple linking/runtime,
Simulator31 and later UI/package acceptance remain pending. This follow-up is
local and unstaged for coordinator review; it does not authorize another CI run.
