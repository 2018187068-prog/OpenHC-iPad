# OpenHC-iPad 当前交接

更新时间：2026-11-26

## 当前状态

- 工程 `D:\OpenHC-iPad`，分支 `stage0-auth-validation`；当前提交和最新 CI 在本节下方记录。只读参考工程 `D:\OpenHC-iPad-ref` 未修改。
- 目标设备为 iPad mini 4 Wi-Fi (`iPad5,1`)，iPadOS 15.8.8，Dopamine rootless。既有 USB SSH 可用记录不等同于 lockdown 配对恢复。
- 已有物理证据：Kotlin bridge、Wi-Fi parser、认证向量、平台 inventory、BTstack 版本/状态查询、FE35/FE36 本地服务注册/清理两轮，以及 2026-11-26 一次 BTstack power on/off 与 Apple/BTstack 服务恢复闭环。不得重复这些检查。
- 未通过：有限会话 gate 的当前真机观测、无线 SDP、双通道 RFCOMM I/O、installed BTdaemon 事件格式兼容、exclusive controller ownership、no-forced-link-auth 运行时证据和 HiCar 握手。上次 power 闭环中无竞争前提不充分，因此不记 ownership PASS。
- 实现入口：`scripts/btstack-session-gate.py` 是有限、点时证据分类器；`theos/btstack-probe.c` 包含 synthetic-only outbound adapter 和无应用数据的 FE35 inbound listener/SDP/accept/close adapter。`scripts/btstack-power-trial.py --execute --mode inbound` 已把固定 `--btstack-control-inbound RUN_DIR` 子命令接到 `Trial.run()` 的 WORKING callback；无 `--execute` 时不执行设备动作，`--mode power-only` 保留旧 power-only 模式。C 子命令使用独立 SSH session、固定 rootless executable 和受控 run-dir；只有确认远端退出后才 OFF/请求恢复。超时或 SSH loss 时不发 OFF/restore-request，停止唯一 heartbeat 并将恢复交给独立 guard。该模式仅验证 inbound/listen/accept/close，不解析 HiCar 控制/认证协议，也不启动 OpenHC discovery。共享 helper 需要 60 秒内完整的 `--session-evidence` metadata；缺失或 UNKNOWN 会阻断，当前尚无新的现场快照。`scripts/btstack-transport-runner.py` 仍是显式计划驱动的离线双通道核心。
- 当前会话结论：broker endpoint owner PID 曾与 comm-only `CarPlay Simulator` PID 27078 匹配，且 broker 源码分支在网络会话初始化前进入 broker loop，属已证实 broker 证据；这不代表没有并发活动会话。另有已知活动 helper 的正向观测才分类为活动会话；信息缺失、未解释 shared helper、残留 marker 或恢复活动均为 UNKNOWN。marker、进程名和进程不存在单独不构成放行条件。`CLEAR_SNAPSHOT` 仅表示这组限定指标在该次快照未见，不声称绝对无并发或没有未来竞争。
- 本轮限制：仅本地代码、合成测试及文档；未连接设备、未上电/卸载/配对/改热点/kill、未读取身份或认证材料、未作新签名信任操作，也未启用收费 runner。
- 本轮 host 接线提交 `57a556b`、跨平台恢复夹具修复提交 `c5d49a0`。GitHub-hosted `macos-15` workflow run `45706468742` 对 `c5d49a04c5bdfec4aad6cd732d618a2ab99454ec` success（2026-11-25 21:44 UTC）。CI 编译并运行 C socket executable：outbound 10/10、close/reopen 2 次、FE35 inbound 5/5；新增 power/guard 测试 24/24；iOS framework、shared JVM/Native tests 和 Theos arm64 package 0.3.4 均通过。DEB SHA-256 `CE546A9E72142790DA7FB68B03A9F4F59163753B09756F24F51257C6FC6BA871`；日志和包位于 `artifacts/ci-run-45706468742/openhc-ipad-stage0-c5d49a04c5bdfec4aad6cd732d618a2ab99454ec/`，仅下载留存、未安装。较早 inbound-only CI 是历史基线 run `45702890162`，不作为本轮 host orchestration 验证。

## 下一步路径

本轮完成 host-side guard/lease lifecycle 接线、合成测试和标准 macOS CI，但未执行设备任务。Synthetic echo peer 只属可选工程测试；目前没有证据用户具备该 peer，也不是 HiCar 项目硬前置。下一次最短真实 Honor transport 目标可限定为一次 `--mode inbound` listener/accept/close：前提是获得距执行 60 秒内的有限 session metadata、确认恢复 guard/独立 SSH power owner 条件、由用户安装本次 DEB，并准备 Honor 20 Pro/HarmonyOS 4.0 上用户正常发起 HiCar 的窗口；当前均未执行，且缺少新鲜 session 快照时 gate 仍阻断。即使该 bounded accept 成功，也只证明 FE35 inbound transport，不代表 HiCar session 成功。随后唯一必要的协议代码范围是实现 OpenHC FE35 `SocketRequested` 控制事件、auth listener 完成后的 channel/UUID 回报及 auth channel 协商接口，再进入控制/认证解析；不得对真实手机发送 synthetic 数据。

真实 Honor 手机用户操作须另行安排；本轮不执行，也不发送 synthetic 测试数据。

## 真机验收卡

完整前置、命令、判定、恢复和用户手机步骤见 `docs/BTSTACK-OWNERSHIP.md` 中的“真机 transport 验收卡”。当前卡片是后续任务，不表示本轮已经执行或要求用户现在操作。热点最小验证方案同文列为独立后续任务。

## 历史证据索引

- 本地 ownership 外部快照、恢复闭环和命令记录：`artifacts/device-validation-20261126/`；详细来源与限制见 `docs/BTSTACK-OWNERSHIP.md`。
- 工具启动路径、SHA-256、SIGKILL 137 和 rootless 路径成功证据：`docs/ROLE-PROBE-DIAGNOSTIC.md`。启动位置差异已解决；终止原因仍未知，不追查 SIGKILL 内核原因。
- 更早 CI `45683689513` / `dddd437` 的 22 项测试、`45698383060` 与 `45702890162` 均为历史证据；本轮 host接线、C adapter 与 package 验收以 `45706468742` 为准。
- 更早的 PID、plist/job 状态、工具启动待验证结论均为历史快照，不可当作当前状态或重复执行指令。lockdown 无需修复。
