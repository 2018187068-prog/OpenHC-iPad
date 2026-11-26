# OpenHC-iPad 当前交接

## Scan transport lifecycle integration (2026-11-26)

Task 2 code is `9aabbb95f72e94257f6a0c2db1de1442da9ebb6b`. The bounded `openhc_btstack_scan_inbound` API consumes a control bridge and a borrowed, serialized `fe35_scan_transport` binding to a started common ScanReceiverSession. The caller captures the session generation and uses CLOCK_MONOTONIC milliseconds for start; its in-memory event sink owns foreground delivery and must invalidate QR/PIN on CLEAR_PAIRING. `stop_fd` requests Stop during partial registration or stream waits; the UI must run the blocking transport off its main thread. This API does not grant controller ownership, create a supervisor, or wire a UIKit screen.

Actual initial RFCOMM acknowledgement and valid FE35 SDP acknowledgement feed separate common callbacks; both must be ready in that generation before one PAIRING_READY. FAILED/Stop/deadline revoke pairing before transport teardown; old generations, duplicate readiness, terminal late callbacks and CLEANED cannot revive it. Only successfully acknowledged resources are explicitly removed, exactly once per transport call; cancellation before an acknowledgement uses daemon client teardown for uncertain pending ownership. A failed SDP reply's garbage handle is never unregistered. A cleanup ordering barrier confirms command processing only; failed barriers report CLEANUP_UNCONFIRMED and close the daemon client.

Validation: Corretto 17 at `C:/Users/quesi/.jdks/corretto-17.0.13` ran the focused ScanReceiverSessionTest (12/12) and complete local JVM suite (47 tests, zero failures). macOS CI [45794539374](https://github.com/2018187068-prog/OpenHC-iPad/actions/runs/45794539374) passed for this exact code SHA, including iOS arm64 and Simulator frameworks, the generated `onTransportEventGeneration:kind:channel:nowMillis:` selector, real Objective-C compilation, shared JVM/Native tests and the rootless package build. Eight new Native socket cases pass: ready_stop, rfcomm_failure, sdp_failure, stop_rfcomm_wait, stop_sdp_wait (late success acknowledgement), deadline_wait, ready_timeout and cleanup_failure; the callback sink additionally checks duplicate readiness, old generation callbacks after restart, terminal late readiness, redacted diagnostics, and CLEAR_PAIRING before exactly-once cleanup. Logs report SCAN_NATIVE_SOCKET_TESTS_OK=8 and FE35_AND_SCAN_KN_ASSERTIONS=432 (190 existing FE35 plus 242 additional scan assertions); the extended C transport inbound socket suite reports 7 cases and 189 wire assertions, including initial RFCOMM/SDP failure ownership cases. The real C/Objective-C/Kotlin-Native path is exercised; only the BTdaemon/socket peer is synthetic. No extra CI dispatch or watch was used.

Next: task 3 UIKit foreground Start/Stop and QR/PIN lifecycle, then task 4 bounded supervisor IPC under the separate plan. No device, radio, installation, real identity/configuration access or phone acceptance occurred. Auth session/TrustStore, Wi-Fi/TCP, DMSDP/media remain outside this slice; QR alone is not authentication or projection.


## Scan session core implementation (2026-11-26)

Task 1 now has common Kotlin source: ScanReceiverSession.start emits OPEN_CONTROL_LISTENER; separate initial-FE35 onControlRfcommReady and onControlSdpReady callbacks must both succeed in the same generation before PAIRING_READY(QR,PIN). Accept revokes QR and permits a one-shot same-PIN AUTH_HANDOFF; Stop, transport failure, reversed clock and deadline emit CLEAR_PAIRING then CLOSE_CONTROL_TRANSPORT. Old-generation callbacks are ignored. Platform callers must execute returned actions in order and schedule tick using deadlineMillis; the model itself performs no I/O or timer scheduling. The existing Fe35ControlBridge.listenerReady remains exclusively the later auth listener callback.

The QR builder/address/host rules follow fixed upstream 8132399bea6aa86d68da6d3e1d9e3e001c0a7643; PIN uses the existing secure entropy source with bounded unbiased 20-bit rejection sampling. Inputs are memory-only and diagnostics redact QR/PIN/host/address. Ten new common tests cover synthetic exact QR/UTF-8, leading zero, rejection boundaries, partial startup, stale events, expiration, cleanup and same-PIN handoff. Local Gradle JVM execution was blocked by the existing JRE lacking JAVA_COMPILER/JDK tools; diff whitespace check passed. macOS CI validation is pending, so source existence is not yet a Native test PASS.

This implements only the session model. No screen QR/scan-capable app, real FE35 start/stop integration, root supervisor or IPC exists yet. Next is task 2: wire actual transport listener/SDP readiness and stop/cleanup to this model, using a synthetic BTdaemon boundary. No device/radio/identity-file access occurred. Real-phone scanning remains unavailable; FE36 auth/session, Wi-Fi/TCP, DMSDP/media remain outside this change.


更新时间：2026-11-26

## 当前结论：先补扫码启动入口（2026-11-26）

用户已知工作流程是接收端显示二维码后手机扫码。已撤销先前的手机主动发起指引；当前不能启动 headless Trial 等待真实来机。固定上游 8132399bea6aa86d68da6d3e1d9e3e001c0a7643 的 README:41 与 WirelessReceiverSession.kt:169–177、225–235 明确：接收端开始 → FE35 监听实际就绪 → PairingReady → 显示二维码及同一会话连接码 → 手机扫码按真实地址查 SDP 并连接。

已具备：原 identity 的本地 provider 字段兼容；iPad5,1 已安装 CI45775185368 / b4c66242 的 0.3.5 且二进制 hash 匹配；64 KiB collector 一次完整快照分类 BROKER。后者仅为有限点时分类，不证明绝对无并发，也不证明接收端可扫码或真机 HiCar 可测。

当前运行入口仍只有 Theos 命令行控制桥；本次新增扫码模型与 PairingQrCode 纯逻辑，尚缺二维码编码/显示、真实监听到模型及 UI 的接线、完整 WirelessReceiverSession/runner/认证与网络编排。BLE/GATT 也未迁移，但上游手动扫码不依赖它，不能列为扫码必需条件。认证、DMSDP、媒体仍未实现。本次仅查源码和改文档，无设备/无线操作。

最小下一软件任务：将真实 transport listener-ready/stop 接到本次新增 Native 会话核心，之后实现 UIKit 前台 app及有界 supervisor IPC。四项验收和平台未决点见 docs/SCAN-STARTUP-IMPLEMENTATION.md；本轮只完成审计，未实现这些新增部件，不安排手机试验。

扫码启动实现边界审计已完成：见 [四项实施任务](docs/SCAN-STARTUP-IMPLEMENTATION.md)。下一软件动作是实时 transport listening-ready/stop 接线；UIKit app 与 IPC 尚需实现。前台页面常驻不延长有界 power lease，不启动真实手机试验。

## 当前状态

- 工程 `D:\OpenHC-iPad`，分支 `stage0-auth-validation`；当前提交和最新 CI 在本节下方记录。只读参考工程 `D:\OpenHC-iPad-ref` 未修改。
- 目标设备为 iPad mini 4 Wi-Fi (`iPad5,1`)，iPadOS 15.8.8，Dopamine rootless。既有 USB SSH 可用记录不等同于 lockdown 配对恢复。
- 已有物理证据：Kotlin bridge、Wi-Fi parser、认证向量、平台 inventory、BTstack 版本/状态查询、FE35/FE36 本地服务注册/清理两轮，以及 2026-11-26 一次 BTstack power on/off 与 Apple/BTstack 服务恢复闭环。不得重复这些检查。
- 未通过：有限会话 gate 的当前真机观测、无线 SDP、双通道 RFCOMM I/O、installed BTdaemon 事件格式兼容、exclusive controller ownership、no-forced-link-auth 运行时证据和 HiCar 握手。上次 power 闭环中无竞争前提不充分，因此不记 ownership PASS。
- 实现入口：`scripts/btstack-session-gate.py` 是有限点时分类器；Theos C `--btstack-control-inbound` 经生产 `fe35-control-bridge.m` 调用公开 `OHCBFe35ControlBridge`，处理 `SEND_FRAME/OPEN_AUTH_LISTENER/CLOSE_AUTH_LISTENER`、UUID/channel 的 `listenerReady` 和服务/CID清理。iOS Simulator 同一执行进程运行真实 `main.m` CLI、`btstack-probe.c::transport_inbound`、生产 ObjC adapter 与 Kotlin/Native framework，由本机合成 BTdaemon peer 驱动完整 Nearby 字节流。3 个场景通过、190 assertions：成功完整帧往返 86，listener 注册失败及清理 72，incoming timeout 32；覆盖分片/合帧、加密 command-4 响应、heartbeat 所有权未转移及限时清理。simulator-only peer 使用 loopback TCP 跨主机/Simulator 边界；生产 Theos 继续使用 Unix socket。stdin 配置有界，CLI 不读身份/key 文件，不打印输入或帧数据。历史 C-only socket mock/Trial guard 测试仍独立覆盖。
- `scripts/capture-btstack-session-evidence.py --capture --output <file>` 提供单次只读 SSH metadata collector，内部运行固定 `--session-owner`（本机 UNIX `LOCAL_PEERPID`、最多 1.5 秒、零应用读写）、一次进程/marker/guard 快照并检查采集窗口不超过 5 秒；无需手工编辑 JSON，不代入历史 PID。缺少 socket owner、进程映射、命令状态或时间窗口异常会写 `snapshot_complete=false`，Trial 在缺少 60 秒内当前快照时仍阻断。该 collector 没有正向 session-state 来源，空 `active_session_pids` 只表示本次未取得正向 PID 绑定状态，不能当作无活动证明；额外/未解释 helper 仍为 UNKNOWN。
- `scripts/btstack-power-trial.py --execute --mode inbound --session-evidence <fresh-file>` 已通过上一基线 CI 验收；它通过固定 rootless C 子命令与独立 SSH channel 运行于 Trial 的 WORKING callback。Trial 单独持有 power lease、heartbeat 与恢复请求；仅确认 C 子进程远端退出后发 OFF，SSH loss/timeout 时由独立 guard 恢复。无 `--execute` 默认不做设备动作，`--mode power-only` 保留。
- 当前会话结论：broker endpoint owner PID 曾与 comm-only `CarPlay Simulator` PID 27078 匹配，且 broker 源码分支在网络会话初始化前进入 broker loop，属已证实 broker 证据；这不代表没有并发活动会话。另有已知活动 helper 的正向观测才分类为活动会话；信息缺失、未解释 shared helper、残留 marker 或恢复活动均为 UNKNOWN。marker、进程名和进程不存在单独不构成放行条件。`CLEAR_SNAPSHOT` 仅表示这组限定指标在该次快照未见，不声称绝对无并发或没有未来竞争。
- 本轮限制：仅本地代码、合成测试及文档；未连接设备、未上电/卸载/配对/改热点/kill、未读取身份或认证材料、未作新签名信任操作，也未启用收费 runner。
- 最近一次代码验收：SHA `fe29b49a0a020a14e1dc087d3e5894ce084f88b1`，macOS workflow `45765343940` 于 2026-11-26 全绿。JVM 35/35、iOS Simulator 33/33；同一真实 CLI/C/ObjC/Kotlin-Native integration 3/3、190 assertions；framework/header 检查与 Theos rootless arm64 DEB 通过。
- 本机地址 provider 当前 tested SHA `b4c66242c775af7470504fb365cba3a02d8d9fc6`，macOS CI `45775185368` 全绿；新增 C socket 地址查询3/3（valid HCI completion、controller error、timeout），Trial 26/26、provider 3/3、simulator、JVM/Native、framework/header 与 Theos rootless arm64 DEB均通过。固定上游依据：`hci.c:2062` 反转 Command Complete 的 BD_ADDR 写入本机 `local_bd_addr`；`daemon.c:1340` 转发普通 HCI command，普通 Command Complete 经 `daemon_emit_packet(NULL, ...)` 广播；`Showcase/source/carplay_bt.m:404` 发送 `hci_read_bd_addr`。Trial 仅在既有 WORKING callback 内查询本机地址，二进制六字节经过匿名 pipe 与现有 identity provider；无手填地址、argv/env/log 输出，不使用 peer address。现有 CLI 接受 identity 文件或 OPENHC_IDENTITY_DIR，缺失配置返回 IDENTITY_CONFIG_UNAVAILABLE；该接口不生成/显示扫码入口，当前不能作为真实手机验收步骤。认证握手、HiCar/DMSDP、媒体仍未实现。
- 本地配置 provider 已验收：源码 SHA `8e7ccf357155460c2237a7e50de9c42726937322`，macOS workflow `45769151355` 全绿；provider 3/3、Trial/guard 25/25、Native socket integration 190 assertions、JVM/Native suite 与 framework/Theos package 检查通过。当前 HEAD `7c9cf6339394364508c3ca2ce06b468e35430a26` 仅包含后续交接文字校正，provider 代码测试以 `8e7ccf3` 为准。测试使用 synthetic identity fixture；未读真实配置或操作设备。

## 下一步路径

按扫码启动实现审计的四项任务补齐接收端 UI/会话入口；当前不安排 Honor 扫码或手机主动连接，不运行 Trial 等真实来机。方向仍是接收端扫码启动 → 蓝牙控制 → auth → Wi-Fi/TCP → DMSDP/媒体。二维码显示不代表认证或投屏实现完成。

## 扫码启动卡

固定上游顺序、已实现/缺失边界和下一软件任务见 docs/BTSTACK-OWNERSHIP.md；历史 guarded inbound 参数与恢复设计仅为底层控制测试基础，不是当前可执行的手机验收卡。既有探针证据保留，不重做。

## 历史证据索引

- 本地 ownership 外部快照、恢复闭环和命令记录：`artifacts/device-validation-20261126/`；详细来源与限制见 `docs/BTSTACK-OWNERSHIP.md`。
- 工具启动路径、SHA-256、SIGKILL 137 和 rootless 路径成功证据：`docs/ROLE-PROBE-DIAGNOSTIC.md`。启动位置差异已解决；终止原因仍未知，不追查 SIGKILL 内核原因。
- 更早 CI `45683689513` / `dddd437` 的 22 项测试、`45698383060`、`45702890162`、`45706468742` 均为历史证据；FE35 状态机、metadata collector 与 0.3.5 包验收以 `45715083711` 为准。
- 更早的 PID、plist/job 状态、工具启动待验证结论均为历史快照，不可当作当前状态或重复执行指令。lockdown 无需修复。CI `45757974503` 的控制桥基线已由 `45765343940` 的真实 CLI/C/ObjC/Kotlin-Native socket integration 覆盖。
