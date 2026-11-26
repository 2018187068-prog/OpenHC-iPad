# OpenHC-iPad 当前交接

更新时间：2026-11-26

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
- 本次真机准备核对：同一 CI artifact 内 0.3.5 arm64 DEB SHA-256 `5A33A0B5B91CD3133930346BC2F912A51B9A6C5F367800406B37305878FA3004`；设备最近有记录的安装为 0.3.2，当前是否安装 0.3.5 未知，不能据 CI build 推断安装。新增本地 provider 复用上游 `openhc-identity.json` schema 中的 host 型号与 `nearbyKeys`，按上游算法生成 device ID；三段 nearby key material 从现有配置读取，不声称为协议固定常量，也不要求用户另填。唯一仍需独立来源的是本机无线 Bluetooth address，经 bounded FD 输入；本机尚无读取该地址的 provider。identity 文件路径可显式传入或由既有 `OPENHC_IDENTITY_DIR` 约定解析。该地址输入、窗口新鲜 ownership 快照、guard ready 与安装核对是启动真机 trial 前置，历史证据不可代替。

## 下一步路径

固定上游来源为只读 `D:\OpenHC-iPad-ref` revision `8132399bea6aa86d68da6d3e1d9e3e001c0a7643`；协议实现与测试对应 `OpenHC/core/common`、`core/nearby`、`WirelessSessionTest.kt` 和 `RealWirelessFlowTest.kt`。离线控制协商已由真实 CLI/C/ObjC/Kotlin-Native 与 synthetic socket peer 端到端验收。后续需另行安排真机条件：当前会话 ownership/transport gate、无线 SDP、双通道 RFCOMM 与 installed BTdaemon 事件兼容证据；不得重跑历史 probe。认证握手、HiCar/DMSDP、媒体仍未实现；本次无真实身份或认证材料，也未发送合成字节到设备。

真实 Honor 手机用户操作须另行安排；本轮不执行，也不发送 synthetic 测试数据。当前可达范围是 FE35 控制协商/控制帧 listener callback，不含认证握手、HiCar/DMSDP 完整会话或媒体。

## 真机验收卡

完整前置、命令、判定、恢复和用户手机步骤见 `docs/BTSTACK-OWNERSHIP.md` 中的“真机 transport 验收卡”。当前卡片是后续任务，不表示本轮已经执行或要求用户现在操作。热点最小验证方案同文列为独立后续任务。

## 历史证据索引

- 本地 ownership 外部快照、恢复闭环和命令记录：`artifacts/device-validation-20261126/`；详细来源与限制见 `docs/BTSTACK-OWNERSHIP.md`。
- 工具启动路径、SHA-256、SIGKILL 137 和 rootless 路径成功证据：`docs/ROLE-PROBE-DIAGNOSTIC.md`。启动位置差异已解决；终止原因仍未知，不追查 SIGKILL 内核原因。
- 更早 CI `45683689513` / `dddd437` 的 22 项测试、`45698383060`、`45702890162`、`45706468742` 均为历史证据；FE35 状态机、metadata collector 与 0.3.5 包验收以 `45715083711` 为准。
- 更早的 PID、plist/job 状态、工具启动待验证结论均为历史快照，不可当作当前状态或重复执行指令。lockdown 无需修复。CI `45757974503` 的控制桥基线已由 `45765343940` 的真实 CLI/C/ObjC/Kotlin-Native socket integration 覆盖。
