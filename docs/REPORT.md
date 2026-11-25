# Stage 0 Validation Report

Date: 2026-11-26

## Confirmed from source

- Reference OpenHC revision: `8132399bea6aa86d68da6d3e1d9e3e001c0a7643`; Showcase revision: `ce9d1d50758f67307deb3f00c901a8e82894930c`. Both worktrees reported clean.
- The reference version catalog pins Kotlin 2.1.20 and Gradle wrapper properties pin 8.13.
- Session documentation says core is pure Kotlin/JVM and the session composes nearby/auth/dmsdp/hisight; `SocketRunner` owns `java.net` blocking I/O.
- `MalformedMessageException` extends `IOException`.
- `WifiChannels.kt` is a self-contained candidate, while `WifiConnectionInfo.kt` uses `MalformedMessageException`, `WifiChannels`, and other platform-free Kotlin/JVM APIs; the minimal dependency slice is now tested as described below.
- The copied `WifiChannels.kt` file's SHA-256 matches the fixed reference source: `F36BEDCAD3EF407D0002C9D461579DFC527F05C7C43B9703AAE714DB63EC9CEB`.

## Environment checks

- Windows worktree: `D:\orcafile`; validation directory did not exist before setup.
- GitHub CLI was initially unauthenticated; after the user logged in, a new private repository `2018187068-prog/OpenHC-iPad` was created. Remote contents were checked while empty, then a README seed and all project files were added through normal parented Git commits. Smart-HTTP pushes were reset by the network, so authenticated Git Database API ref updates were used with `force=false`; no existing remote file or commit was overwritten.
- AGENTS.md: none found in `D:\`, `D:\orcafile`, or the new validation root.
- WSL: no installed/registered distribution; `wsl --exec` requests WSL installation.
- GitHub CLI: initial check was unauthenticated; subsequently logged in and used for the private repository and CI (see above).
- SSH config has aliases `aliyun-vps` and `singa-vps` only. No device alias was found; no host was contacted. No SSH agent identities were listed.
- Windows PATH has no `xcrun`, `clang`, `theos`, or `ldid`.

## Implemented and built in CI

Added a minimal Kotlin Multiplatform `iosArm64` static framework with exported `BridgeSelfCheck.selfCheck()`, common `WifiChannels` source/tests targeting JVM and iOS simulator, a macOS-15 GitHub Actions workflow, framework inspection script, Theos arm64/iOS-15 rootless command-line package targeting `/usr/bin`, and a device-run helper. The expected device output is `KOTLIN_BRIDGE_OK`.

## Validation status

- Source/configuration review: completed for the items above.
- Kotlin/Native framework build: passed on GitHub macOS 15 arm64 runner, initial successful GitHub Actions run `45620285649`, commit `bd0168441fb8362cd0466acd0227242ebd77f8d5`.
- Shared `jvmTest` and `iosSimulatorArm64Test`: both passed on that run (`BUILD SUCCESSFUL`). This confirms the test suites run on JVM and simulator, not an installed app on the physical iPad.
- Objective-C link, static-link dependency inspection, arm64, package layout/metadata, system-library inspection, and iOS minimum checks: passed in CI. Framework archive members report minimum iOS 12.0; the Theos executable reports minimum iOS 15.0.
- Theos reported its signing stage; `ldid -h` found an embedded CodeDirectory and CDHash. This is a local ad-hoc/fakesign result with no developer certificate identity, not proof of trusted signing or device acceptance.
- Native simulator test task: passed. A GUI simulator app launch has not been done.
- Physical iPad mini 4 bridge: **passed, user-reported**. On 2026-11-25 the user reported `KOTLIN_BRIDGE_OK` after the installation/run instructions. This agent did not operate SSH or observe installation, `uname -m`, exit status, device metadata or the installed package hash; none of those are claimed as independently captured device evidence.
- WifiChannels JVM/Native shared test: passed in the macOS CI run above on both JVM and iOS simulator.

## Physical-device deployment check (2026-11-25)

- Re-read `scripts/run-on-device.sh`: it accepts exactly one configured SSH alias and runs `ssh <alias> 'uname -m; /usr/bin/openhc-bridge-check'`. Expected output is two lines: `arm64` then `KOTLIN_BRIDGE_OK`.
- The helper has no install step. The downloaded package is `artifacts/ci-run-45620285649/openhc-ipad-stage0-bd0168441fb8362cd0466acd0227242ebd77f8d5/deb/com.gcbond.openhc-bridge-check_0.1.0_iphoneos-arm64.deb`; package inspection shows it installs to `/var/jb/usr/bin/openhc-bridge-check`; use that canonical rootless path (do not assume `/usr/bin` is redirected). Install using Sileo by opening/importing this DEB on the iPad, or with an already configured privileged SSH account by copying it to `/var/mobile/` and running `dpkg -i /var/mobile/com.gcbond.openhc-bridge-check_0.1.0_iphoneos-arm64.deb`. The SSH route requires root, or an account with working `sudo`; that access mode has not been verified.
- Connection preflight: Windows SSH config contains only `aliyun-vps` and `singa-vps`, with no iPad alias. Neither host was contacted. No SSH identities were printed or used. WSL has no registered distribution. Do not substitute either VPS alias.
- The initial SSH preflight was blocked on connection setup; it is superseded for bridge execution by the user-reported result below. Agent-operated SSH remains unconfigured. Required to enable agent-operated SSH: the configured iPad SSH alias (preferred), or its LAN address, SSH port and login name, plus confirmation that the account can run `dpkg` as root. Do not send passwords or private keys.
- Verified artifact SHA-256 remains `45FC16BC3F94C938BDB2AFA6BC355631B936A2E30610B09B0DF93BD4F6CD9FD8`. The user subsequently reported the device output below; the installed package hash was not independently verified on-device.

## Successful CI artifacts

Downloaded to `D:\OpenHC-iPad\artifacts\ci-run-45620285649\openhc-ipad-stage0-bd0168441fb8362cd0466acd0227242ebd77f8d5\` (ignored by Git):

- `iosArm64/OpenHCBridge.framework/` (static arm64 framework and Objective-C header).
- `deb/com.gcbond.openhc-bridge-check_0.1.0_iphoneos-arm64.deb` (rootless package).
- `logs/` and `BUILD.txt` (Kotlin/Native, test, Theos, linker, package, SDK and inspection output).

SHA-256: framework archive `1B33DA2067763D1DE5166F7B8C7E783E9686B98102E6B73584C2A6104D3A4F52`; DEB `45FC16BC3F94C938BDB2AFA6BC355631B936A2E30610B09B0DF93BD4F6CD9FD8`.
- First macOS CI run compiled and linked the `iosArm64` framework successfully in 1m 6s; a local inspection script then failed because it passed the archive path to `lipo` in the wrong argument position. Corrected the architecture inspection and added a static-archive minimum-iOS check before rerun.
- Second macOS CI run passed static-framework build/inspection and both shared JVM and Native simulator test tasks. Theos bootstrap then failed because its recursive clone already populated the `sdks` submodule and the workflow tried to clone that directory a second time. Removed the redundant clone; Theos package/signing checks remain pending.
- Third macOS CI run again passed the framework and shared tests, then compiled the Theos Objective-C source far enough to show the framework header search path was not being passed to Clang. Switched to Theos' documented per-target compiler/linker flags for `-F`; also corrected the device-binary `lipo` argument order.
- Fourth macOS CI run passed framework and shared tests and compiled through header inclusion; Kotlin's generated Objective-C class name carries the module prefix `OHCB`. Updated the Theos client to call the generated `OHCBBridgeSelfCheck` class; package/link/signing checks remain pending.
- Fifth macOS CI run passed framework inspection, both shared test targets, Theos compile/link, rootless staging, and Theos signing; it produced an `iphoneos-arm64` DEB. Post-build inspection stopped because macOS lacks `dpkg-deb` by default. Added Homebrew `dpkg` and corrected the expected package architecture field from `iphoneos-arm` to `iphoneos-arm64`.
- Sixth macOS CI run passed framework, shared tests, Theos compile/link/signing and DEB creation/extraction. The final inspection failed because `ldid -e` returns failure when asked to extract entitlements from this binary, which intentionally has none. The same log showed a CodeDirectory; switched the check to assert that signature metadata is present instead of requiring an entitlement blob.
- Seventh macOS CI run passed framework, tests, Theos build/sign, DEB extraction, architecture, dependency, and iOS minimum checks; the last failure was a package-layout grep expecting a leading slash absent from `dpkg-deb -c` output. Corrected the pattern to match the observed `var/jb/usr/bin/...` path.

## WifiConnectionInfo dependency assessment (source review only)

`WifiConnectionInfo` depends on `WifiMode`, `WifiChannels`, `Ipv4Text.isCanonical`, Kotlin `Regex`/collections/string APIs, and `MalformedMessageException`. No Java API is directly referenced in the `WifiConnectionInfo` class slice; the blocker is the exception base class in `java.io.IOException` (and its `cause` constructor). A narrowly scoped migration can keep parse behavior while introducing a common exception type, but callers that catch `IOException` must be audited. `Ipv4Text` is a small pure Kotlin IPv4 parser in `core/common/codec`; its copied reference tests now pass in JVM and Native simulator. This is limited parser-slice evidence, not full protocol migration readiness.

## Physical bridge result and next probe (2026-11-25)

User supplied the following device result after the install/run instructions:

```text
KOTLIN_BRIDGE_OK
```

Gate 1 bridge execution is **passed on the basis of user-reported physical-device output**. The agent has no live device connection and did not capture `uname -m` or installation logs. This result establishes the minimal Kotlin/Native-to-Objective-C bridge only; Stage 0 as a whole remains incomplete.

The next probe extracts `WifiMode` and `WifiConnectionInfo` verbatim from the fixed reference file up to the following `WifiLinkMessages` documentation block; it copies `Ipv4Text` and its tests. `WifiLinkMessages` is deliberately excluded: its `String(value, Charsets.US_ASCII)` is a separate JVM boundary, not silently rewritten. `scripts/source-slices.sha256` pins LF-normalized probe sources, checked by CI.

`MalformedMessageException` is an explicit expect/actual boundary: the JVM actual keeps `java.io.IOException(message, cause)`, and the Native actual uses `Exception(message, cause)`. Shared tests check message/cause preservation and malformed-input behavior; a JVM test checks `IOException` catch compatibility. Native callers must catch `MalformedMessageException` explicitly; session `SocketRunner` IOException catch sites (301/324/344/357/450/473/497/505 at the reference revision) require policy review when that layer is migrated. No session migration is included.

The 0.2.0 DEB adds `openhc-bridge-check --wifi`, which executes synthetic encode/parse, channel and rejection checks and emits only `WIFI_CONNECTION_INFO_OK` or `WIFI_CONNECTION_INFO_FAILED`. Default invocation still emits `KOTLIN_BRIDGE_OK`. The user subsequently confirmed the second (`--wifi`) command returned OK; see the device evidence below. New JVM/Native CI results are recorded below. The helper now uses the canonical `/var/jb/usr/bin/openhc-bridge-check` path and accepts optional `--wifi`.

## WiFi parser probe CI evidence (2026-11-25)

Run `45642428044`, commit `d53c49c1aa4047a2f45f09c9f118761be9241afc`: **success**. The downloaded JUnit XML reports 14 JVM tests and 13 iosSimulatorArm64 tests, all with zero failures/errors. Coverage includes WifiChannels, copied Ipv4Text tests, 8 WifiConnectionInfo tests, and JVM IOException catch compatibility. All four pinned source-slice checks passed. `BUILD SUCCESSFUL` is present for the framework and shared-test steps.

The 0.2.0 static framework and Theos package passed architecture, static-link, minimum OS (framework 12.0, executable 15.0), signature-metadata and rootless layout checks. Dynamic dependencies are libobjc, Foundation, CoreFoundation, libSystem and libc++; no OpenHCBridge runtime framework dependency is present. This CI signing evidence is separate from acceptance of the new binary on the iPad.

Artifacts downloaded to `artifacts/ci-run-45642428044/openhc-ipad-stage0-d53c49c1aa4047a2f45f09c9f118761be9241afc/`; full run log is `artifacts/ci-run-45642428044.log`. An identical convenience DEB copy is at `artifacts/device-ready/com.gcbond.openhc-bridge-check_0.2.0_iphoneos-arm64.deb`.

DEB SHA-256: `2CF3C1921A003E686C4C097D264E311A8DEFDBAB35C7AF0A18F2BFC0974E6547`. Independently inspected the downloaded ar/tar payload: its only regular installed file is `./var/jb/usr/bin/openhc-bridge-check`, executable mode 0755; bytes match the CI extracted-binary artifact.

Install the 0.2.0 DEB via Sileo, then run:

```sh
/var/jb/usr/bin/openhc-bridge-check
/var/jb/usr/bin/openhc-bridge-check --wifi
```

Expected stdout respectively: `KOTLIN_BRIDGE_OK` and `WIFI_CONNECTION_INFO_OK`. The new `--wifi` device result is **passed, user-reported**: after being asked to run `/var/jb/usr/bin/openhc-bridge-check --wifi`, the user confirmed that the second command returned OK. This is evidence of the synthetic parser self-check running on the physical device. The agent did not independently capture stdout, exit status, package database version or the installed file hash, and does not infer those from this reply. Authentication, Bluetooth and real hotspot gates remain pending; see `docs/NEXT-PROBES.md`. No additional paid runner or billing setting was enabled.

## WiFi parser physical-device confirmation (2026-11-25)

After the canonical rootless `--wifi` command was supplied, the user replied “第二个是ok的” (the second command is OK). Record the expected `WIFI_CONNECTION_INFO_OK` result as user-confirmed physical-device evidence. The user did not report the first (`dpkg-query`) command's version output; package version was not independently verified. File name and modification time are not used as pass criteria.

Both minimal bridge and synthetic WiFi parser device gates now have user-reported passes. This does not validate live WiFi/AP configuration, HiCar authentication, Bluetooth services or a full protocol migration. Continue only with bounded Stage 0 probes.

## Authentication candidate probe CI (2026-11-26 Asia/Shanghai)

Run `45649915495`, commit `2793c7f38e2e1c2bfb3a0de7efad9c7a2263860a`: **success**. Downloaded test XML reports **23 JVM / 21 iosSimulatorArm64 tests**, zero failures/errors. New auth coverage comprises 8 shared tests plus a JVM reference-equivalence test: SHA-256, HMAC, HKDF, AES-GCM/AAD/tamper rejection, Ed25519, X25519/small-order rejection, HKDF bounds and synthetic SPEKE3072 math/key-derivation/public-value boundaries. The independent Python oracle also passed. Tests use only public standard vectors and synthetic values, and no credential/derived bytes are emitted.

JVM uses the pinned reference AuthCrypto source and Bouncy Castle 1.79. Native uses a candidate OpenSSL 3.5.9 static backend, verified upstream commit `45e844fa2a14ec92d146bd8f5778ac130b6625fb`. Both device and simulator arm64 backend archives compiled with minimum iOS 15.0 and correct, distinct device/simulator platforms. The combined framework contains 12.0/15.0 minimum objects; the final CLI minimum is 15.0. `_oh_crypto` was found in the linked tool; no dynamic libcrypto/libssl/OpenHCBridge dependency is present. Theos build/sign, ldid CodeDirectory, architecture and rootless layout checks passed. See `docs/AUTH-PROBE.md` for explicit adapter boundaries and source provenance.

Artifacts and full log downloaded to `artifacts/ci-run-45649915495/` and `artifacts/ci-run-45649915495.log`. Independent ar/tar inspection confirmed the DEB contains `/var/jb/usr/bin/openhc-bridge-check` and OpenHC/OpenSSL license documents; binary bytes match the CI extracted-binary artifact. Convenience copy:

`artifacts/device-ready/com.gcbond.openhc-bridge-check_0.3.0_iphoneos-arm64.deb`

DEB SHA-256: `19820169296137F8648D5FF875CD0056C7EF4958B6D0241C3C025025DD36F441`.

Install this new DEB with Sileo, then run:

```sh
/var/jb/usr/bin/openhc-bridge-check --version
/var/jb/usr/bin/openhc-bridge-check --auth
/var/jb/usr/bin/openhc-bridge-check --platform
```

Expected version: `OPENHC_STAGE0_VERSION=0.3.0`. Expected auth success: `AUTH_VECTORS_OK`. Platform output ends with `PLATFORM_INVENTORY_DONE` and reports hardware/OS, IPv4 interfaces, MIS/MobileWiFi availability and known BTstack socket/daemon presence. It never starts sharing, reads passwords, calls WiFi setters or connects to the BTstack socket; the presence of these APIs/files alone does not establish a functional hotspot or dual-channel transport.

Physical auth/platform runs were pending at CI delivery; subsequent user screenshot evidence is recorded below. No live iPad SSH connection is configured for this agent. The original bridge and 0.2.0 parser retain their separately recorded user-reported physical passes. Full SPEKE/STS/identity-exchange state transitions, real HiCar handshake, Bluetooth FE35/FE36 dual-channel I/O/close and actual AP IP/SSID/BSSID/frequency remain unverified. Stage 0 is not complete, and full migration has not started. No extra paid runner or paid-quota setting was enabled.

CI repair evidence: run `45648844771` failed at duplicate OpenSSL target flags; run `45649195389` compiled both archives and framework then failed because `nm | grep -q` caused a broken pipe in the larger archive inspection. Both checks were corrected without changing protocol behavior. The screenshot's older `96f1a22` run (`45617916269`, 2026-11-25 20:52 Asia/Shanghai) failed on a package-list path assertion requiring a leading slash; subsequent bridge/parser runs passed. A past CI failure notification does not invalidate those later results.

## Physical platform inventory screenshot (2026-11-26)

User screenshot shows `HW_MACHINE=iPad5,1`, iOS 15.8.8 (19H422), an IPv4 address on en0, all five MIS/MobileWiFi availability checks YES, `BTSTACK_UNIX_SOCKET=NOT_FOUND`, `BTDAEMON_ROOTLESS_FILE=PRESENT`, and `PLATFORM_INVENTORY_DONE`. The read-only inventory executed on the physical target, based on user-provided image evidence; package version, exit status and installed hash were not captured. The screenshot does not contain `AUTH_VECTORS_OK`, so the physical authentication gate remains pending.

Only the known `/tmp/BTstack` socket was checked. Its absence does not determine whether the daemon is stopped, unregistered, failing, or configured for another endpoint. The fixed reference launchd plist uses label `ch.ringwald.BTstack`, socket `/tmp/BTstack` and executable `/usr/bin/BTdaemon`; the installed rootless plist and launchd registration must be inspected before changing service state. No launch/start/restart action has been taken. MIS/MobileWiFi symbol availability and en0 connectivity do not establish an AP, SSID, BSSID or frequency. All live hotspot and FE35/FE36 gates remain unverified.

## Subsequent physical auth and BTstack screenshots (2026-11-26)

The 00:39 screenshot confirms `state = running`, `runs = 1`, `pid = 35779`, and `last exit code = (never exited)` after the manual kickstart instruction. User screenshot evidence establishes launchd registration, listener creation and a running process at that instant. It does not establish BTstack request/response, radio readiness or FE35/FE36 services.

## Bounded BTstack query CI evidence (2026-11-26)

Run `45657981526`, commit `1d0233fc290886291a786a4dc030e7d2db98e5c9`: success. The new standalone C client's nine macOS synthetic-server cases passed, including fragmentation, unrelated events, EOF, oversized frames, invalid event length, wrong channel, timeout, event flood and missing endpoint. Downloaded JUnit XML confirms 23 JVM / 21 iosSimulatorArm64 tests, zero failures/errors. Theos arm64, minimum iOS 15, static-link/system-dependency, ldid CodeDirectory and rootless layout checks passed. This is build/mock evidence only for the new client; no physical `--btstack` response has yet been supplied.

Downloaded framework, DEB, test reports, licenses and build logs under `artifacts/ci-run-45657981526/`; full log `artifacts/ci-run-45657981526.log`. Independently read the DEB ar/tar archives: version 0.3.1, architecture iphoneos-arm64, executable `/var/jb/usr/bin/openhc-bridge-check`, bytes equal the CI extracted executable and both new query/version markers present. Convenience copy: `artifacts/device-ready/com.gcbond.openhc-bridge-check_0.3.1_iphoneos-arm64.deb`. SHA-256: `ee119bac546bcc1c628ea6fbc3fd7742d655ad183f1c385d94ce6e6889c3d50f`. Summary: `artifacts/btstack-query-validation-summary.json`.

Next manual action is Sileo installation followed by `--version` (expect 0.3.1) and `--btstack` (expect version/revision/state and `BTSTACK_QUERY_OK`, or explicit failure stage). See `docs/BTSTACK-PROBE.md` for daemon cleanup effects and remaining live gate boundaries. Existing auth/parser device passes are preserved. No additional paid runner/quota was enabled.

## Local FE35/FE36 registration probe CI (2026-11-26)

User identifies the intended HiCar peer as Honor 20 Pro with HarmonyOS 4.0 and HiCar support; record as user-provided information, not an independently tested compatibility result. The local registration probe requires no phone connection.

Run `45661451771`, commit `ba0ea6fdfa8eca837fd6cda61a99321cb53a7825`: success. All nine query-client and eight new local-service synthetic server cases passed on macOS. New cases independently parse SDP records, check both UUID/channel mappings, require two cycles on separate connections, ensure only owned resources are removed, and test busy/exhausted channels, state-not-OFF refusal, allocation failure, partial SDP failures and mismatched registration replies. Downloaded JUnit XML: 23 JVM / 21 iosSimulatorArm64, zero failures/errors. iOS arm64 framework and rootless Theos package passed minimum iOS 15, static-link/dependency, ldid CodeDirectory and layout checks. This is compilation/mock evidence, not physical FE35/FE36 or radio evidence.

Artifacts: `artifacts/ci-run-45661451771/`; full log `artifacts/ci-run-45661451771.log`; local summary `artifacts/btstack-services-validation-summary.json`. Independent DEB ar/tar inspection verified package version 0.3.2, architecture iphoneos-arm64, canonical executable path, executable permissions, new markers and byte equality with the CI extracted executable. Convenience copy: `artifacts/device-ready/com.gcbond.openhc-bridge-check_0.3.2_iphoneos-arm64.deb`; SHA-256 `025f858163c5a1fc0d670bdee5fd79809a310534085238eafa54b05bc6b3e1d7`.

Physical `--btstack-services` was subsequently run and reported successful two-cycle local registration, cleanup, and channel reuse; see the dedicated physical result below. The probe requires observed BTstack OFF, selects two transient free channels from 16..23, registers local FE35/FE36 SDP records, removes owned registrations, and reuses the same channels on a second connection. No power/discoverability/pairing commands or peer I/O are sent. See `docs/BTSTACK-PROBE.md` for cleanup limitations and separation from real SDP/security/channel-I/O/HiCar gates. No extra paid runner or quota enabled.

## Physical daemon query result (2026-11-26)

User supplied `btstack_version=1.1` followed by `reversion=3257,state=0.query_ok`. Record version 1.1, revision 3257, state 0 and query success as user-transcribed physical evidence, not an agent-captured transcript. This passes the bounded local daemon GET_VERSION/GET_STATE prerequisite. Exact stdout casing, exit status, installed package version/hash remain uncaptured. Both queries must validate before this implementation prints version/state. The fixed reference maps state 0 to HCI_STATE_OFF; it is expected to be possible because the query sends no power request. System Bluetooth switch state/controller ownership is not inferred from it. Real FE35/FE36 radio/SDP/channel/I/O/close and HiCar/AP evidence remain pending.

Source review for the next powered probe found Showcase's explicit precondition that Apple Bluetooth has already been unloaded before `btstack_set_power_mode(1)` (`source/carplay_bt.m` around 1517). The target's ownership/recovery path is not verified; no blind system daemon unload/kill commands were supplied or executed. Need compatible peer details for the real handshake phase; transport-only mocks or RFCOMM tests are insufficient.

## Physical local FE35/FE36 service probe (2026-11-26)

The user ran the 0.3.2 `--btstack-services` probe on the physical iPad and supplied two complete registration/cleanup cycles. The observed output reported FE35 on local RFCOMM channel 16 with SDP handles 65537 and 65539, FE36 on channel 17 with handles 65538 and 65540, followed by `BTSTACK_LOCAL_SERVICE_CYCLE_OK=1`, `BTSTACK_LOCAL_SERVICE_CYCLE_OK=2`, and `BTSTACK_LOCAL_SERVICES_OK`. This is user-reported physical evidence, not an agent-captured transcript.

The result establishes that the installed BTstack daemon accepted local FE35/FE36 listener and SDP registration, cleanup, and channel reuse across two daemon connections while the probe's required state condition held. It does not establish wireless SDP visibility, peer discovery, negotiated remote channel numbers, link-authentication behavior, dual-channel open/send/receive/close, or a HiCar handshake. Those remain separate Stage 0 gates.

## Read-only ownership probe build (2026-11-26)

The USB SSH path was established through Windows `iproxy` (`localhost:2222` to iPad SSH); the device reported `USB_SSH_OK` and `iPad5,1`. A new read-only `--btstack-ownership` entry point was added to the Theos binary. CI run `45670248895` passed all existing query/service tests, framework/package checks, and produced the updated rootless DEB. The probe reports machine/OS, BTstack socket, daemon file and plist presence, then emits an explicit ownership snapshot completion marker; it does not unload or kill Apple Bluetooth, power the controller, pair, or connect to a peer. The binary is awaiting installation after the USB forwarding session is re-established.

At 00:31–00:32 the correctly spaced print output confirms `system/ch.ringwald.BTstack` is registered, program `/var/jb/usr/bin/BTdaemon`, `state = not running`, `runs = 0`, `last exit code = (never exited)`, and a passive stream listener `/tmp/BTstack`. This is a registered, not-yet-launched service; it is not evidence of a crash. Socket existence was launchd listener evidence, not daemon execution. Next bounded step is a single manual launch followed by state/PID/run/exit inspection; no successful transport operation is claimed.

The user's next screenshot explicitly shows `AUTH_VECTORS_OK`: record the synthetic authentication-vector device run as passed from user-provided screenshot evidence. This does not validate a live authentication transcript or handshake. Installed package version/hash and exit status remain uncaptured.

Further screenshots show `/var/jb/Library/LaunchDaemons/ch.ringwald.BTstack.plist` exists and its contents specify `/var/jb/usr/bin/BTdaemon` and `/tmp/BTstack`. Initial service/process filters showed Apple BTServer entries and grep itself, with no BTdaemon process visible. After the bootstrap instruction, the 00:29 screenshot shows a socket entry (`srw-rw-rw-`, owner root, group daemon) at `/tmp/BTstack`, timestamp 00:26. Bootstrap stdout/exit status was not shown; socket existence is confirmed, daemon health and protocol responsiveness are not. The print attempt shown is malformed (`printsystem/...`, missing a space), so its usage output does not establish service absence. Ask for the correctly spaced read-only `launchctl print system/ch.ringwald.BTstack` result before diagnosing service health. No successful client connection, FE35/FE36 registration or radio I/O is evidenced yet.

## Latest USB install and external ownership audit (2026-11-26)

This section supersedes earlier pending-install and historical next-action notes above. Existing iproxy PID 39484 / port 2222 was reused for root SSH. CI 45670248895's DEB passed remote SHA-256 verification, installed as 0.3.2, and completed the binary `--btstack-ownership` command with exit 0. Its service/process fields explicitly reported `UNAVAILABLE_IN_SANDBOX`; completion is not an ownership PASS. Log: `artifacts/device-validation-20261126/ownership-20261126-022442.log`.

External UID-0 `launchctl print/list` and filtered `ps` captures then established BTdaemon PID 35779 and Apple bluetoothd PID 30370 were simultaneously running. BlueTool was registered but idle; BTLEServer PID 485 was running. Apple BTServer AVRCP/MAP/PBAP subservices were registered but idle; the umbrella `com.apple.BTServer` label was absent. Showcase PID 27255 was present without an observed CarDisplaySim helper. Its recovery guard job and ready handshake were absent, although recovery.plist and `/tmp/showcase_bt_ready` existed; the latter is not fresh readiness evidence. BTdaemon belongs to installed `com.rostane.showcase` 1.0~beta5-3, not a cryptographically pinned source revision.

Raw logs: `artifacts/device-validation-20261126/root-ownership-snapshot-20261126-022903.log` and `root-ownership-detail-20261126-023012.log`. No service/radio/network mutation, signal, phone connection, or repeated query/local-registration/vector probe occurred. Lockdown pairing remains unresolved separately from working USB SSH.

Read-only reference review at Showcase ce9d1d50758f67307deb3f00c901a8e82894930c establishes the applicable rootless handoff and BlueTool-before-bluetoothd restoration ordering; the Taurine force-kill branch is inapplicable. The shell ownership collector now checks root/tool availability, includes Apple/guard jobs and process names without argument lists, records query exits, and no longer depends on missing awk.

## Bounded power/restoration trial and preflight correction (2026-11-26)

After twelve offline mock tests passed, the new host power-only client and launchd recovery guard performed one physical trial via the original USB SSH forwarder. The guard was positively ready before Apple jobs were unloaded. BTstack state progressed 0/1/2/3/0, yielding WORKING and OFF observations. Requested restoration unloaded BTstack, loaded BlueTool then bluetoothd, restored BTstack registration, and was independently checked before guard disarm and active-lock cleanup. No discoverability/SDP/peer commands, phone connection or authentication payload logging occurred. Evidence: `artifacts/device-validation-20261126/power-trial-20261126-024343.log`, `post-power-helper-audit.log`.

The baseline and restored snapshots also showed `CarPlay Simulator` PID 27078, the source-defined rootless Showcase service helper. A path-only name matcher missed this bare comm. This qualifies the trial: direct power/OFF and restored-state evidence stands, but numeric `POWER_TRIAL_PASSED=1` is not a complete uncontested ownership PASS. The matcher and guard process parsing now handle bare names; regression cases include whitespace and failed process queries. The user has been asked to stop the Showcase session normally and report Honor phone readiness. No helper was killed; no second power trial was run. Further radio testing waits for the helper to disappear and a fresh service baseline after Stop. Phone FE35/FE36 transport/security/HiCar and AP gates remain open. Normal restoration was exercised on device; heartbeat/deadline failure restoration has only simulated evidence.

Correction following the user's clarification that Showcase was not started:
the same executable hosts the persistent BAA broker (`Showcase.m:3500–3516,3613`;
`carplay_services.m:6369–6372`). Its name cannot establish an active session.
Latest read-only capture finds PID 27078, started 2026-11-25 10:43:00 by device
time, with the BAA socket present, but no Showcase main process or Bluetooth
helper. This is consistent with a retained broker; socket-to-PID ownership is
not yet established with available device tools. The Stop request and required
helper-disappearance gate above are withdrawn. Current driver conservatively
reports `SHARED_HELPER_ROLE_UNVERIFIED`; the next gate is metadata-only role
verification. No helper was stopped, no radio operation was repeated, and no
broker authentication request, argv/credential/log or key access was made.
