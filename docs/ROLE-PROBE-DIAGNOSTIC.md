# Metadata tool termination and transport preparation — 2026-11-26

## Latest physical result after SSH resumed

The user subsequently reported SSH connected. Port 2222 returned OpenSSH 9.7;
an existing authenticated native SSH console supplied UID 0, iPad5,1 and
15.8.8. No password, private key, pairing record, terminal history, process argv
or broker application data was read. No new SSH authentication was performed.

| Controlled condition | Observed result |
| --- | --- |
| New baseline, root-owned mode 700, `/var/root/Library/OpenHCStage0Tools/showcase-role-probe-baseline-dacf5f82`, remote SHA-256 matches CI | Direct zero-socket self-check killed / 137; no main marker |
| Add only that baseline's SHA-1 CDHash, while its SHA-256 CDHash was already listed | Add returned 0; same self-check still killed / 137 |
| Independently hashed legacy-fixups candidate under the same `/var/root` directory | Zero-socket self-check also killed / 137 |
| Copy the **same baseline bytes and signature**, mode 700, to `/var/jb/usr/bin/openhc-role-probe-dacf5f82` | `ROLE_PROBE_MAIN_ENTERED`, `ROLE_PROBE_SELF_CHECK_OK`, exit 0 |
| One normal fixed-endpoint query from that verified rootless copy | Owner PID 27078, zero application bytes sent/read, query OK, exit 0 |

Both baseline copies have SHA-256
`dacf5f82545ac5e67b32c34fe992dab9e4f804fdc65bd73bc86c9b526b12c445`.
File metadata locates the failing copy on `/private/var` (device 16777222),
and the working copy on `/private/preboot` (device 16777221). Mount metadata
lists `protect` for `/private/var`; it does **not** list `noexec`. This is an
observed execution-location/filesystem difference and a validated narrow
deployment fix, not a proven kernel termination namespace or a demonstrated
`noexec` mechanism. No device termination-reason record was obtained. Do not
claim missing trust, memory pressure or chained fixups as the diagnosed cause.

Comm-only metadata associates PID 27078 with `CarPlay Simulator`; a new
Showcase main process PID 37681 was also present. No `CarDisplaySim`/`carplay_bt`
was listed, and `/tmp/showcase_bt_owned` was absent. The reference broker
branch returns into its loop before network-session initialization. Socket
ownership now supports the persistent broker interpretation; it is not proof
of installed source equivalence, no parallel session, exclusive controller
ownership, or permission to power on. No process was stopped or killed.

Evidence: `artifacts/device-validation-20261126/console-metadata-bridge.py.log`
and `ssh-resumed-role-evidence.json` in the same directory. The local console
bridge is session-specific and must not be reused blindly with its saved PID.

`scripts/package-role-probe.py` now emits an audited copy under
`rootless/var/jb/usr/bin/openhc-role-probe-<sha8>` and a manifest naming the
required device execution path. It neither installs nor executes nor changes
trustcache/signing policy. The copied layout was verified locally using the
existing CI artifact; the new workflow packaging step has not yet run in CI.
The prior 22 tests were not repeated for a layout-only change. Old files and
the compatibility candidate are preserved; no DEB or system executable was
overwritten. The power-driver role gate remains closed.

## Earlier offline evidence

The original helper artifact from CI `45680397016` has SHA-256
`f5e6565974e35cec2480ceba1d3b24d704c044230debbdea46f31a065f5f10b7`.
Its bytes agree with the historical upload log. `scripts/audit-role-binary.py`
checks the actual artifact, not just ldid's printed summary: thin baseline
arm64 executable, iOS platform 2, minimum 15.0, SDK 18.5, sole dependency
`/usr/lib/libSystem.B.dylib`, no RPATH or entitlements, unencrypted executable,
bounded signature blobs, SHA-1/SHA-256 CodeDirectory coverage and every code
page and special-slot hash. The original artifact passes those checks.

The physical log establishes SIGKILL / shell status 137 twice, including after
one tool CDHash registration. It does **not** establish AMFI rejection,
jetsam, dyld failure, a socket API fault, or an external signal sender. No
device termination-reason metadata was captured. The old program emitted
nothing before endpoint work, so absence of output does not identify the
startup phase. Its four-second alarm would not itself explain signal 9.

The known working 0.3.2 executable also uses `LC_DYLD_CHAINED_FIXUPS`, SDK 18.5,
CodeDirectory v0x20400, zero CD flags and 4 KiB signature pages. Those features
alone are not an explanation. A valid offline signature does not prove AMFI
acceptance on this installation, nor did the earlier trustcache action prove
successful execution. Do not add entitlements, broad trust entries, disable
validation, or re-sign unrelated installed binaries to guess around the fault.

## Safe changes and evidence boundaries

The probe now flushes `ROLE_PROBE_MAIN_ENTERED` before endpoint work and accepts
only an additional fixed `--self-check` mode. That mode returns
`ROLE_PROBE_SELF_CHECK_OK` without root, socket, process, broker, or auth access.
Normal release execution still has a fixed endpoint and root requirement;
there is no endpoint override. No send/recv/read/write, authentication API,
process argv, key or credential file access was added.

CI builds independently named baseline and `-Wl,-no_fixup_chains` variants.
The latter is a compatibility experiment, **not a diagnosed fix**. Keeping the
baseline avoids attributing a difference to a changed source or signing policy.
Both have independent hashes, full load commands, signature/dependency reports,
structural audit JSON, and toolchain provenance. Never substitute one binary
under the other's hash or run both automatically on device.

CI `45683159550` / source `46d6daa82b4708ed68134bbec54ebbb1f0ebf79f`
passed six synthetic signature tests and seven macOS endpoint/startup tests.
Artifacts are under `artifacts/ci-run-45683159550/`:

- baseline SHA-256 `dacf5f82545ac5e67b32c34fe992dab9e4f804fdc65bd73bc86c9b526b12c445`
- legacy-fixups SHA-256 `a552f4b29b2406285daa22d0f946a9e8571247e7642beea2db0e35e13b7d977a`

The first revised CI `45683029352` failed before iOS compilation because
macOS Bash 3 with nounset rejects expansion of an empty array. That CI-only
bug was corrected by keeping common flags in the array. It is unrelated to
the old physical SIGKILL. At this point no revised artifact had run on iPad;
the later physical execution and owner evidence is recorded above.

Final combined CI `45683689513` / `dddd437` passed all 22 tests (6 signature,
7 endpoint/startup, 9 new transport metadata cases). Artifacts were downloaded
to `artifacts/ci-run-45683689513/`; the two binary hashes match those above and
both downloaded binaries also pass the local structural auditor. Final build
provenance records Xcode 16.4, clang 17, SDK 18.5 and ldid 2.1.5_2. The host
channel observation is recorded in
`artifacts/device-validation-20261126/continuation-local-audit.log`.

## USB blocker and future read-only diagnostic order

The user confirmed successful administrator restart of Apple Mobile Device
Service during this session. The one subsequent host check returned
`USB_DEVICE_COUNT=0`, `USB_LIST_EXIT=0`, `SSH_BANNER_PRESENT=0`,
`SSH_BANNER_BYTES=0` using the existing port 2222 forwarder. No new forwarder
was started, no process was killed, and no further trust reset or driver
operation was requested. At this earlier point transport was unavailable;
it later resumed as recorded above. No further administrator command is needed.

The following was the diagnostic plan before SSH returned. Startup and owner
steps are now completed as recorded above; do not repeat them:

1. Confirm only the tool's path/type/owner/mode/hash and OS architecture; do
   not enumerate credential files or dump process arguments/environment.
2. Stage one verified baseline tool as a separate file and run `--self-check`
   once with bounded output/time. First try the zero-socket mode, not the broker.
3. If killed, collect only a tool-specific structured termination summary
   (process name, timestamp, exception/termination namespace and numeric code).
   A future extractor must discard all other fields before emitting output;
   do not dump DiagnosticReports, unified logs, broker logs, or raw crash reports.
   Until that extractor is available, mark termination reason unknown.
4. A successful self-check isolates executable startup but proves no socket
   access. Only then run the fixed-endpoint owner query once. Compare its PID
   with a current comm-only snapshot. A PID match is broker endpoint ownership,
   not proof of no concurrent Bluetooth session or exclusive HCI ownership.
5. Consider the separately hashed legacy variant only as a targeted follow-up
   to the observed failure phase. Neither outcome authorizes power/unload.

## Independent live transport code work

`scripts/btstack-transport-metadata.py` is a new bounded metadata reader with
synthetic tests, not a live executable or a complete transport probe. It has
no connect, command, power, SDP mutation, peer accept or data-send operation.
RFCOMM data frames are refused after the six-byte outer header, before payload
read. Non-allowlisted HCI event parameters, including security events, are
refused after only the event code/length; no security parameters are read.
Output contains only numeric state/status/channel/CID/MTU/credit/handle fields,
never addresses or raw packets. It bounds deadlines, event count and framing.

Source review of read-only Showcase `ce9d1d50758f67307deb3f00c901a8e82894930c`
identified two independently modeled incompatibilities:

- `src/btstack_event.h:1618` and `src/classic/rfcomm.c:273` put RFCOMM CID at
  byte 12. `platform/daemon/src/daemon.c:1612` reads byte 13 for CHANNEL_OPENED.
  This could route/account the event incorrectly. Installed binary equivalence
  is unknown; this is not a confirmed physical defect.
- `src/classic/rfcomm.c:265–277` allocates 18 bytes and advertises 16 parameter
  bytes, but dispatches `pos=17`. The reader intentionally rejects this length
  mismatch; it does not silently accept a malformed stream. The daemon's
  immediate create-failure event is a distinct 16-byte shape, without incoming
  direction; the reader accepts it only as a failure and reports unknown direction.

Further local/CI work can implement a synthetic two-channel state machine,
negotiated SDP/direction handling and bounded cleanup without a device. A live
runner still needs verified helper role, installed event-format/routing evidence,
no-forced-link-auth evidence, explicit synthetic peer readiness and integration
with the recovery guard. Actual powered execution is forbidden in this session.
The current metadata slice does not prove SDP, I/O, close/reopen lifecycle,
ownership or a HiCar handshake, even when its synthetic tests pass.
