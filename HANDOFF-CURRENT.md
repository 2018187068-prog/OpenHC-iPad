# OpenHC-iPad 阶段 0 当前交接

更新时间：2026-11-26

## 工程与远程

- 工程：`D:\OpenHC-iPad`
- GitHub：`2018187068-prog/OpenHC-iPad`，私有仓库
- 分支：`stage0-auth-validation`，变更持续推送到远程 `main`，未强推
- 最新代码提交：`dddd437`（本轮诊断与 transport 元数据读取层；后续交接文档提交以 git log 为准）
- 参考仓库只读：`D:\OpenHC-iPad-ref\OpenHC`、`D:\OpenHC-iPad-ref\showcase`

## 设备

- iPad mini 4 Wi-Fi：`iPad5,1`
- iPadOS 15.8.8，Dopamine rootless，Sileo
- Windows 已安装 USB 工具：`D:\OpenHC-iPad\tools\libimobiledevice\`
- `iproxy.exe` 已存在
- 历史：Windows 曾发现设备 UDID、USB SSH 曾可用；当时 lockdown 配对验证失败：`Invalid HostID (-21)` / `is not paired with this host`。当前通道不可用，以本轮状态为准。
- USB SSH 曾成功：
  - `USB_SSH_OK`
  - `iPad5,1`
- 2026-11-26 已通过现有 iproxy 上传、安装新 DEB 并完成 ownership 二进制检查。不要将 SSH 可用等同于 lockdown 配对已恢复。

## 已通过的真机证据

- `KOTLIN_BRIDGE_OK`
- `WIFI_CONNECTION_INFO_OK`
- `AUTH_VECTORS_OK`
- 平台库存：`iPad5,1`、iOS 15.8.8、MIS/MobileWiFi 符号存在、BTdaemon 文件存在
- BTstack 查询：版本 `1.1`、revision `3257`、state `0`、query OK
- BTstack 本地 FE35/FE36 服务两轮成功：
  - FE35 channel 16，handles `65537`、`65539`
  - FE36 channel 17，handles `65538`、`65540`
  - `BTSTACK_LOCAL_SERVICE_CYCLE_OK=1`
  - `BTSTACK_LOCAL_SERVICE_CYCLE_OK=2`
  - `BTSTACK_LOCAL_SERVICES_OK`

这些结果不代表无线 SDP、手机连接、双通道 I/O、链路认证或 HiCar 握手成功。

## 已完成真机构建（历史，不重测）

- CI：`45670248895`，成功
- 新增二进制选项：`--btstack-ownership`
- 该选项只读输出机器、系统、BTstack socket、BTdaemon 文件、plist，并结束于 `OWNERSHIP_SNAPSHOT_DONE`
- 不执行卸载、杀进程、上电、配对或 peer 连接
- 新 DEB 位于：
  `D:\OpenHC-iPad\artifacts\ci-run-45670248895\openhc-ipad-stage0-d1ef7cf62392fe1692677715f52be64031371057\deb\com.gcbond.openhc-bridge-check_0.3.2_iphoneos-arm64.deb`
- SHA-256：`7E1F3A99DCDBAD66134014981E86E0ECAC72B8ADD701D835FD23591D9E2A7892`
- 已上传到 iPad `/var/mobile/com.gcbond.openhc-bridge-check_0.3.2_iphoneos-arm64.deb`，远端 SHA-256 一致，`dpkg -i` 成功，安装版本 `0.3.2`。
- 已运行 `/var/jb/usr/bin/openhc-bridge-check --btstack-ownership`，退出码 `0`，完整日志：`D:\OpenHC-iPad\artifacts\device-validation-20261126\ownership-20261126-022442.log`。
- 输出：`OWNERSHIP_MACHINE=iPad5,1`；系统 `15.8.8 (Build 19H422)`；`BTSTACK_SOCKET=PRESENT`、`BTDAEMON_FILE=PRESENT`、`BTSTACK_PLIST=PRESENT`；`OWNERSHIP_SNAPSHOT_DONE`。
- 二进制明确输出 `OWNERSHIP_SERVICE_PRINT=UNAVAILABLE_IN_SANDBOX`、`OWNERSHIP_PROCESS_SNAPSHOT=UNAVAILABLE_IN_SANDBOX`。随后已取得下方 root shell 外部快照；快照采集完成不等于控制器所有权验证通过。

## 外部 ownership 审计（2026-11-26，已完成采集）

- 复用原 iproxy PID `39484` / `2222 → 22`，root UID `0`；未重做 query、FE35/FE36 本地注册、向量、安装或配对验证。
- `ch.ringwald.BTstack`：running，PID `35779`，`/var/jb/usr/bin/BTdaemon`；launchd 已注册 `/tmp/BTstack` 监听器。
- `com.apple.bluetoothd`：running，PID `30370`；`com.apple.BlueTool`：已注册，当前 not running，最后为 idle jetsam 退出。不能把 BlueTool 没有进程等同于已卸载。
- `com.apple.BTServer.le` / `BTLEServer`：running，PID `485`。AVRCP、MAP、PBAP 子服务已注册但 not running。`com.apple.BTServer` 总标签不存在（113），不能据此说 Apple 蓝牙服务不存在。
- Showcase 主进程 PID `27255` 存在，进程快照未见 `CarDisplaySim`。这不足以确认其 UI 状态或排除后续自动竞争。
- `com.reng.showcase.bluetooth-recovery` 未注册（113）；其 ready 文件不存在；recovery.plist 存在；`/tmp/showcase_bt_owned` 不存在；`/tmp/showcase_bt_ready` 却存在，必须视为残留/未验证标记，不能据此上电。
- `dpkg-query` 确认 BTdaemon 归属 `com.rostane.showcase`，版本 `1.0~beta5-3`；未证明安装二进制与参考源码提交一致。
- 原始日志：`artifacts/device-validation-20261126/root-ownership-snapshot-20261126-022903.log`、`root-ownership-detail-20261126-023012.log`。
- 结论：**Apple 蓝牙与 BTdaemon 同时存在，尚未建立 BTstack 独占控制器的证据；没有可依赖的已就绪恢复守护。ownership 不能记为 PASS。** 本轮未卸载、杀进程、上电、连接手机或读取认证材料。
- 完整源码依据、接管/恢复顺序和后续试验安排：`docs/BTSTACK-OWNERSHIP.md`。参考 Showcase 提交仍为 `ce9d1d50758f67307deb3f00c901a8e82894930c`。

## 当前阻塞

最新复查：**本轮用户已明确确认管理员重启 Apple Mobile Device Service 成功**。随后仅做一次主机通道检查：`idevice_id -l` 退出 0、设备数仍为 0；复用 2222 转发，SSH banner 字节数 0。未重做 `idevicepair validate`，没有设备 shell，不能判断新配对是否成功；不要再次要求重置信任或重复服务重启。目前没有证据支持另一个管理员命令。

0. **当前 USB SSH 已中断（2026-11-26 最新状态）**：历史 PnP 可见 Apple iPad 和 Apple USB 设备且状态 OK，但 usbmux 列表为空。原 iproxy PID `39484` 曾监听 2222。本轮用户已成功执行唯一要求的管理员服务重启命令；其后设备数仍为 0、SSH banner 仍为空。该操作没有恢复通道，不再把“等待管理员重启”记为待办；不杀 iproxy、不卸载 USB 驱动、不重复重置信任或读取配对记录。下文 SSH 可用的描述为历史状态。
   共享 helper 工具 CI `45680397016` 产物已下载至 `artifacts/ci-run-45680397016/helper-role-5b4ee733d4a1a320ac41c4186bbe7958e3031e7b/`，已上传 `/var/root/Library/OpenHCStage0Tools/showcase-role-probe`，远端 SHA-256 与本地相同：`f5e6565974e35cec2480ceba1d3b24d704c044230debbdea46f31a065f5f10b7`。启动被系统 `Killed: 9`，退出 137；一次仅注册该工具 CDHash 后仍为 137，尚未得到 owner PID，不能放行 ownership。日志：`broker-endpoint-owner-20261126.log`、`broker-tool-launch-diagnostic.log`、`broker-endpoint-owner-trusted-20261126.log`、`usbmux-device-list-status.log`（位于本日 device-validation 目录）。终止原因未证实；恢复 SSH 后优先检查该工具的兼容性/执行环境元数据，不重跑上电。

1. **共享 helper 角色未最终核实，不是已证实的活动会话**：用户明确表示并未启动 Showcase。最新只读快照仅见 `CarPlay Simulator` PID `27078`，启动时间为设备报告的 `2026-11-25 10:43:00`；此前 Showcase 主进程 PID `27255` 已不在，未见 `CarDisplaySim`/`carplay_bt`。`/tmp/showcase_baa.sock` 存在，`/tmp/showcase_bt_owned` 不存在。源码 `Showcase.m:3500–3516,3613` 与 `carplay_services.m:6369–6372` 表明相同可执行文件还以 `--baa-broker` 模式长期驻留，退出 app 后可保留；进程名称不能证明蓝牙竞争。先前要求用户 Stop 是过早推断，现已撤回；无需为此打开 Showcase，也不要 kill。设备没有已发现的 lsof/Python 等工具，`launchctl procinfo` 返回 45，因此尚未取得该 PID 与 broker socket 的归属对应。不得读取认证日志、证书/密钥、进程参数或请求 broker 认证数据来确认。
2. 独立恢复守护和有界 power-only 驱动已经实现并执行一次真机闭环（见下方）。首轮驱动遗漏无路径 comm 已修正；当前驱动对共享 executable 报 `SHARED_HELPER_ROLE_UNVERIFIED`，不再仅凭名称报活动竞争。下一步用不读取认证数据的进程/socket 归属元数据确认 broker 与活动服务角色，或增加只输出角色与 PID 的只读平台工具，再决定放行；不能简单以 socket 存在作为白名单。当前 0.3.2 没有无线 peer 测试选项，仍需独立 live transport probe；不得用 `--btstack-services` 冒充无线验证。Honor 手机准备状态尚未确认。
3. lockdown 配对未获恢复证据，且当前 USB SSH 不可用，已阻塞设备只读诊断。用户已完成解锁、拔插及信任；不要重复请求。历史 ACL/文件替换推断未证实，本轮不修复、不读取配对记录或扩大权限。

## 本轮本地修复与 CI（2026-11-26）

完整说明：`docs/ROLE-PROBE-DIAGNOSTIC.md`。本轮没有设备执行，没有上电、卸载、kill、读取真实认证数据，也没有重复旧真机测试。

**已验证**：

- 原 CI `45680397016` 工具为 baseline arm64、iOS minimum 15.0、SDK 18.5，只依赖 libSystem；无 entitlements/RPATH。新增离线审计器校验所有 SHA-1/SHA-256 代码页与签名特殊槽哈希，原产物通过。有效静态签名不等于设备 AMFI 接受。
- 已成功运行的 0.3.2 同样含 chained fixups，不能仅凭该特征解释 SIGKILL；历史 CDHash 注册后仍 137 也不能证明内存不足或信任已生效。
- 探针新增立即 flush 的 `ROLE_PROBE_MAIN_ENTERED` 与固定 `--self-check`；后者不连接 socket、无需 root，可先定位启动阶段。正常 owner 查询仍固定 endpoint、无应用字节读写、不接受 endpoint 参数。
- CI `45683159550` / `46d6daa` 成功：6 项签名合成测试、7 项 macOS 合成 endpoint/启动测试；产物已下载 `artifacts/ci-run-45683159550/`。分别构建 baseline 与 legacy-fixups 两个二进制，独立哈希和完整 load command/签名/依赖审计。legacy 只是兼容性候选，不能称为已修复真机 SIGKILL。
- 新增 `scripts/btstack-transport-metadata.py`，本地 9 项合成测试通过；没有 live 入口或连接/上电/发送功能。拒绝 RFCOMM payload 时只读外层 header；拒绝安全事件时不读取参数。支持实际 channel/CID 元数据，测试包含 close/reopen 不同 CID，但这不是设备生命周期验证。
- 只读参考源码发现 CID 偏移 12/13 不一致，及 CHANNEL_OPENED 声明长度 18、实际回调 17 的不一致；新 reader 在后者处 fail closed。见诊断文档精确源码位置。参考仓库未修改。

**仍未验证**：SIGKILL 的 termination namespace/code；新版工具真机启动、owner PID、helper 活动角色、安装 BTdaemon 是否包含参考源码的事件问题、完整 live transport runner、无线 SDP/双通道 I/O、独占 ownership、HiCar 握手。不得把离线 PASS 当成上述任一设备 PASS。

**最终组合 CI 已验证**：`45683689513` / `dddd437` 成功，6 + 7 + 9 = 22 项合成测试通过。产物已下载至 `artifacts/ci-run-45683689513/`；本地再次审计下载的两个二进制并核对 SHA-256，均通过，哈希与前轮一致。日志：`artifacts/device-validation-20261126/continuation-local-audit.log`。这些均为本地/CI 证据，没有上传设备。

**可独立推进**：transport 合成状态机、SDP/方向协商、恢复守护集成与 tool-specific termination 元数据过滤器；这些不依赖 USB。禁止借开发 runner 执行真机上电。

凭据未写入脚本、日志或仓库，不要从历史消息复制到交接材料。

## 有界上电与恢复闭环（2026-11-26，已执行一次）

共享 helper 元数据工具已完成 CI 构建：`scripts/showcase-role-probe.c`，独立手动 workflow `stage0-helper-role.yml`；最新模拟/产物证据见上节。正常模式固定连接 `/tmp/showcase_baa.sock`，只用 `LOCAL_PEERPID` 获取 PID 后关闭，不发送或读取应用字节；不请求认证操作。模拟测试检查真实合成 socket 的 PID、零应用字节、缺失/残留/非 socket/符号链接拒绝及 release 不能改 endpoint。CI 产物独立保存，不替换 DEB；新版尚未上传设备。

- 新脚本：`scripts/btstack-power-trial.py`、`scripts/btstack-power-recovery.sh`；模拟测试：`scripts/test-btstack-power.py`。主机仅经 SSH 转发固定 `/tmp/BTstack`，不依赖额外 CI 构建或安装。
- 初次真机试验前 12 项模拟测试通过；名称解析修复后的最终 13 项全部通过（含无路径 BTdaemon 阻止恢复、无路径带空格 helper 识别），日志：`artifacts/device-validation-20261126/power-mock-tests.log`。修复后未再次执行上电。
- 独立 launchd label：`io.github.gcbond.openhc.stage0-power-recovery`；ready 已观测，120 秒绝对期限、20 秒心跳过期；恢复动作只由守护执行。先模拟平台命令验证，再进行真机试验。
- 单次真机：Apple bluetoothd、BlueTool unload 后确认 job/process 退出；BTstack 重载后，状态依次 `0 → 1 → 2 → 3 → 0`，得到 `BTSTACK_POWER_WORKING`、`BTSTACK_POWER_OFF_OBSERVED`。未发送 discoverability、SDP 注册、配对或 peer 命令。
- 恢复：BTstack unload 后，BlueTool load、bluetoothd load，再恢复原 BTstack job，全部返回 0。主机再次确认 Apple jobs、BTServer.le、bluetoothd 进程、BTstack job/socket 与 OFF 状态，之后解除守护并清理 active 锁。
- 只读后验：BlueTool PID `37365`、bluetoothd PID `37358`、BTLEServer PID `485`、BTdaemon PID `37392`；恢复 job exit `113`（已卸载），`ACTIVE_LOCK_CLEARED`、`RESTORED`。
- 证据：`artifacts/device-validation-20261126/power-trial-20261126-024343.log`、`post-power-helper-audit.log`；远端 per-run 目录 `/var/root/Library/OpenHCStage0Power/20261126-024344-112d8808` 保留审计文件。
- **限制**：共享 helper PID 27078 在前后快照均存在，其角色未最终核实，不能仅凭名称认定活动会话或竞争。保留上电/OFF 和已恢复的直接观测，但本轮的“无竞争会话”前提不足，不能作为完整 ownership PASS 或手机无线测试 PASS。尚未做真机 SSH 失联恢复测试；该失败路径仅模拟通过。
- 用户澄清后的只读记录：`showcase-process-role-audit.log`、`showcase-process-role-audit-2.log`、`showcase-process-role-audit-3.log`（均在上述 artifacts 目录）。首次 launchctl list 的 shell 变量 `status` 与 zsh 只读变量冲突，改名后重查；未匹配到 PID 27078/27255 的 launchd job 标签，不据此认定无父进程或无活动。

## 通道恢复后的只读顺序

```powershell
# 仅在出现新的通道恢复证据后，检查设备数量和现有转发 banner。
# 复用原 iproxy；不重做配对验证，不盲目启动或杀转发进程。
# banner 恢复后按 docs/ROLE-PROBE-DIAGNOSTIC.md 先运行无 socket 自检。
```

安装、二进制检查、外部快照和首轮有界上电/恢复均已完成，无需重复。不要再要求用户停止其未启动的 Showcase；先核实共享 helper 的 broker/会话角色，避免误杀驻留 broker。再补齐 live transport probe 及已知手机准备状态，按 `docs/BTSTACK-OWNERSHIP.md` 安排后续受控验证。手机通道需按 SDP/协商结果决定，不能固定使用历史本地 16/17，也不能将普通设置配对当成 HiCar 握手。

已执行的二进制命令：

```sh
/var/jb/usr/bin/openhc-bridge-check --btstack-ownership
```

## 约束

- 不读取、打印或提交 `openhc-identity.json`、密码、密钥或真实认证字节
- 只用合成数据
- 不盲目执行 Apple Bluetooth 卸载/kill/上电
- 不启用付费 runner 或额度
- 阶段 0 未完成前不展开全量迁移
