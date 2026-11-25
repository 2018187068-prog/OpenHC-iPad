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
- First macOS CI run compiled and linked the `iosArm64` framework successfully in 1m 6s; a local inspection script then failed because it passed the archive path to `lipo` in the wrong argument position. Corrected the architecture inspection and added a static-archive minimum-iOS check before rerun.
- Second macOS CI run passed static-framework build/inspection and both shared JVM and Native simulator test tasks. Theos bootstrap then failed because its recursive clone already populated the `sdks` submodule and the workflow tried to clone that directory a second time. Removed the redundant clone; Theos package/signing checks remain pending.
- Third macOS CI run again passed the framework and shared tests, then compiled the Theos Objective-C source far enough to show the framework header search path was not being passed to Clang. Switched to Theos' documented per-target compiler/linker flags for `-F`; also corrected the device-binary `lipo` argument order.
- Fourth macOS CI run passed framework and shared tests and compiled through header inclusion; Kotlin's generated Objective-C class name carries the module prefix `OHCB`. Updated the Theos client to call the generated `OHCBBridgeSelfCheck` class; package/link/signing checks remain pending.
- Fifth macOS CI run passed framework inspection, both shared test targets, Theos compile/link, rootless staging, and Theos signing; it produced an `iphoneos-arm64` DEB. Post-build inspection stopped because macOS lacks `dpkg-deb` by default. Added Homebrew `dpkg` and corrected the expected package architecture field from `iphoneos-arm` to `iphoneos-arm64`.
- Sixth macOS CI run passed framework, shared tests, Theos compile/link/signing and DEB creation/extraction. The final inspection failed because `ldid -e` returns failure when asked to extract entitlements from this binary, which intentionally has none. The same log showed a CodeDirectory; switched the check to assert that signature metadata is present instead of requiring an entitlement blob.

## WifiConnectionInfo dependency assessment (source review only)

`WifiConnectionInfo` depends on `WifiMode`, `WifiChannels`, `Ipv4Text.isCanonical`, Kotlin `Regex`/collections/string APIs, and `MalformedMessageException`. No Java API is directly referenced in `WifiConnectionInfo`; the blocker is the exception base class in `java.io.IOException` (and its `cause` constructor). A narrowly scoped migration can keep parse behavior while introducing a common exception type, but callers that catch `IOException` must be audited. `Ipv4Text` is a small pure Kotlin IPv4 parser in `core/common/codec`; its edge cases and test vectors still need a separate review before treating this slice as migration-ready.

Stage 0 first gate is **blocked on external execution prerequisites**, not passed. The workflow and scripts are locally reviewable in this project, but their unexecuted assumptions remain unverified.
