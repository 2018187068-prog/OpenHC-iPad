# Stage 0 Validation Report

Date: 2026-11-25

## Confirmed from source

- Reference OpenHC revision: `8132399bea6aa86d68da6d3e1d9e3e001c0a7643`; Showcase revision: `ce9d1d50758f67307deb3f00c901a8e82894930c`. Both worktrees reported clean.
- The reference version catalog pins Kotlin 2.1.20 and Gradle wrapper properties pin 8.13.
- Session documentation says core is pure Kotlin/JVM and the session composes nearby/auth/dmsdp/hisight; `SocketRunner` owns `java.net` blocking I/O.
- `MalformedMessageException` extends `IOException`.
- `WifiChannels.kt` is a self-contained candidate, while `WifiConnectionInfo.kt` uses `MalformedMessageException`, `WifiChannels`, and other platform-free Kotlin/JVM APIs; dependency review and tests remain pending.
- The copied `WifiChannels.kt` file's SHA-256 matches the fixed reference source: `F36BEDCAD3EF407D0002C9D461579DFC527F05C7C43B9703AAE714DB63EC9CEB`.

## Environment checks

- Windows worktree: `D:\orcafile`; validation directory did not exist before setup.
- AGENTS.md: none found in `D:\`, `D:\orcafile`, or the new validation root.
- WSL: no installed/registered distribution; `wsl --exec` requests WSL installation.
- GitHub CLI: not authenticated; no repository listing was obtained.
- SSH config has aliases `aliyun-vps` and `singa-vps` only. No device alias was found; no host was contacted. No SSH agent identities were listed.
- Windows PATH has no `xcrun`, `clang`, `theos`, or `ldid`.

## Implemented, not yet built

Added a minimal Kotlin Multiplatform `iosArm64` static framework with exported `BridgeSelfCheck.selfCheck()`, common `WifiChannels` source/tests targeting JVM and iOS simulator, a macOS-15 GitHub Actions workflow, framework inspection script, Theos arm64/iOS-15 rootless command-line package targeting `/usr/bin`, and a device-run helper. The expected device output is `KOTLIN_BRIDGE_OK`.

## Validation status

- Source/configuration review: completed for the items above.
- Kotlin/Native compilation: not run; no local Apple toolchain and GitHub Actions cannot be dispatched while GitHub CLI is unauthenticated. Gradle configuration on Windows completed and explicitly disabled both Apple targets.
- Objective-C link, static-link dependency inspection, ldid/package validation: not run; CI workflow has not run.
- Simulator: not run; simulator success would not establish device success.
- Physical iPad mini 4: not run; no configured device SSH connection was found.
- WifiChannels JVM/Native shared test: implemented against the fixed source; the JVM task was attempted but could not start because the machine exposes only Java 8 JRE (no compiler). A temporary JDK download stalled and was stopped. Native simulator tests need macOS CI.

## WifiConnectionInfo dependency assessment (source review only)

`WifiConnectionInfo` depends on `WifiMode`, `WifiChannels`, `Ipv4Text.isCanonical`, Kotlin `Regex`/collections/string APIs, and `MalformedMessageException`. No Java API is directly referenced in `WifiConnectionInfo`; the blocker is the exception base class in `java.io.IOException` (and its `cause` constructor). A narrowly scoped migration can keep parse behavior while introducing a common exception type, but callers that catch `IOException` must be audited. `Ipv4Text` is a small pure Kotlin IPv4 parser in `core/common/codec`; its edge cases and test vectors still need a separate review before treating this slice as migration-ready.

Stage 0 first gate is **blocked on external execution prerequisites**, not passed. The workflow and scripts are locally reviewable in this project, but their unexecuted assumptions remain unverified.
