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
