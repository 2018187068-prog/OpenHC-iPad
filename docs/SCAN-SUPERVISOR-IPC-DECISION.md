# Scan UI to helper IPC prototype

**Phase:** scan-entry development. **Target:** iPad5,1 / iPadOS 15.8.8 / Dopamine rootless.
**Scope decision:** Unix-domain socket to a separate rootless LaunchDaemon is the first prototype, because it uses the iOS 15 POSIX socket API, keeps the protocol explicit, and can bind inside the rootless prefix. This is a bounded development PING/PONG only. It does not enable the production scan backend or establish a production authorization boundary.

## Why this path

The Theos application target packages `OpenHCScanDemo.app` under `/var/jb/Applications`; the helper package places its executable at `/var/jb/usr/libexec/openhc-scan-ping-helper`, its LaunchDaemon plist at `/var/jb/Library/LaunchDaemons/com.gcbond.openhc-scan-ping-helper.plist`, and a root-owned runtime directory at `/var/jb/var/run/openhc`. The helper derives relocated rootless paths with Theos `ROOT_PATH`; the plist uses the stable `/var/jb` bootstrap alias.

This is distinct from an App Store app installed into its managed container. Apple’s app-sandbox model confines that app to its container and entitled services; code living in a jailbreak bootstrap’s `/var/jb/Applications` is not an App Store installation. However, Theos packaging and that path alone do **not** prove that the target jailbreak launches this app unsandboxed or permits access to `/var/jb/var/run`. The PoC deliberately treats socket connect as fallible, and the exact target must confirm it. Do not add an invented entitlement or claim a bundle identifier authenticates the client.

The server is a launchd-managed root process. It requires a root-owned, non-group/world-writable runtime directory, creates a root-owned socket with group `mobile` and mode `0660`, and uses `getpeereid(2)` to compare kernel-provided peer effective UID/GID to the system `mobile` account. It never trusts a caller-supplied identity. It reads one bounded line through EOF and returns `PONG\n` only for exactly `PING\n`; all other peers/frames are closed. Each client read/write is limited to 1.5 seconds, the backlog is four, and the app does connect/read/write off the main queue with a per-poll timeout capped at five seconds. Stop/restart cleanup unlinks only an existing socket owned by root; the helper refuses a non-socket or non-root-owned stale path.

**Credential guarantee and limit:** `getpeereid` proves the peer’s effective account credentials as supplied by the kernel; it does not distinguish this UIKit bundle from another process running as `mobile`, and this PoC does not verify a code signature or entitlement. The directory/socket owner and mode limit pathname replacement/connect access under the ordinary filesystem model, but jailbreak-wide root access can replace those assumptions. The fixed PING/PONG helper has no BT, power, identity, QR, or arbitrary command interface, so accepting any `mobile` peer is proportionate only for this harmless local development endpoint. Do not carry this authentication model into a privileged production supervisor without a target-supported app identity check and review.

Theos rootless packaging establishes package placement, not app sandbox status. Dopamine 2.x `BaseBin/launchdhook/src/daemon_hook.m` adds plists from `JBROOT_PATH(@"/Library/LaunchDaemons")` to launchd’s daemon dictionary and search paths, which is evidence that this deployment shape is recognized by the target-family bootstrap. It does not prove this newly added plist will be loaded, the service will run as root, the socket path is accessible to this app, or that `getpeereid` returns the assumed mobile credentials on iPad5,1/iOS 15.8.8. The plist uses `RunAtLoad` and `KeepAlive` with launchd throttling; the helper tolerates one client at a time, exits cleanly on SIGTERM, and removes its socket on graceful exit. A crash can leave a stale socket, which the relaunched helper removes after verifying root ownership. No separate heartbeat or Bluetooth lease is involved.

## Code and build entry

The existing Start action runs the fake scan session and, in parallel, invokes the app-side `probeIndependentHelperWithCompletion:` method. `OHCScanHelperClient` performs connect/write/read off the main queue and returns `PONG` or an unavailable result; a small status row displays the outcome. There is no additional button and no in-process socketpair mock. The helper executable is in `theos/scan-supervisor/main.c`; its launchd job and package layout are alongside it. `scripts/check-scan-supervisor-helper.sh` builds/extracts the rootless helper package and checks the binary, plist, arm64 architecture, link dependencies and signature metadata. The existing Simulator UI build compiles the app client, but does not launch a helper or claim an independent-process response test.

On a Mac with the static framework already built, `scripts/check-scan-ui.sh` builds/tests the existing Simulator UI and packages the UIKit app (including the asynchronous client). The helper check builds the rootless package, runs the actual helper as an independent host process against a separate Python client, and places the harmless `.deb` plus integration log under `artifacts/scan-supervisor/` for CI collection. It covers fixed PING/PONG, malformed and oversized requests, a slow partial request against the 1.5 second server deadline, concurrent second-instance rejection without socket replacement, SIGTERM cleanup, and restart. The integration build defines its test socket and same-UID policy at compile time; production has no argv/environment credential override and always checks `getpeereid` against the `mobile` account.

The `flock` on a root-owned lock file enforces one active helper even if launchd temporarily overlaps service instances. The daemon owns listener/client descriptor closure; signal handlers only set a `sig_atomic_t` stop flag, and the poll loop notices it within its bounded wait. Socket cleanup happens only after this process successfully bound the path. The Mac integration run validates these process and filesystem behaviors for the host OS only; it does not establish iPad root/mobile values, the app's sandbox treatment, launchd loading, or app-to-socket reachability. The checks require Theos, ldid, dpkg and Xcode tools:

```sh
THEOS=/path/to/theos bash scripts/check-scan-supervisor-helper.sh
```

## Minimum harmless target-device validation

**Packaging prerequisite (2026-11-27):** artifact `15133189055` / run `45847497955` is forbidden for installation: the real DEBs carry builder UID/GID `501:20` even on the helper's required root-owned runtime directory. The macOS process tests did not validate these archive owners. Both demo Makefiles now explicitly select `scripts/scan-demo-dpkg-deb.sh`, which delegates to native `dpkg-deb --root-owner-group` rather than Darwin's default `dm.pl`. Theos' `makefiles/package/deb.mk` invokes `_THEOS_PLATFORM_DPKG_DEB` as a writer with `-b`, and `makefiles/platform/Darwin.mk` defaults this variable to `dm.pl`; overriding the executable per demo target preserves the normal Theos rootless staging/package flow. No filesystem ownership rewrite, privileged build, install-time recursive chown, or peer-check relaxation is involved. The supported dpkg switch sets archived IDs to root without requiring the build user's effective UID to be root.

The first native-writer run `45855259305` exposed a separate compression compatibility error: Theos still supplied its legacy `-Zlzma` default, rejected by Homebrew dpkg 1.23.12. Both targets now use the documented `THEOS_PLATFORM_DEB_COMPRESSION_TYPE = xz` variable (see <https://theos.dev/docs/variables>), so Theos itself chooses the supported format instead of filtering or discarding arguments in the wrapper. CI runs a native dpkg build/read roundtrip for both layouts before either demo package build, records its tool version, and requires xz data compression in the final package checker alongside all existing ownership/security checks. That preflight is synthetic host evidence; accepted new device DEBs still require their own successful archive checks and recorded hashes.

`scripts/check-scan-demo-archive.py` checks the numeric tar header UID/GID for both control and data archives before extraction or artifact publication. All members, including shared ancestors, must be `0:0`; directories/executables must be `0755`, metadata/plists must be `0644`. Only the exact two demo layouts and fixed helper launchd keys are accepted; symlinks, hardlinks, devices, duplicate/traversal paths, maintainer scripts/triggers and unexpected payloads are rejected. This root-only packaging policy requires no app-specific ownership exception: the app executable runs under the launcher's credentials, and its writable state belongs in the ordinary app data container, not its package directory. The regression suite explicitly rejects `501:20` fixtures for both packages and checks root-owned positive fixtures. Actual built DEBs must independently pass the same archive checker; extracted-host `stat` cannot substitute for it.

Packaging source references: <https://github.com/theos/theos/blob/master/makefiles/package/deb.mk>, <https://github.com/theos/theos/blob/master/makefiles/platform/Darwin.mk>, and dpkg-deb `--root-owner-group` at <https://manpages.debian.org/bookworm/dpkg/dpkg-deb.1.en.html>.

After the coordinator’s planned package installation, use the authorized root shell to run only these checks; they do not inspect identity material or touch Bluetooth/power:

```sh
launchctl print system/com.gcbond.openhc-scan-ping-helper
stat -f '%u:%g %Lp %N' /var/jb/var/run/openhc /var/jb/var/run/openhc/scan-ping.sock
```

Open the demo and tap its existing **Start · 开始演示** action. Expected result: the helper status row changes to `独立 helper：PONG（固定合成响应）`; the socket is owned by root, group `mobile`, mode `660`; the directory is root-owned and not group/world writable. Because the daemon replies only after `getpeereid` accepts the kernel UID/GID, this one observation settles app-path reachability and the effective mobile UID/GID check on the target. A request failure, helper launch failure, unexpected peer credentials, or inability to load the rootless plist is a NO-GO; preserve the production backend as disabled rather than weakening the peer check. No install, device command, or wireless action was run for this patch.

## Alternatives

- **Mach service / XPC:** retained for later only if the target bootstrap and iOS 15 API prove the service namespace and peer identity rules. Do not use newer `XPCSession` API availability as evidence for iOS 15, and do not equate generic macOS XPC service examples with a jailbreak daemon.
- **launchd socket activation:** not selected for this first test because it adds launchd socket handoff/API details while the direct Unix socket can answer the main open question: can this particular rootless UIKit app reach a pathname and what kernel peer UID/GID does the helper observe?
- **App Store sandbox app:** expected to be constrained to its container absent documented entitlements; that is not the distribution model of this Theos rootless application. The jailbreak’s actual sandbox treatment still requires the single harmless target observation above.

## Sources checked

- Theos rootless package documentation: <https://theos.dev/docs/rootless>
- Dopamine 2.x official launchd hook: <https://github.com/opa334/Dopamine/blob/2.x/BaseBin/launchdhook/src/daemon_hook.m>
- Apple Platform Security, iOS/iPadOS third-party apps and sandbox: <https://support.apple.com/guide/security/security-of-runtime-process-sec15bfe098e/web>
- Darwin `getpeereid(2)` is the kernel credential interface used by the C helper; the result is account identity, not bundle identity.
