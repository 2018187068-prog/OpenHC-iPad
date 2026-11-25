# Stage 0 Tasks

- [x] Inspect reference revisions and working trees; confirm validation directory did not exist.
- [x] Check local GitHub CLI, WSL, SSH aliases and native tool availability without printing credentials.
- [x] Add minimal Kotlin/Native static framework and Objective-C API.
- [x] Add macOS CI workflow, artifact inspection, Theos rootless client/package, and device-run script.
- [x] Copy fixed-reference WifiChannels into shared JVM/Native tests.
- [x] Run workflow on macOS and download framework, header, toolchain/build logs and DEB.
- [x] Verify Theos static link, arm64, iOS 15 minimum, system libraries, ldid CodeDirectory metadata and rootless package layout from CI outputs.
- [ ] Configure iPad SSH for agent-operated later probes if desired; manual device runs are also supported.
- [x] Physical bridge output `KOTLIN_BRIDGE_OK` reported by user on 2026-11-25. `uname -m`, install logs and device package hash were not independently captured.
- [x] Run WifiChannels shared JVM test on macOS CI (passed).
- [x] Run WifiChannels Native simulator test on macOS CI (passed).
- [x] Assess WifiConnectionInfo minimal dependency closure and document explicit JVM/Native exception substitution and excluded WifiLinkMessages boundary.
- [x] Run new WifiConnectionInfo JVM/Native tests in macOS CI and download 0.2.0 probe artifacts (run 45642428044: 14 JVM / 13 Native simulator tests, all passed).
- [ ] Run 0.2.0 `--wifi` on physical iPad; observe `WIFI_CONNECTION_INFO_OK`.
- [ ] Continue later Stage 0 protocol/platform gates only after bridge gate is evidenced.
