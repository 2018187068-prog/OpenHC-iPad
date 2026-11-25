# OpenHC-iPad 当前交接

更新时间：2026-11-26

## 当前状态

- 工程 `D:\OpenHC-iPad`，分支 `stage0-auth-validation`；当前提交和最新 CI 在本节下方记录。只读参考工程 `D:\OpenHC-iPad-ref` 未修改。
- 目标设备为 iPad mini 4 Wi-Fi (`iPad5,1`)，iPadOS 15.8.8，Dopamine rootless。既有 USB SSH 可用记录不等同于 lockdown 配对恢复。
- 已有物理证据：Kotlin bridge、Wi-Fi parser、认证向量、平台 inventory、BTstack 版本/状态查询、FE35/FE36 本地服务注册/清理两轮，以及 2026-11-26 一次 BTstack power on/off 与 Apple/BTstack 服务恢复闭环。不得重复这些检查。
- 未通过：有限会话 gate 的当前真机观测、无线 SDP、双通道 RFCOMM I/O、installed BTdaemon 事件格式兼容、exclusive controller ownership、no-forced-link-auth 运行时证据和 HiCar 握手。上次 power 闭环中无竞争前提不充分，因此不记 ownership PASS。
- 实现入口：`scripts/btstack-session-gate.py` 是有限点时分类器；Theos C CLI 有 synthetic-only outbound adapter 与不发应用数据的 FE35 listener/SDP/accept/close adapter。`bridge/.../Fe35ControlNegotiator.kt` 新增基于只读 OpenHC 固定 revision 的解码后消息层 TLV 状态机：passive `SocketRequested` 触发 FE36/请求 UUID listener，listener 完成后回 channel/UUID；reconnect 发消息层 command 3，匹配 command 4 后输出本机 connect 方向、channel/UUID。它只完成控制协商核心，当前 C inbound CLI 尚未接入 Nearby frame CRC/加密控制帧 reader，因此不能宣称真实手机控制链路或认证已接通。
- `scripts/capture-btstack-session-evidence.py --capture --output <file>` 提供单次只读 SSH metadata collector，内部运行固定 `--session-owner`（本机 UNIX `LOCAL_PEERPID`、最多 1.5 秒、零应用读写）、一次进程/marker/guard 快照并检查采集窗口不超过 5 秒；无需手工编辑 JSON，不代入历史 PID。缺少 socket owner、进程映射、命令状态或时间窗口异常会写 `snapshot_complete=false`，Trial 在缺少 60 秒内当前快照时仍阻断。该 collector 没有正向 session-state 来源，空 `active_session_pids` 只表示本次未取得正向 PID 绑定状态，不能当作无活动证明；额外/未解释 helper 仍为 UNKNOWN。
- `scripts/btstack-power-trial.py --execute --mode inbound --session-evidence <fresh-file>` 已通过上一基线 CI 验收；它通过固定 rootless C 子命令与独立 SSH channel 运行于 Trial 的 WORKING callback。Trial 单独持有 power lease、heartbeat 与恢复请求；仅确认 C 子进程远端退出后发 OFF，SSH loss/timeout 时由独立 guard 恢复。无 `--execute` 默认不做设备动作，`--mode power-only` 保留。
- 当前会话结论：broker endpoint owner PID 曾与 comm-only `CarPlay Simulator` PID 27078 匹配，且 broker 源码分支在网络会话初始化前进入 broker loop，属已证实 broker 证据；这不代表没有并发活动会话。另有已知活动 helper 的正向观测才分类为活动会话；信息缺失、未解释 shared helper、残留 marker 或恢复活动均为 UNKNOWN。marker、进程名和进程不存在单独不构成放行条件。`CLEAR_SNAPSHOT` 仅表示这组限定指标在该次快照未见，不声称绝对无并发或没有未来竞争。
- 本轮限制：仅本地代码、合成测试及文档；未连接设备、未上电/卸载/配对/改热点/kill、未读取身份或认证材料、未作新签名信任操作，也未启用收费 runner。
- 最近已通过 CI 基线：GitHub-hosted `macos-15` run `45706468742`，revision `c5d49a04c5bdfec4aad6cd732d618a2ab99454ec`，C socket 与 guarded power/restore 测试、Kotlin/Native framework/tests、Theos 0.3.4 均成功；DEB SHA-256 `CE546A9E72142790DA7FB68B03A9F4F59163753B09756F24F51257C6FC6BA871`。它不覆盖本轮新增控制状态机、peer-PID collector 与 `0.3.5` 包。当前 revision/CI 结果在本段更新为新 CI 后补录。

## 下一步路径

本轮只完成离线协商状态机与只读 metadata collector 代码；没有执行设备命令。Synthetic echo peer 是可选工程测试，目前没有证据用户具备它，也不是 HiCar 硬前置。最短真机推进条件是标准 CI 通过后，由用户另行安装相应 DEB、建立既有 USB SSH tunnel，并安排 Honor 20 Pro/HarmonyOS 4.0 正常发起 HiCar 的窗口；先运行 collector 得到不超过 60 秒的新快照，若分类 UNKNOWN 则停止。只有在 C inbound 适配器接上真实 Nearby frame 解码器之后，才能把控制 channel/UUID 协商状态机用于真实手机连接；随后再实现 FE36 listener/connect 的协议调用与状态关联，HiCar auth 握手仍未实现。不得把 synthetic 字节发给真实手机。

真实 Honor 手机用户操作须另行安排；本轮不执行，也不发送 synthetic 测试数据。

## 真机验收卡

完整前置、命令、判定、恢复和用户手机步骤见 `docs/BTSTACK-OWNERSHIP.md` 中的“真机 transport 验收卡”。当前卡片是后续任务，不表示本轮已经执行或要求用户现在操作。热点最小验证方案同文列为独立后续任务。

## 历史证据索引

- 本地 ownership 外部快照、恢复闭环和命令记录：`artifacts/device-validation-20261126/`；详细来源与限制见 `docs/BTSTACK-OWNERSHIP.md`。
- 工具启动路径、SHA-256、SIGKILL 137 和 rootless 路径成功证据：`docs/ROLE-PROBE-DIAGNOSTIC.md`。启动位置差异已解决；终止原因仍未知，不追查 SIGKILL 内核原因。
- 更早 CI `45683689513` / `dddd437` 的 22 项测试、`45698383060` 与 `45702890162` 均为历史证据；本轮 host接线、C adapter 与 package 验收以 `45706468742` 为准。
- 更早的 PID、plist/job 状态、工具启动待验证结论均为历史快照，不可当作当前状态或重复执行指令。lockdown 无需修复。
