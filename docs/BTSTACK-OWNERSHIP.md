# BTstack ownership, session gate, and transport validation

更新时间：2026-11-26。适用设备 iPad5,1 / iPadOS 15.8.8 / Dopamine rootless。下列设备记录是有时间戳的历史证据，不是当前设备状态；当前交接见 `HANDOFF-CURRENT.md`。

## 证据状态

### 已完成的历史真机工作

- BTstack 查询返回版本 1.1、revision 3257、state 0；FE35/FE36 本地注册、SDP record 创建、清理和重注册两轮成功。历史本地 RFCOMM channel 16/17 不是无线协商结果。
- 2026-11-26 root 快照曾见 BTdaemon、Apple `bluetoothd`、`BTLEServer` 同时存在；BlueTool job 已注册但当时 idle。日志在 `artifacts/device-validation-20261126/root-ownership-snapshot-20261126-022903.log` 和 `root-ownership-detail-20261126-023012.log`。
- 后续一次有界 power-only 真机闭环观测到 BTstack `OFF → INITIALIZING → WORKING → HALTING → OFF`，恢复守护按 BlueTool、bluetoothd、基线 BTstack 顺序恢复并经独立快照验收。日志 `power-trial-20261126-024343.log`、`post-power-helper-audit.log`。SSH loss/deadline 恢复路径只有合成测试证据。
- 该次 preflight 漏过共享 helper，故 power 状态和恢复状态观测有效，但它不是“无竞争”或 exclusive ownership PASS；不得重复 power cycle。
- 已完成的 owner 查询一次得到 socket peer PID 27078，零 broker 应用字节读写；comm-only 快照将其识别为 `CarPlay Simulator`。参考源码 `Showcase.m` 表明共享 executable 可运行常驻 BAA broker，broker 分支在网络 session 初始化前进入 loop。PID/socket/source 三项支持分类为 broker。不能据此排除另一个同时存在的活动 session，也不能推断安装二进制必与参考源码一致。没有读取 argv、broker payload、认证日志或密钥材料。
- 主机工具相同字节在 `/var/root` 启动 SIGKILL/137，在 `/var/jb/usr/bin` 自检成功；终止 namespace/code 未知。路径差异已有验证，不追查 SIGKILL 内核原因。详情见 `ROLE-PROBE-DIAGNOSTIC.md`。

### 当前有限会话判据

实现：`scripts/btstack-session-gate.py`。只有 socket owner PID 是当前 comm 中已识别 broker 且 shared-helper 集合恰好只有该 PID 时才可 `BROKER`；额外 shared helper 一律为 `UNKNOWN`。每次只依据一组有界 metadata 快照，分类如下：

| 分类 | 必要观测 | 处理 |
| --- | --- | --- |
| `BROKER` | 固定 broker socket 的本次 peer PID 与同一快照 comm 匹配，限定源码/平台 metadata 支持 broker 角色；shared-helper 集合恰为该 owner；无已观测正向活动 PID、无恢复 job、marker absent | 只确认这个 endpoint owner 的 broker 角色，不代表已证明独占会话或没有并发；不能单独当作 controller ownership 放行 |
| `ACTIVE_SESSION` | 与已识别 PID 绑定的正向 session-state metadata 表明已知 helper（如 `CarDisplaySim`、`carplay_bt`）处于活动会话 | 阻断；不停止、不 kill |
| `CLEAR_SNAPSHOT` | 固定检查集完整、已知 helper 的活动状态 metadata 未报活动、shared helper 均未出现、无恢复 job、marker 明确 absent、无未解释 broker owner | 只表示该时点的限定检查集未见竞争；进程名不单独证明活动或空闲，不声称绝对不存在并发或消除后续竞态 |
| `UNKNOWN` | 快照不全、shared helper 角色未明、socket owner 与 comm 不匹配、恢复 job 活跃、marker 残留/无法读取或 owner/marker 元数据缺失 | 阻断；只补造成 UNKNOWN 的最小 metadata，不追加泛化探针 |

Marker 只能作为一项辅助状态，不能单独证明活动/空闲；进程名或 Showcase 主进程存在不能单独判活动；进程缺席不能证明绝对无并发。正向活动状态优先于 broker 分类。判据不要求证明“绝对不存在并发”。真实 C/ObjC/Kotlin-Native inbound session 已在固定 CI 合成 socket peer 中贯通；本地 identity-to-FD provider 已实现，真机仍无新鲜 metadata 快照，也没有本机 Bluetooth address 的受控 FD 来源。owner/comm 的旧快照不得复用；未来执行若 collector 当前快照为 `UNKNOWN` 即停止。不复测工具启动、不执行无关上电探针。

## 离线实现与明确阻塞

FE35 控制协商仍由 `bridge/src/commonMain/.../Fe35ControlNegotiator.kt` 负责；新 `Fe35NearbyControlSession` 将其接到真实 Nearby frame stream、handshake、解密与输出帧。固定来源为 OpenHC revision `8132399bea6aa86d68da6d3e1d9e3e001c0a7643`。最小依赖闭包取自上游 `core/common/ByteReader.kt`、`ByteWriter.kt`、`codec/Ea.kt`、`codec/Crc16Arc.kt`、`codec/ReceiveBuffer.kt` 和 `core/nearby/Ea.kt`、`Tlv.kt`、`NearbyFrame.kt`、`NearbyFrameDecoder.kt`、`ChannelManagement.kt`、`SocketMessages.kt`；握手顺序/行为对照 `NearbySession.handleChannelManagement/feed/handleSocketLayer`，listener 与 callback 对照 `WirelessReceiverSession.onSocketRequest/onAuthListening` 及 `NearbySession.acceptRfcommSocket`。该上游 common-compatible 源码在本工程仅把 `System.arraycopy`/JVM 格式化转换为 common Kotlin，并用已有 HMAC 与显式 AES-CFB JVM/OpenSSL Native boundary 承接 cipher；没有接入真实 identity/key 文件。帧格式是 `7f | EA outer | TLV flag | EA payload length | payload | CRC16/ARC LE`；decoder 保持上游丢弃整个坏缓冲行为，session 限制输入块 64 KiB、总暂存 64 KiB+512、握手 deadline 5 秒。每加密帧使用独立明文 seed；协议没有额外帧序号。

未验证工作树中有统一 common Kotlin 入口 `Fe35NearbyControlSession.start/feed/onAuthListenerReady/close`，测试源贯穿固定合成 `PHONE_FIRST` 握手帧和 command-3 RFCOMM request，产生 listener UUID，并在模拟 channel 回调后构造完整加密 command-4 frame。测试还覆盖分片/粘帧、CRC 错误、握手前请求与 negotiator 的重复 UUID/protocol bit/reconnect UUID 规则。此处仅能确认源码存在：当前 Windows 无 JDK 编译器，JVM 测试未运行；Native 测试、framework 编译、ObjC 导出均未验证，源码中也未找到 `OHCBFe35NearbyControlSession` 或对外 session wrapper。

这还不是端到端传输：当前 `--btstack-control-inbound` 仍只做 socket accept/close，不读取 RFCOMM 数据，也没有 C 调用 Kotlin/Native framework 的代码。唯一下一项实现依赖是先添加并在 macOS CI 验证 public ObjC session wrapper，再由 C adapter 将有界 read bytes 与 Open/Send/Close/listener-ready 动作接入该 wrapper，同时保留 Trial WORKING lease 和恢复顺序。此后才可用合成 C socket peer 验收实际 adapter 路径；真实手机模式绝不发送 synthetic 数据，HiCar auth 握手、DMSDP、媒体仍未实现。

`scripts/btstack-transport-runner.py` 现在只消费显式 session plan，不解析 SDP 也不从 SDP 虚构 direction：`WirelessReceiverSession.start()` 是 FE35 本机 listen；`startReconnect()` 才是 FE35 本机 connect。正常 `SocketRequested` 事件触发本机开 auth listener，监听完成后再将本地 channel/UUID 回报；`AuthChannelReady` 是 reconnect flow 的 peer channel/UUID，才触发本机 auth connect。证据来自只读参考 `WirelessReceiverSession.kt` 的 `start/startReconnect`、`onSocketRequest/onAuthListening/onAuthChannelReady` 及 `NearbySession.acceptRfcommSocket`。同一个数字只有在两条本机 listener 同时占用时才冲突；peer connect 的 channel 与本机 listener channel 不在同一 namespace。

新增 iOS C CLI `--btstack-control-synthetic` 连接固定 `/tmp/BTstack`，只在现有 BTstack state 已为 WORKING 且调用方 run-dir 存在 READY/未过期 deadline 时，按显式 peer 地址与 RFCOMM channel 建立 FE35 类控制连接。该命令只交换固定 `OPENHC-SYNTHETIC-CONTROL-v1` 测试字节，不发 power command，不执行 SDP、配对或 HiCar 握手；它只能用于另一个受控 synthetic peer，不能对 Honor/真实手机运行。它在首次受控连接内按指定 profile 或 `auto` 识别 `strict-17` / `reference-17-len16`；未知 shape/事件立即拒绝应用字节，若 CID 可解析则尝试 disconnect，否则关闭 client socket 触发 daemon 按 client ownership 清理。传输命令只读取 guard marker/deadline，不写 heartbeat；恢复守护的 heartbeat 由 power driver 独占更新。主机侧须由 power driver 确认对应 recovery launchd job 已注册；run-dir marker 本身不证明 job 活着。该 CLI 已由 GitHub-hosted macOS run `45698383060` 编译并进入 `0.3.3` arm64 DEB，但未安装。

兼容证据分两类：静态可离线确认的是 socket packet header、RFCOMM create/disconnect opcode、event 字段 offsets、`rfcomm.c` 成功 callback 的 17-byte 实际长度/16 声明，以及 daemon 读取 byte 13 routing 的源码事实；只读参考文件分别是 `platform/daemon/src/socket_connection.c`、`platform/daemon/src/daemon.c`、`src/classic/rfcomm.c` 与 `src/btstack_event.h`。reference daemon 在 `DAEMON_EVENT_RFCOMM_CREDITS` 中调用 `daemon_retry_parked()` 并消费内部 credits event，不把该事件转给 socket client；adapter 因而发送标准 `RFCOMM_DATA_PACKET`，不自行发放 credits，合成对端 echo 和 deadline 是该单次发送的应用层确认。若 installed daemon 将未识别事件路由到 client，adapter 立即拒绝并关闭连接。installed BTdaemon 是否同源、opened event 是否真的送达本 client、运行时采用 strict 还是 reference 格式，只能在首个受控连接读取 bounded metadata 时得知，不是 adapter 实现前置条件。新 CLI 的 `auto` 在首次受控连接内检测 `strict-17` 或 `reference-17-len16`；未知 shape、异常状态或超时均不发应用字节，若成功 CID 可解析则尝试有界 disconnect，否则关闭 client 清理。若 daemon 不路由该事件，现有静态源码不能证明装机行为；当前最小观测就是这次可选 synthetic 连接的 profile/timeout 结果，不要求独立 metadata-only 探针。

## 真机 FE35 控制协商验收卡（准备中，待另行安排窗口）

### 当前构建与设备状态

- 当前 checkout `f61843e47648ea625737f53f025fc8ff7eacfbbc`；本功能验收 revision `fe29b49a0a020a14e1dc087d3e5894ce084f88b1`，macOS CI `45765343940` 成功。产物为 `com.gcbond.openhc-bridge-check` 0.3.5 arm64 DEB，CI artifact 已核对 SHA-256 `5A33A0B5B91CD3133930346BC2F912A51B9A6C5F367800406B37305878FA3004`。设备最近一次有记录的安装是 2026-11-26 的 0.3.2；0.3.5 是否已安装未知，安排窗口前需只读核对包版本/hash，不可把 CI 出包当成安装证据。
- 当前真机前置证据缺失：新的 `snapshot_complete=true` ownership/session 快照（最多 60 秒）、独立恢复 guard 当前 ready 状态、目标 iPad 当前安装版本/二进制与本次 0.3.5 对应、Honor 手机现有正常配对/HiCar 可启动状态。旧 PID、旧快照和历史 WORKING/OFF 闭环不可复用；collector 没有正向 active-session-state 来源，空列表不构成无活动证明。
- 本地 provider 复用固定上游 identity schema：`host.modelId/subModelId` 是本机型号标识输入，`nearbyKeys.rootKey/constA/constB` 是本机现有 nearby 加密材料；上游未将它们定义为协议固定常量，本实现不要求用户另行填写。device ID 按上游 `DeviceId` 从型号字段与无线使用的本机 Bluetooth address 计算；address 不在 identity JSON。provider 接受显式 identity 文件或 `OPENHC_IDENTITY_DIR/openhc-identity.json`，地址仅从继承 FD 读取，生成原有版本化 bridge bytes 并经匿名 pipe 交给当前进程，Trial 再按现有 bounded stdin 传到固定远端入口。内容不放 argv/env/log，输入只在进程内短暂存在并尽力清零。
- 唯一仍需外部提供的软件输入是本机无线 Bluetooth address 的 bounded FD 来源；当前仓库未实现从目标环境 Bluetooth property 读取并安全转成此 FD 的 provider，不能用 synthetic address 运行真机。另需每次窗口新鲜 ownership snapshot、guard ready 和安装 revision/hash 只读核对；这些是现场状态门槛，不是缺少 identity schema。

### 允许的最小验收范围

范围仅为真实 FE35 控制协商：目标手机正常发起其现有 HiCar 连接后，观察 inbound listener/transport 是否收到合法控制帧、bridge 是否发出 `OPEN_AUTH_LISTENER` 并完成 listener-ready channel/UUID 回调，以及是否收到真实对端后续控制帧。不得记录/输出 device ID、UUID 原值、帧 payload、密钥或认证 transcript；只记录非敏感阶段标签、事件类别、长度、channel、超时/退出状态与恢复结果。这里不验证认证握手、HiCar/DMSDP 完整连接或媒体。

未满足上述前置时可执行的唯一现场动作是经用户另行安排后的只读 capture：

```powershell
python scripts\capture-btstack-session-evidence.py --capture --output artifacts\session-evidence.json
```

只有 capture 完整、分类明确、距运行不超过 60 秒，当前 shared-helper PID 集一致，recovery guard ready，安装包与待测 revision 核对一致，且授权操作者已通过安全渠道准备真实 FE35 bridge config FD，才可由协调者单独批准以下 bounded trial。下面的 FD 必须由专用秘密注入器创建并继承；不能改用文件明文、命令行参数、日志或 synthetic fixture；当前 repo 没有该注入器，所以此命令现阶段不可直接执行：

```powershell
python scripts\btstack-power-trial.py --execute --mode inbound --bridge-config-fd <inherited-fd> --session-evidence artifacts\session-evidence.json
```

成功需要同时出现 `BTSTACK_POWER_WORKING`、`BTSTACK_FE35_BRIDGE_SESSION_OK`、`TRANSPORT_RESULT=PASSED`、`BTSTACK_POWER_OFF_OBSERVED`、`RESTORATION_RESULT=VERIFIED`；所有事件/阶段都不得包含 payload 或身份字段。`TRANSPORT_RESULT=FAILED` 时，只有远端退出已确认才允许 Trial 按既定唯一顺序发 OFF 并恢复；若 SSH loss、deadline 或 exit status 未确认，必须看到 `EXIT_UNCONFIRMED` 与 `DELEGATED_TO_GUARD`，不手工并行恢复、不重试。恢复 guard 从 arm 起的 deadline 是 240 秒，inbound 子命令上限 45 秒；超时后等待 guard 对原 run-dir 的结果并独立只读核验恢复，不启动第二个恢复者。手机侧仅由用户正常打开目标 HiCar 连接，不重新配对、不改热点。

### A. 可选的受控 synthetic peer 工程回环

- 这是可选的 adapter 工程验证，不是 HiCar 项目完成或真实手机验收的前置条件；目前没有证据表明用户具备相应 synthetic Bluetooth peer。
- 本地 AF_UNIX mock 只验证 socket framing 和 C 进程的状态/清理行为，不能代替 over-air peer，也不能证明 HiCar 协议正确。
- 不要把真实 Honor 手机用于 synthetic echo。不得为执行此可选测试而先改变设备 Bluetooth/power 状态。

### 精确命令与成功标志

本地合成验收命令（可在设备任务前执行）：

```powershell
python scripts\test-btstack-session-gate.py
python scripts\test-btstack-transport-runner.py
python scripts\test-btstack-transport-metadata.py
python scripts\test-btstack-power.py
python scripts\test-btstack-transport-socket.py
```

已新增 C `--btstack-control-inbound RUN_DIR` API：在本地 RFCOMM channel 16..23 中按 busy 状态选择 listener，注册 FE35 SDP record，白名单解析 `RFCOMM_EVENT_INCOMING_CONNECTION (0x82)` 的 channel/CID（读取并丢弃地址），发 `RFCOMM_ACCEPT_CONNECTION (OCF 0x44)`，校验 incoming `CHANNEL_OPENED` 后有界 disconnect。该 API 完全不读取 RFCOMM data packet，不执行 OpenHC 控制握手，不发送应用数据；accept/open/timeout/disconnect 异常时尝试移除本次拥有的 SDP/service，再关闭 daemon client 作为 pending CID 的清理兜底。它只证明 listener/accept/close 的 transport 层，不证明真实 HiCar 端到端可用。

`scripts/btstack-power-trial.py` 的 host CLI 现在接受 `--execute --mode inbound`，并在 `Trial.run()` 的 WORKING callback 中通过独立 Paramiko SSH session 调用固定 `/var/jb/usr/bin/openhc-bridge-check --btstack-control-inbound <run-dir>`。路径和参数由代码常量及 Trial 生成的 run-dir 提供，不接受任意远端命令；timeout 包装为固定 45 秒并合并 stdout/stderr，最多保留 64 KiB。只有收到远端 exit status 才确认子命令退出，之后 PowerProtocol 才发送 OFF；远端非零退出也属于已确认退出，随后照常 OFF 并由同一 Trial 请求 guard restore。timeout、SSH loss、取消或输出超限等导致退出状态未知时，跳过 OFF 与 host restore-request，停止 heartbeat，让独立 guard 在 heartbeat age 超过 20 秒时恢复；输出 `TRANSPORT_RESULT=EXIT_UNCONFIRMED` 与 `RESTORATION_RESULT=DELEGATED_TO_GUARD`，不声称恢复已完成。常规路径下 Trial 是唯一 heartbeat writer 和 restore-request 发起者；PowerProtocol 是唯一 power lease client。Guard deadline 从 arm 开始计 240 秒，覆盖 takeover、最多约 45 秒 transport、15 秒 OFF 等待和最多 65 秒 host restore 观察时间，留有执行余量；不确定路径不等待 transport 来决定恢复 actor。

当前 metadata 由可执行只读 collector 生成，不手工编 JSON、不使用历史 PID。执行环境须是用户自行准备好的 USB SSH tunnel，且先安装包含 `--session-owner` 的 0.3.5+ 工具包；本轮没有安装或运行该命令。collector 以一次 SSH command 顺序采集 start/end epoch、一次 `ps -axo pid,ppid,state,comm`、recovery job status、marker 和安装版本的 `--session-owner` 结果，要求窗口不超过 5 秒；peer PID 查询是固定本机 Unix socket 的 `LOCAL_PEERPID`、有界 connect/getsockopt、零应用字节读写，并在前后核对 socket inode。命令无 `--capture` 时只打印 `NO_DEVICE_ACTION`：

```powershell
python scripts\capture-btstack-session-evidence.py --capture --output artifacts\session-evidence.json
```

`--capture` 仅读取 metadata 并输出 JSON；采集异常、owner 不在同一进程快照、输出字段缺失或时间跨度过大都会得到 `snapshot_complete=false`，不能用于放行。该 collector 不存在可读的正向 HiCar active-session-state 来源，`active_session_pids: []` 仅代表本次没有取到正向 PID 绑定事件，不能解释成无活动。额外 shared helper、恢复活动、残留 marker 或任何不完整输入继续为 UNKNOWN 并阻断。新鲜 capture 也不能证明不存在未观测的并发或后续竞态。

结果 JSON 的字段形状如下；这个例子只描述 schema，不能复制作为真实证据：

```json
{
  "captured_at_epoch": 0,
  "snapshot_complete": true,
  "shared_helper_pids": [],
  "broker_owner_pid": null,
  "broker_comm_pid": null,
  "active_session_pids": [],
  "recovery_active": false,
  "ownership_marker": null
}
```

结果距 guarded trial 不超过 60 秒；`shared_helper_pids` 必须与 Trial 再次采集的当前 helper PID 集完全相等。`broker_owner_pid` 只取 collector 本次 `LOCAL_PEERPID`，`broker_comm_pid` 只在相同快照进程名属于已源码确认的 broker 进程时赋值。`active_session_pids` 只有正向 session-state 来源才可填入，本轮 collector 不会猜测填充。只有符合现行有限 classifier 的明确证据才可能分类为 BROKER；活动、额外 helper、UNKNOWN、过期/不完整/与当前 PID 集不匹配均阻断。当前没有新鲜现场 snapshot，执行仍阻断；不可自动使用历史 PID。

下一次由用户另行安排设备窗口、独立恢复条件就绪后，先 capture，再从同一时段手动确认 Trial 仍被授权；这是操作说明，不是本轮执行要求。collector 会提示输入 SSH 密码且不会将其写入文件：

```powershell
python scripts\capture-btstack-session-evidence.py --capture --output artifacts\session-evidence.json
python scripts\btstack-power-trial.py --execute --mode inbound --session-evidence artifacts\session-evidence.json
```

不带 `--execute` 时 CLI 输出 `NO_DEVICE_ACTION` 并以状态码 2 退出；`--execute` 配合 `--mode power-only` 保留旧 power-only 行为。此命令不安装 package、不配对、不改热点、不发送应用数据。成功标志分别为 `TRANSPORT_RESULT=PASSED`、`BTSTACK_POWER_OFF_OBSERVED`、`RESTORATION_RESULT=VERIFIED`；可确认的 inbound accept/close 失败表现为 `TRANSPORT_RESULT=FAILED`，但仍应观察 OFF 和 guard restoration；SSH loss/timeout 表现为 `EXIT_UNCONFIRMED` / `DELEGATED_TO_GUARD`，这不是成功恢复证据，之后必须通过独立只读检查观察 guard `result`。Guard deadline 为从 arm 开始的绝对 240 秒，预算包含 takeover、最长 45 秒 C 命令、最多 15 秒 OFF wait、最多 65 秒 restore observation 与执行余量。本轮未运行该设备命令。

### B. 真实 HiCar 协议/metadata 模式

离线合成路径已通过 C/ObjC/Kotlin-Native 集成验收（见 checkpoint）；这不是安装机兼容或真实 Honor 连接证据。真实手机绝不运行 synthetic echo adapter，也不发送任意 synthetic auth/control 数据；其控制事件只允许提取事件类别、长度、channel 和状态，不记录地址、raw payload、UUID 原值或认证 transcript。

### 失败判据与恢复

任一未知 gate、opened event 格式异常、连接 timeout、帧解析失败、close 未确认、guard heartbeat 丢失或 SSH 断开，均为 `TRANSPORT_FAIL`，不可自动重试。若远端退出已确认，由 Trial 按既有 lease 顺序发 OFF 并请求同一 guard 恢复；若退出状态未知，Trial 不发 OFF 或第二个恢复请求，停止 heartbeat 并将恢复权交给已 arm 的独立 guard。随后只读观察该 run directory 的 `result` 与 `recovery.log`，并检查 guard：

```sh
/var/jb/usr/bin/launchctl print system/io.github.gcbond.openhc.stage0-power-recovery
```

只有 guard 报 `RESTORED`，且独立确认 Apple BlueTool/bluetoothd/BTServer.le、bluetoothd 进程、基线 BTstack registration/socket、BTstack OFF 状态后才结束；任何恢复不明/失败都停止后续无线试验，按既有 USB recovery 流程处理。绝不添加 kill 命令或并行手工 unload/load。记录 transport 结果与 restoration 结果为两个独立状态。

## 后续任务：热点能力最小验证方案（本轮不执行）

1. 先只做本地/API 可用性审计，确认目标硬件/系统暴露的 hotspot 控制 API 与所需权限；不存在可支持的接口即记录不可用，不绕过系统安全边界。
2. 用户另行明确窗口与手机后，在独立恢复方案下由用户手动开启热点；设备侧只读采集 hotspot enabled、接口/IP、频段/信道等非凭据元数据，并做一次受限客户端连通性检查。
3. 不读取/输出 SSID 密码文件、密钥、认证 payload；如 SSID 本身被定义为敏感则只记录长度/是否存在。验证后由用户关闭热点，确认设备服务恢复。与 HiCar RFCOMM/握手验收分开报告。
