# OpenHC 技术路线与交接说明

更新时间：2026-11-27。本文记录当前实际选定的开发、构建、安装与验收路线，供新协调者和实现者接手。遇到与本文冲突的旧计划时，以最近的 `HANDOFF-CURRENT.md`、`docs/RESUME-CHECKPOINT.md` 和实际 CI SHA / artifact 证据为准。

## 1. 产品与平台路线

目标是把 OpenHC 的接收端流程移植到已越狱的 iPad mini 4 Wi-Fi（目标记录：iPad5,1、iPadOS 15.8.8、Dopamine rootless），由接收端前台 Start 建立真实 FE35 控制监听；RFCOMM 与 FE35 SDP 都实际注册成功后，才显示本会话 QR/PIN，Honor 手机上通过扫码发起连接。扫码本身不是认证成功或投屏成功。

安装和运行目标是越狱设备上的 Theos rootless `.deb`，由 rootless 包管理/受控 SSH 安装，文件位于 `/var/jb` 前缀。**不以 App Store、TestFlight、Apple Developer ID/开发者 provisioning profile 作为分发路线。**这不是普通非越狱 iOS 应用的部署方案。

“不走 Apple 官方签名分发”不等于“构建完全不签名”：当前 GitHub workflow 对 Theos target 指定 `TARGET_CODESIGN=ldid`、`TARGET_CODESIGN_FLAGS=-S`，为二进制生成 Theos/越狱场景所用签名数据；这不是 Apple Developer 证书、官方 provisioning profile 或 App Store 签名。目标设备上的安装/启动行为仍以真实设备验证为准。不要把这个签名参数改成 Apple 官方签名流程，除非用户明确改变分发路线。

工程当前阶段是扫码启动与 FE35 控制会话，不是“完整 HiCar 已完成”。已存在的 session model、FE35 C/ObjC/Kotlin bridge、UIKit 演示 App 和固定 PING helper 不能被描述为可连接手机的完整产品。认证/TrustStore、Wi-Fi/TCP、DMSDP 与媒体仍有后续实现。

## 2. 软件组件与责任边界

- **UIKit 前台 App**：Theos `application.mk` 构建，负责 Start/Stop、会话状态、显示同一会话 QR/PIN。transport 必须在后台执行；UI 不持有 root 权限、无线 owner、密钥或恢复责任。
- **Common Kotlin/Native session**：维护 session generation、双 ready、超时/Stop 时撤码和一次性 handoff 的状态。模型本身不访问设备，不替代平台 transport。
- **ObjC/C FE35 transport**：通过 BTdaemon socket 执行实际 RFCOMM/SDP 注册与接收。只有当代 session 的两项注册都确认，才能产生 PairingReady。typed completion 的 `returned` 与 `cleanup_confirmed` 相互独立；`CLEANED` 只表示 worker 到达返回前尾部，绝不能单独授权关电或恢复。
- **Owner / lease / recovery**：真实 backend 当前保持 disabled。接入前必须有明确且目标可验证的 app caller admission、单 owner、已有 lease/ownership preflight、独立 guard、唯一 heartbeat 与退出不确定时交给 guard 的恢复规则。UI、PING helper 或客户端自报字段不能取得这些权限。
- **固定 PING helper**：只验证 UI 到固定 rootless socket 的基本请求响应；不启动蓝牙、不读 identity、不代表 app 身份验证，不是生产 owner。

Showcase/BAA 目前未被本路线修改或替换，演示 PING helper 不使用蓝牙。未来真实无线试验时需避开 Showcase 正在使用蓝牙的会话，不能仅凭看到常驻 broker 进程就杀进程或宣称控制器独占。

## 3. 编译与验收路线（GitHub macOS CI）

开发工作区在 Windows `D:\OpenHC-iPad`；本机没有 Apple Xcode/iOS SDK 工具链。iOS framework、iOS Simulator、UIKit 和 arm64 Theos package 使用 GitHub Actions 托管的 `macos-15` runner 构建，不要求另买 runner 或 Apple 开发者签名账户。公开仓库的常规 hosted runner 是既定成本路线；不得为提速擅自切换付费大规格 runner。

当前 workflow：`.github/workflows/stage0-ios.yml`。工作树里的分层版本包括：

1. `host-validation` 在 `ubuntu-24.04` 批量跑 Python host suites 与 JVM tests。
2. macOS `build` 单次运行 Gradle，构建 iOS arm64 与 Simulator framework、运行 Native Simulator tests、检查生成的 ObjC API，并跑 FE35/scan Simulator 集成。
3. 同一 macOS job 安装 Theos、`ldid`、`dpkg`，构建 rootless `.deb`，运行包归档审计与 UIKit / helper 检查，上传可复核日志与 artifacts。
4. 聚合 required-check 保留失败传播；任何必需 host 或 Apple 检查失败，不能称整个 workflow 通过。

执行原则：先在 Windows 可跑的源检查、C 交叉编译和 host 单测中集中发现问题；把依赖 Apple SDK 的改动按完整纵切片合并，再 push 一次触发集中 macOS 验收。不要为文档或无关 host-only 修改反复重建 iOS framework；不得跳过或削弱失败断言。修复一个 Apple/Simulator 回归后，用同一失败检查覆盖新 SHA，不要把旧 SHA 的通过结果挪作新代码证据。复用 Gradle 缓存或独立已验收 artifact 时须记录精确 SHA/来源，并验证 artifact 的 `BUILD.txt`、摘要和包内二进制。

GitHub Actions macOS 排队是 runner 容量问题时，区分“job 尚未启动”和“实际代码步骤失败”；避免重复创建 run。账户额度/容量不通过更换付费 runner 解决，除非用户明确授权成本变更。

## 4. 打包、签名和安装

- Theos targets 明确使用 `ARCHS=arm64`、iOS deployment target 15.0、`THEOS_PACKAGE_SCHEME=rootless`。UIKit App 使用 `application.mk`，CLI/worker 使用 `tool.mk`。
- workflow 用 `ldid -S` 处理目标二进制签名，再由 Theos/`dpkg-deb` 生成 `.deb`。rootless 包须落在 `/var/jb`；归档检查要确认 xz、payload owner `0:0`、mode、精确路径、无意外链接和维护脚本。不要因为构建机 tar 默认 UID 不是 0 而放宽归档策略。
- CI artifact 必须记录 repository/commit SHA、run id、artifact id、ZIP digest、DEB SHA-256 与 executable SHA-256；安装器只接受其精确 pin。App-only 改动优先只更新 App，健康 helper 无改动时不重装/重启。
- 真机安装目标是已越狱 iPad 的 rootless 环境，不是 Apple Configurator、Xcode Devices 或 TestFlight。安装前先检查目标型号、OS/rootless、包 SHA、安装版本与当前 executable hash；设备登录密码仅使用既有交互式内存 stdin 入口，不传给 worker、不写进文档/命令行/环境变量。
- 工具链脚本 `scripts/install-scan-demo.py` 有固定包 pin 和目标 gate；诊断脚本只读并输出脱敏摘要。新协调者如需设备操作，先按最新 checkpoint 判断是否真的需要，避免为软件 build 验收重复上设备。

## 5. 当前证据与未完成状态

- 已审计的聚焦 Apple CI：run `45879557331`，SHA `72a11ae004e800d30db41550cdbb5d5ac0f5676f`；CPU QR App artifact/包已固定并安装。用户现场确认合成 QR 正常显示，约 60 秒后合成演示到期。这不证明持续稳定、真实 FE35 ready 或真实手机连接。
- 其后 FE35 typed completion 改动：task `task_3151f0cca27f` / dispatch `ctx_1ab93d17778c` 已交付，修改仍在共享工作树且未提交；本地严格 C/Werror 与 host fixture 检查通过，但 Apple/Simulator runtime 尚待验证。不要重复编写这段实现；把它纳入下一次相关 scan/FE35 聚焦 Apple 验收。
- 当前没有运行中的 worker。CI 45879557331 是代码验收基线，不是 typed-completion 新代码验收。
- 合成 PING/PONG、UI 显示二维码、READY 模型或 synthetic socket peer 都不能代表 Honor 手机已扫码、认证成功或媒体已启动。真实手机试验要等真正 owner/lease/backend 和 FE35 ready 链路可运行后再安排。
- 旧 FE35 CI 曾有真实失败及 Simulator 启动超时；保留具体失败类型，不用其他 step 通过掩盖整体失败。

## 6. 新协调者的操作要求

1. 协调者固定使用 Orca `new work` workspace；工作路径 `D:\orcafile`，交接在 `OPENHC-COORDINATOR-HANDOFF.md`。项目源码位于 `D:\OpenHC-iPad`。
2. 先只读检查真实最新 run、共享工作树与 checkpoint，再规划；保留共享目录所有既有改动，不执行 `git clean/reset`，不覆盖未提交工作。
3. 用户要求端到端整合、少等 CI。把 FE35 owner 生命周期、双 ready→QR、Stop/cleanup/guard 按依赖组成可验收纵切片，尽量一次交付并集中一次 macOS build。无明确 caller admission/恢复依据时维持 backend disabled，报告具体阻塞，不虚构技术能力。
4. Showcase 保持可用；先不要执行任何设备、无线、安装、identity 读取、启停服务或试验，除非用户另行安排有明确边界的现场窗口。
5. 身份材料、密钥、密码只可由原设计的受控本地 provider/交互入口使用。不要读取、复制、日志打印、上传或提交身份原文或凭据。

## 7. 工程内参考文件

- `HANDOFF-CURRENT.md`、`docs/RESUME-CHECKPOINT.md`：精确最新状态、CI 与包证据。
- `docs/PLAN.md`、`docs/SCAN-STARTUP-IMPLEMENTATION.md`：原始扫码流程、依赖顺序与历史实现。历史章节可能陈旧，读取前先看文首状态。
- `docs/SCAN-PRODUCTION-INTERFACE-MAP.md`：当前生产 caller、owner/lease、FE35 typed completion 缺口。
- `.github/workflows/stage0-ios.yml`：GitHub macOS/host 构建与 artifact pipeline。
- `theos/Makefile`、`theos/scan-ui/Makefile`、`theos/scan-supervisor/Makefile`：arm64/iOS15/rootless targets。
- `scripts/install-scan-demo.py`、`scripts/check-scan-demo-archive.py`：精确 pinned artifact 安装和 DEB 安全审计入口。
