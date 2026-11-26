# OpenHC-iPad 当前交接

更新时间：2026-11-26

## 当前状态

- 工程 `D:\OpenHC-iPad`，分支 `stage0-auth-validation`；当前提交和最新 CI 在本节下方记录。只读参考工程 `D:\OpenHC-iPad-ref` 未修改。
- 目标设备为 iPad mini 4 Wi-Fi (`iPad5,1`)，iPadOS 15.8.8，Dopamine rootless。既有 USB SSH 可用记录不等同于 lockdown 配对恢复。
- 已有物理证据：Kotlin bridge、Wi-Fi parser、认证向量、平台 inventory、BTstack 版本/状态查询、FE35/FE36 本地服务注册/清理两轮，以及 2026-11-26 一次 BTstack power on/off 与 Apple/BTstack 服务恢复闭环。不得重复这些检查。
- 未通过：有限会话 gate 的当前真机观测、无线 SDP、双通道 RFCOMM I/O、installed BTdaemon 事件格式兼容、exclusive controller ownership、no-forced-link-auth 运行时证据和 HiCar 握手。上次 power 闭环中无竞争前提不充分，因此不记 ownership PASS。
- 实现入口：`scripts/btstack-session-gate.py` 是有限点时分类器；Theos C `--btstack-control-inbound` 现已串接 bounded RFCOMM data -> `fe35-control-bridge.m` -> 公共 `OHCBFe35ControlBridge`，处理 `SEND_FRAME/OPEN_AUTH_LISTENER/CLOSE_AUTH_LISTENER`，以注册到的 UUID/channel 回调 `listenerReady`，并显式清理两条服务与连接。输入凭据必须由调用方经 stdin 注入固定长度二进制结构（版本、UTF-8 device ID、三段长度前缀 key）；CLI 不打开身份/key 文件，不显示或记录值。Python socket fixture 走该 C CLI 子命令并用测试 bridge 替身检查帧收发、UUID SDP、channel 回调、clean close 和异常清理；本机已跑 Trial/guard mock 25 项。当前提交候选的 C/ObjC/Native 全链路 CI 尚待验证，不把测试替身说成实际执行 Kotlin/Native；生产 Objective-C adapter 直接调用公共 K/N API，Theos build 检查其编译链接。
- `scripts/capture-btstack-session-evidence.py --capture --output <file>` 提供单次只读 SSH metadata collector，内部运行固定 `--session-owner`（本机 UNIX `LOCAL_PEERPID`、最多 1.5 秒、零应用读写）、一次进程/marker/guard 快照并检查采集窗口不超过 5 秒；无需手工编辑 JSON，不代入历史 PID。缺少 socket owner、进程映射、命令状态或时间窗口异常会写 `snapshot_complete=false`，Trial 在缺少 60 秒内当前快照时仍阻断。该 collector 没有正向 session-state 来源，空 `active_session_pids` 只表示本次未取得正向 PID 绑定状态，不能当作无活动证明；额外/未解释 helper 仍为 UNKNOWN。
- `scripts/btstack-power-trial.py --execute --mode inbound --session-evidence <fresh-file>` 已通过上一基线 CI 验收；它通过固定 rootless C 子命令与独立 SSH channel 运行于 Trial 的 WORKING callback。Trial 单独持有 power lease、heartbeat 与恢复请求；仅确认 C 子进程远端退出后发 OFF，SSH loss/timeout 时由独立 guard 恢复。无 `--execute` 默认不做设备动作，`--mode power-only` 保留。
- 当前会话结论：broker endpoint owner PID 曾与 comm-only `CarPlay Simulator` PID 27078 匹配，且 broker 源码分支在网络会话初始化前进入 broker loop，属已证实 broker 证据；这不代表没有并发活动会话。另有已知活动 helper 的正向观测才分类为活动会话；信息缺失、未解释 shared helper、残留 marker 或恢复活动均为 UNKNOWN。marker、进程名和进程不存在单独不构成放行条件。`CLEAR_SNAPSHOT` 仅表示这组限定指标在该次快照未见，不声称绝对无并发或没有未来竞争。
- 本轮限制：仅本地代码、合成测试及文档；未连接设备、未上电/卸载/配对/改热点/kill、未读取身份或认证材料、未作新签名信任操作，也未启用收费 runner。
- 最近一次成功代码验收仍是 run `45751891681` / SHA `e810378c5f3d9e34ebd09a9a7c85f545d79cf2b1`（2026-11-26）：JVM 35/35、iOS Simulator 33/33，Objective-C smoke 编译链接、rootless Theos arm64 DEB 均通过。本轮 C 接线候选加入后尚无 CI 结果；本机 `python scripts/test-btstack-power.py` 25/25 和 Python AST/diff 检查通过，但本机无 clang/Xcode，C socket/ObjC 编译待 macOS workflow。

## 下一步路径

固定上游来源为只读 `D:\OpenHC-iPad-ref` revision `8132399bea6aa86d68da6d3e1d9e3e001c0a7643`；协议实现与测试对应 `OpenHC/core/common`、`core/nearby`，以及 `core/nearby/src/test/.../WirelessSessionTest.kt` 和 `core/session/src/test/.../RealWirelessFlowTest.kt`。本轮候选已改 `theos/btstack-probe.c::transport_inbound`、`theos/fe35-control-bridge.m/.h`、`theos/main.m`、`theos/Makefile`、`scripts/test-btstack-transport-socket.py` 及 Theos workflow 使用的 C mock 替身；Trial 通过继承 FD 输入把有界 key 配置从内存写到 CLI stdin，原 WORKING lease/deadline/guard 恢复顺序未改。下一步唯一依赖是 macOS workflow 证明 C mock/ObjC build/JVM+Native 和 rootless package 全通过；若失败按日志修复。成功后真实 auth 握手、DMSDP、媒体仍未实现；禁止将 synthetic 字节发送给真机。

真实 Honor 手机用户操作须另行安排；本轮不执行，也不发送 synthetic 测试数据。

## 真机验收卡

完整前置、命令、判定、恢复和用户手机步骤见 `docs/BTSTACK-OWNERSHIP.md` 中的“真机 transport 验收卡”。当前卡片是后续任务，不表示本轮已经执行或要求用户现在操作。热点最小验证方案同文列为独立后续任务。

## 历史证据索引

- 本地 ownership 外部快照、恢复闭环和命令记录：`artifacts/device-validation-20261126/`；详细来源与限制见 `docs/BTSTACK-OWNERSHIP.md`。
- 工具启动路径、SHA-256、SIGKILL 137 和 rootless 路径成功证据：`docs/ROLE-PROBE-DIAGNOSTIC.md`。启动位置差异已解决；终止原因仍未知，不追查 SIGKILL 内核原因。
- 更早 CI `45683689513` / `dddd437` 的 22 项测试、`45698383060`、`45702890162`、`45706468742` 均为历史证据；FE35 状态机、metadata collector 与 0.3.5 包验收以 `45715083711` 为准。
- 更早的 PID、plist/job 状态、工具启动待验证结论均为历史快照，不可当作当前状态或重复执行指令。lockdown 无需修复。早先 CI `45715083711`、`45749076797`、`45751378673` 均已被当前 `45751891681` 覆盖。
