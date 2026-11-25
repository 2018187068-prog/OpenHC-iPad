# OpenHC-iPad 当前交接

更新时间：2026-11-26

## 当前状态

- 工程 `D:\OpenHC-iPad`，分支 `stage0-auth-validation`；当前提交和最新 CI 在本节下方记录。只读参考工程 `D:\OpenHC-iPad-ref` 未修改。
- 目标设备为 iPad mini 4 Wi-Fi (`iPad5,1`)，iPadOS 15.8.8，Dopamine rootless。既有 USB SSH 可用记录不等同于 lockdown 配对恢复。
- 已有物理证据：Kotlin bridge、Wi-Fi parser、认证向量、平台 inventory、BTstack 版本/状态查询、FE35/FE36 本地服务注册/清理两轮，以及 2026-11-26 一次 BTstack power on/off 与 Apple/BTstack 服务恢复闭环。不得重复这些检查。
- 未通过：有限会话 gate 的当前真机观测、无线 SDP、双通道 RFCOMM I/O、installed BTdaemon 事件格式兼容、exclusive controller ownership、no-forced-link-auth 运行时证据和 HiCar 握手。上次 power 闭环中无竞争前提不充分，因此不记 ownership PASS。
- 实现入口：`scripts/btstack-session-gate.py` 是有限、点时证据分类器；`theos/btstack-probe.c` 包含 synthetic-only outbound adapter 和无应用数据的 FE35 inbound listener/SDP/accept/close adapter，后者由 `--btstack-control-inbound` 暴露。它不解析 OpenHC 控制协议，不应对真实手机宣称 HiCar 可用。`PowerProtocol.run(on_working=...)` 有 callback 生命周期和异常释放测试，但 `Trial.run()` 尚未接入 C transport，当前没有安全的设备调用入口。`scripts/btstack-transport-runner.py` 仍是显式计划驱动的离线双通道核心。
- 当前会话结论：broker endpoint owner PID 曾与 comm-only `CarPlay Simulator` PID 27078 匹配，且 broker 源码分支在网络会话初始化前进入 broker loop，属已证实 broker 证据；这不代表没有并发活动会话。另有已知活动 helper 的正向观测才分类为活动会话；信息缺失、未解释 shared helper、残留 marker 或恢复活动均为 UNKNOWN。marker、进程名和进程不存在单独不构成放行条件。`CLEAR_SNAPSHOT` 仅表示这组限定指标在该次快照未见，不声称绝对无并发或没有未来竞争。
- 本轮限制：仅本地代码、合成测试及文档；未连接设备、未上电/卸载/配对/改热点/kill、未读取身份或认证材料、未作新签名信任操作，也未启用收费 runner。
- 本轮代码提交 `314fe7e1f23e81186620b06e3e7ca1965dc929b6` 的 GitHub-hosted `macos-15` workflow run `45702890162` success（2026-11-25 21:20 UTC）。CI 用 clang 实际编译 C test executable 并运行 outbound socket cases 10/10、close/reopen 2 次、FE35 inbound cases 5/5（success、accept failure、incoming timeout、disconnect timeout、daemon-client-close cleanup）；后续 iOS framework、shared JVM/Native tests 与 Theos arm64 package 均通过。0.3.4 DEB SHA-256 `924C42F46C919109199B4BC0022923C00E02C191F03D7B203D1A2C3D7845FD02`，逐案日志与包位于 `artifacts/ci-run-45702890162/openhc-ipad-stage0-314fe7e1f23e81186620b06e3e7ca1965dc929b6/`；包仅下载保留，未安装。此结果是实际 C socket mock 与构建证据，不是无线/HiCar 运行证据。

## 下一步路径

当前没有完成 guard/lease 生命周期集成的可执行设备流程，不安排本轮真机操作。Synthetic echo peer 只属可选工程测试；目前没有证据用户具备该 peer，也不是 HiCar 项目硬前置。FE35 transport API 已完成离线实现后，最短真实 Honor 推进路径仍是验证本轮 C listener/accept/cleanup mock CI，再将其接入 power driver 的唯一 WORKING callback，最后按 OpenHC `NearbySession` 完成受限 control state machine 与 auth channel 协商。设备阶段仍需有限 session metadata 快照、独立恢复 guard/唯一 lease owner、包含新代码的构建，以及用户提供 Honor 20 Pro/HarmonyOS 4.0/HiCar 正常连接窗口；不得对真实手机发送 synthetic 数据。

真实 Honor 手机用户操作只在 FE35 协议路径和 driver lease 集成完成后另行安排；本轮不执行，也不发送 synthetic 测试数据。

## 真机验收卡

完整前置、命令、判定、恢复和用户手机步骤见 `docs/BTSTACK-OWNERSHIP.md` 中的“真机 transport 验收卡”。当前卡片是后续任务，不表示本轮已经执行或要求用户现在操作。热点最小验证方案同文列为独立后续任务。

## 历史证据索引

- 本地 ownership 外部快照、恢复闭环和命令记录：`artifacts/device-validation-20261126/`；详细来源与限制见 `docs/BTSTACK-OWNERSHIP.md`。
- 工具启动路径、SHA-256、SIGKILL 137 和 rootless 路径成功证据：`docs/ROLE-PROBE-DIAGNOSTIC.md`。启动位置差异已解决；终止原因仍未知，不追查 SIGKILL 内核原因。
- 更早 CI `45683689513` / `dddd437` 的 22 项测试是历史证据；本轮 C/adapter 与 package 验收以 `45698383060` 和本节结果为准。
- 更早的 PID、plist/job 状态、工具启动待验证结论均为历史快照，不可当作当前状态或重复执行指令。lockdown 无需修复。
