# OpenHC-iPad 当前交接

更新时间：2026-11-26

## 当前状态

- 工程 `D:\OpenHC-iPad`，分支 `stage0-auth-validation`；当前提交和最新 CI 在本节下方记录。只读参考工程 `D:\OpenHC-iPad-ref` 未修改。
- 目标设备为 iPad mini 4 Wi-Fi (`iPad5,1`)，iPadOS 15.8.8，Dopamine rootless。既有 USB SSH 可用记录不等同于 lockdown 配对恢复。
- 已有物理证据：Kotlin bridge、Wi-Fi parser、认证向量、平台 inventory、BTstack 版本/状态查询、FE35/FE36 本地服务注册/清理两轮，以及 2026-11-26 一次 BTstack power on/off 与 Apple/BTstack 服务恢复闭环。不得重复这些检查。
- 未通过：有限会话 gate 的当前真机观测、无线 SDP、双通道 RFCOMM I/O、installed BTdaemon 事件格式兼容、exclusive controller ownership、no-forced-link-auth 运行时证据和 HiCar 握手。上次 power 闭环中无竞争前提不充分，因此不记 ownership PASS。
- 实现入口：`scripts/btstack-session-gate.py` 是有限点时分类器；Theos C CLI 有 synthetic-only outbound adapter 与不发应用数据的 FE35 listener/SDP/accept/close adapter。已保存的未提交代码新增 common `Fe35NearbyControlSession`，可从帧字节流解码、握手/解密、调用 `Fe35ControlNegotiator`，再经模拟 listener-ready channel 生成完整应答帧；对应合成 fixture 源码存在，但本机未能运行（无 JDK 编译器），Native/ObjC 构建也未验证。当前 session 构造器是 `internal`，源码中无 ObjC wrapper，C inbound CLI 不读 RFCOMM、不调用 framework；因此不宣称此次工作树的 JVM/Native 通过或端到端 C 链路完成。
- `scripts/capture-btstack-session-evidence.py --capture --output <file>` 提供单次只读 SSH metadata collector，内部运行固定 `--session-owner`（本机 UNIX `LOCAL_PEERPID`、最多 1.5 秒、零应用读写）、一次进程/marker/guard 快照并检查采集窗口不超过 5 秒；无需手工编辑 JSON，不代入历史 PID。缺少 socket owner、进程映射、命令状态或时间窗口异常会写 `snapshot_complete=false`，Trial 在缺少 60 秒内当前快照时仍阻断。该 collector 没有正向 session-state 来源，空 `active_session_pids` 只表示本次未取得正向 PID 绑定状态，不能当作无活动证明；额外/未解释 helper 仍为 UNKNOWN。
- `scripts/btstack-power-trial.py --execute --mode inbound --session-evidence <fresh-file>` 已通过上一基线 CI 验收；它通过固定 rootless C 子命令与独立 SSH channel 运行于 Trial 的 WORKING callback。Trial 单独持有 power lease、heartbeat 与恢复请求；仅确认 C 子进程远端退出后发 OFF，SSH loss/timeout 时由独立 guard 恢复。无 `--execute` 默认不做设备动作，`--mode power-only` 保留。
- 当前会话结论：broker endpoint owner PID 曾与 comm-only `CarPlay Simulator` PID 27078 匹配，且 broker 源码分支在网络会话初始化前进入 broker loop，属已证实 broker 证据；这不代表没有并发活动会话。另有已知活动 helper 的正向观测才分类为活动会话；信息缺失、未解释 shared helper、残留 marker 或恢复活动均为 UNKNOWN。marker、进程名和进程不存在单独不构成放行条件。`CLEAR_SNAPSHOT` 仅表示这组限定指标在该次快照未见，不声称绝对无并发或没有未来竞争。
- 本轮限制：仅本地代码、合成测试及文档；未连接设备、未上电/卸载/配对/改热点/kill、未读取身份或认证材料、未作新签名信任操作，也未启用收费 runner。
- 最新代码验收：GitHub-hosted `macos-15` workflow run `45715083711`，测试 revision `40fe9939b06d4a713c07c6ecc2274d9f046bf391`，结论 success；覆盖 Python/C mock 与 guarded power tests、iOS arm64 Release framework、JVM/Native simulator shared tests 和 Theos rootless 0.3.5 package。FE35 状态机测试在 JVM 与 iOS Simulator 各 7 项、0 failures；C socket adapter 10 项、inbound 5 项、guarded power 24 项均通过。产物 `com.gcbond.openhc-bridge-check_0.3.5_iphoneos-arm64.deb` SHA-256 `805EBA1F4CB5F490E09AF8148C3360461C270F5E52DB04CADF15C2923FD15ADF`，CI 日志、测试报告及 DEB 本地副本位于被忽略的 `artifacts/ci-45715083711/`，未安装。后续仅交接文档提交不改变该测试 revision 的代码。

## 下一步路径

固定 Nearby 依赖来源为只读 `D:\OpenHC-iPad-ref` revision `8132399bea6aa86d68da6d3e1d9e3e001c0a7643`：`OpenHC/core/common/{ByteReader,ByteWriter}.kt`、`codec/{Ea,Crc16Arc,ReceiveBuffer}.kt`、`core/nearby/{Ea,Tlv,NearbyFrame,NearbyFrameDecoder,NearbyFrameCipher,ChannelManagement,SocketMessages,NearbySession}.kt`；行为和向量对照 `core/nearby/src/test/.../WirelessSessionTest.kt` 与 `core/session/src/test/.../RealWirelessFlowTest.kt`。当前新实现闭包已保存，但只 common 测试源静态存在：Windows Gradle `:bridge:jvmTest` 因配置指向仅含 JRE 的 `C:\Program Files\Java\jre1.8.0_461`、缺少 `JAVA_COMPILER` 失败；iOS Native/ObjC framework 需 macOS，尚无本次工作树 CI。协议路径的唯一下一项依赖是新增可导出的 ObjC session wrapper 并由 macOS CI 生成/检查头文件；随后才能把 C `--btstack-control-inbound` 的有界 RFCOMM read、SendControl/OpenAuthListener/Close 和真实 channel callback 接入同一 API，保持 Trial WORKING lease 与恢复顺序。合成 C socket peer 的实际入口验收仍未完成。HiCar auth 握手、DMSDP、媒体仍未实现。真机推进仍需用户具备 Honor 20 Pro/HarmonyOS 4.0 正常发起 HiCar 的窗口、既有 USB SSH tunnel 和适配构建；先用 collector 获取不超过 60 秒的新快照，若分类 UNKNOWN 即停止。不得把 synthetic 字节发给真实手机。

真实 Honor 手机用户操作须另行安排；本轮不执行，也不发送 synthetic 测试数据。

## 真机验收卡

完整前置、命令、判定、恢复和用户手机步骤见 `docs/BTSTACK-OWNERSHIP.md` 中的“真机 transport 验收卡”。当前卡片是后续任务，不表示本轮已经执行或要求用户现在操作。热点最小验证方案同文列为独立后续任务。

## 历史证据索引

- 本地 ownership 外部快照、恢复闭环和命令记录：`artifacts/device-validation-20261126/`；详细来源与限制见 `docs/BTSTACK-OWNERSHIP.md`。
- 工具启动路径、SHA-256、SIGKILL 137 和 rootless 路径成功证据：`docs/ROLE-PROBE-DIAGNOSTIC.md`。启动位置差异已解决；终止原因仍未知，不追查 SIGKILL 内核原因。
- 更早 CI `45683689513` / `dddd437` 的 22 项测试、`45698383060`、`45702890162`、`45706468742` 均为历史证据；FE35 状态机、metadata collector 与 0.3.5 包验收以 `45715083711` 为准。
- 更早的 PID、plist/job 状态、工具启动待验证结论均为历史快照，不可当作当前状态或重复执行指令。lockdown 无需修复。
