# Stage 0 Tasks

- [x] Inspect reference revisions and working trees; confirm validation directory did not exist.
- [x] Check local GitHub CLI, WSL, SSH aliases and native tool availability without printing credentials.
- [x] Add minimal Kotlin/Native static framework and Objective-C API.
- [x] Add macOS CI workflow, artifact inspection, Theos rootless client/package, and device-run script.
- [x] Copy fixed-reference WifiChannels into shared JVM/Native tests.
- [x] Run workflow on macOS and download framework, header, toolchain/build logs and DEB.
- [x] Verify Theos static link, arm64, iOS 15 minimum, system libraries, ldid CodeDirectory metadata and rootless package layout from CI outputs.
- [ ] Install and run the package on physical iPad mini 4; observe `KOTLIN_BRIDGE_OK`.
- [x] Run WifiChannels shared JVM test on macOS CI (passed).
- [x] Run WifiChannels Native simulator test on macOS CI (passed).
- [ ] Assess WifiConnectionInfo dependency closure and document IOException substitution points.
- [ ] Continue later Stage 0 protocol/platform gates only after bridge gate is evidenced.
