# 扫码启动纵切片：实现边界审计

日期：2026-11-26。仅源码/构建定义审计；未运行测试、CI、设备命令或读取真实 identity。上游固定 commit：8132399bea6aa86d68da6d3e1d9e3e001c0a7643。

## 工程结论与事件顺序

可做出“前台 Start/Stop、真实 FE35 listening-ready 后显示本次 QR/PIN”的有限接收端切片；当前 Foundation CLI 尚不是这个入口，不能安排手机扫码或启动 Trial 等来机。第一版应是受主机 supervisor 管理的有界开发会话；独立脱离主机的 root supervisor 启动/授权属于尚待落地的平台边界，不能假定 Theos app 自带 root。

固定上游 core/session/src/main/kotlin/io/github/gcbond/openhc/core/session/WirelessReceiverSession.kt:105–106、169–177、225–235：创建会话 PIN → start 发出 FE35 ListenRfcomm → 该 control listener 的实际 onListening 成功 → PairingReady(QR,PIN)。WORKING 不是 listening-ready，后续 auth listener 的 ready 也不是初始 PairingReady。app/src/main/kotlin/io/github/gcbond/openhc/wireless/WirelessController.kt:237–240、516–561、935–975、1045–1056 将用户 Start、session/runner/platform executor 和 PairingReady 接到 UI；ui/WirelessScreen.kt:64–108 只在等待扫码状态显示。

扫码前：监听及 FE35 SDP 已成功注册，显示本次有效码和六位 PIN；不先开热点。扫码后：手机用码中的本机经典地址查 SDP、连接 FE35，接收端处理 Nearby/control 握手及业务19请求，再开放 FE36 auth 子通道；只有真实认证成功才进入热点/Wi-Fi/TCP。依据 core/session/README.md:102–111、133–158 及 WirelessReceiverSession 的事件处理。扫码不是接收端主动连接手机；startReconnect 是另一条路径。WirelessController.kt:584–588 对非 AUTO 返回空 beaconPlan，故手动扫码不要求先实现 BLE/GATT。

QR 规则来自 core/nearby/src/main/kotlin/io/github/gcbond/openhc/core/nearby/PairingQrCode.kt:36–63，配置同源关系来自 core/session/.../WirelessReceiverConfig.kt:53–65、90–91：名称/型号、真实本机经典地址、本次 PIN 和实际支持能力；字段顺序 devicename/mac/moduleid/submoduleid/pin/ability，沿用原有名称清洗规则，不自行 URL 编码或猜字段。USB 能力不能照搬 Android 的 true。core/auth/.../HiCarAuthSession.kt:306–312 的 PinCodes 用均匀随机数并补足六位前导零；Native 应复用已有安全熵边界，以拒绝采样等方式保持均匀，不能直接取模引入偏差。PIN 必须保留给后续 auth，不能显示后另生成。

## 必需部件及可复用边界

| 必需部件 | 现状与最小改动 |
| --- | --- |
| 会话模型与扫码数据 | 迁移 PairingQrCode 纯逻辑及 PIN 生命周期，新增 Idle/Starting/ListeningReady/Connected/Stopping/Stopped/Failed 状态和 session generation；过期事件不能重新显示旧码。真实值仅内存及受控前台显示。 |
| 真监听事件与停止接口 | theos/btstack-probe.c:622–679 的 transport_inbound 已注册 RFCOMM/FE35 SDP，但没有注册成功即向 UI 发 ready 的接口；当前阻塞25秒来机等待和30秒控制期限不能放 UI 主线程。提取可取消的有界事件循环，注册/SDP 任一步失败不发 ready，关闭先撤 UI 码再清理 CID/listener。 |
| 前台应用 | theos/Makefile 是 TOOL_NAME + Foundation + tool.mk，main.m 是 stdin CLI；无 UIKit app、QR renderer、Start/Stop 页面。新增独立 application 目标，不把 CLI 改名当 app。 |
| supervisor 与 UI 通信 | 当前 Trial 只有 host 驱动及最终输出，没有 app Start/Stop 和实时 ready/event 通道；须新增有界 IPC 与单会话关联/断连失效。app 不读 root identity/key，不自行启动第二个电源客户端。 |

可复用 b4c66242 / CI45775185368 已验收的 C socket/SDP/清理、ObjC fe35-control-bridge.m、common Fe35ControlBridge 及 iOS 静态 OpenHCBridge framework；复用 WORKING 内本机地址查询和既有 provider。bridge/src/commonMain/.../Fe35ControlBridge.kt:31–53 只有 deviceId/nearby 材料与 start/feed/listenerReady/tick/close，没有 QR/PIN/完整 session。它的 listenerReady 是控制协商所请求的 auth listener 回调，不能直接替代初始 FE35 PairingReady。无需为生成 PIN 整体搬入依赖 SecureRandom/TimeZone 的 JVM WirelessReceiverConfig。

## 前台、rootless 与 lease

bridge/build.gradle.kts 已有 iosArm64/iosSimulatorArm64 静态 framework；.github/workflows/stage0-ios.yml 证明现有 Apple 工具链可构建 framework 和 Foundation CLI/DEB，尚未构建 .app。Theos 官方 templates commit 6c3944e281c4726f1383755d0fbb642840312d28（2025-02-16）的 iphone_application_modern 模板包含 APPLICATION_NAME、UIKit/CoreGraphics、application.mk、UIApplicationMain、UIWindow/rootVC 及 iPad UIDeviceFamily；因此 UIKit + Theos rootless application 在构建结构上可行，应保留本项目 arm64/iOS15 配置，而非复制模板旧 target。官方 rootless 文档仅证明 /var/jb、库搜索和打包方案，不授予 app root 权限，也不证明当前设备签名、启动或 IPC 路径可用。

Apple Core Image 的 CIQRCodeGenerator 接受 NSData、纠错 M，iOS7起可用。它是可选原生 renderer；上游 ui/QrCode.kt:22–58 用 UTF-8/纠错M/白边2，Apple文档字符串示例建议 Latin-1，不能未经验证认为中文等价。实现应以 UTF-8 原始数据为准，补白边、整数放大并禁插值，解码合成含中文 QR 核对内容；若系统 encoder 不能保真，换显式支持 UTF-8 的 encoder，不能改变协议文本。

页面常驻与无线会话常驻必须分开。第一版复用 host Trial 的有界 power lease、独立 launchd guard 和唯一 heartbeat owner，把 Start/Stop/ready 通过新增 IPC 连接前台；不是把阻塞 CLI 塞进 app。UI 只请求开始/停止，supervisor 串行持 lease、检查 guard job、处理事件；guard 是唯一恢复 actor。现有240秒绝对 guard deadline不得因 UI 前台而无限续租；后台/断连/Stop/到期撤销码并结束会话。远端退出确认才 OFF 并请求恢复；退出不明停止 heartbeat，交独立 guard，禁止第二次 OFF/restore。真实身份/nearby key留 root-side；UI 仅收到 QR/PIN和无敏感状态，数据不得进 stdout、argv、env、报告或持久日志。

脱离主机的最终 app 需要另外实现受限 root supervisor 的启动、调用者授权、IPC权限与崩溃恢复；目前无此构建/安装证据。第一版 IPC 也必须先以无电源 mock 证明 app 与 supervisor 的协议，明确 root/mobile 权限路径，不能默认 rootless sandbox 可跨越。此为具体平台实现工作，不要求新增设备探针来替代。

## 最短实施计划（按依赖顺序；本轮未执行）

1. **Native 扫码会话核心。** 增加 QR builder、均匀 PIN provider 和上述状态模型，复用 identity/address 的内存配置接口；只在初始 FE35 ready 后发布同一 generation 的 QR，Stop/失败/到期撤销，预留同 PIN 的 auth handoff。验收：新增合成测试后运行现有 ./gradlew :bridge:jvmTest :bridge:iosSimulatorArm64Test，覆盖前导零/地址拒绝/名称清洗/实际ability/乱序ready/旧generation/Stop。mock仅替换熵、地址与时钟，不替换被测 QR 规则，不用真实文件。
2. **C transport 提供实时 ready/stop。** 从既有 transport_inbound 提取事件和取消边界，保留协议桥、deadline与清理；不要在本任务迁移认证状态机。验收：扩展现有 python scripts/test-btstack-transport-socket.py，合成 daemon 分别让 RFCOMM或SDP失败、成功、取消及断连，断言注册全部成功才一次 ready、stop撤销/清理一次、晚到ready无效。mock在 BTdaemon socket 边界，使用已合成配置；不跑蓝牙、不重做190断言作为本次新增验收。
3. **UIKit rootless app 与真实 QR renderer。** 新增 application.mk目标、前台 Start/Stop/状态/二维码与PIN页面及 fake session provider；UI主线程不跑transport。验收入口作为任务交付：新增 scripts/check-scan-ui.sh，在既有macOS工具链构建设备rootless .app DEB及Simulator app，Simulator注入合成provider，检查Start前无码、ready后可见、Stop/后台/过期撤码，并由系统decoder核对合成中文QR/前导零/白边。该脚本和app目标当前尚不存在；不能把现有CLI CI视为通过。mock替换会话，不替换UIKit或QR编码/解码；不安装设备。
4. **有界 supervisor ↔ 前台接线。** 在既有host Trial生命周期内新增 app Start/Stop 和实时session事件协议，锁定单owner及可审计root/mobile IPC权限/启动方案，禁止UI持heartbeat或直接接触key；真实backend保持显式禁用，等待协调者审查。交付新增 scripts/test-scan-supervisor.py 的可运行mock验收：完整Start→guard-ready→WORKING→listener-ready→UI QR→Stop→清理/恢复序列；覆盖重复Start、后台、event断连、超时和退出不明仅guard恢复，验证无二次OFF和不续绝对deadline。mock替换SSH/launchd/power/transport，使用真实supervisor状态机；不联系设备。若root/mobile启动/IPC权限仍未落地，任务报告具体未解决接口，不能宣布真实扫码可用。

四项完成仅可宣称“扫码入口与有界 FE35 控制切片具备软件实现及mock证据”。FE36 auth数据 listener、业务19后真实认证/TrustStore、热点/Wi-Fi/TCP、DMSDP/media仍在切片之外；遇到这些下一阶段应报告未实现并受控停止，不能伪造认证成功。真实手机验收需协调者另行安排，不由本计划自动启动。

官方依据（2026-11-26只读核对）：https://github.com/theos/templates/tree/6c3944e281c4726f1383755d0fbb642840312d28 ；https://theos.dev/docs/rootless ；https://developer.apple.com/library/archive/documentation/GraphicsImaging/Reference/CoreImageFilterReference/index.html （CIQRCodeGenerator）。以上是平台可行性资料，不是本项目已运行证据。
