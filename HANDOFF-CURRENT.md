# OpenHC-iPad 阶段 0 当前交接

更新时间：2026-11-26

## 工程与远程

- 工程：`D:\OpenHC-iPad`
- GitHub：`2018187068-prog/OpenHC-iPad`，私有仓库
- 分支：`stage0-auth-validation`，变更持续推送到远程 `main`，未强推
- 最新提交：`c77577e`
- 参考仓库只读：`D:\OpenHC-iPad-ref\OpenHC`、`D:\OpenHC-iPad-ref\showcase`

## 设备

- iPad mini 4 Wi-Fi：`iPad5,1`
- iPadOS 15.8.8，Dopamine rootless，Sileo
- Windows 已安装 USB 工具：`D:\OpenHC-iPad\tools\libimobiledevice\`
- `iproxy.exe` 已存在
- Windows 已发现设备 UDID，但当前 lockdown 配对失败：`Invalid HostID (-21)`
- USB SSH 曾成功：
  - `USB_SSH_OK`
  - `iPad5,1`
- 当前需要恢复“信任此电脑”会话，然后重新运行 `idevicepair validate`。

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

## 最新构建

- CI：`45670248895`，成功
- 新增二进制选项：`--btstack-ownership`
- 该选项只读输出机器、系统、BTstack socket、BTdaemon 文件、plist，并结束于 `OWNERSHIP_SNAPSHOT_DONE`
- 不执行卸载、杀进程、上电、配对或 peer 连接
- 新 DEB 位于：
  `D:\OpenHC-iPad\artifacts\ci-run-45670248895\openhc-ipad-stage0-d1ef7cf62392fe1692677715f52be64031371057\deb\com.gcbond.openhc-bridge-check_0.3.2_iphoneos-arm64.deb`
- SHA-256：`7E1F3A99DCDBAD66134014981E86E0ECAC72B8ADD701D835FD23591D9E2A7892`

## 当前阻塞

Windows 能看到 Apple USB 设备，但 `idevicepair validate` 返回 `Invalid HostID (-21)`，`iproxy` 因此无法稳定转发 SSH。请用户在 iPad 解锁后拔插 USB；若没有信任弹窗，可执行“设置 → 通用 → 传输或还原 iPad → 还原 → 还原位置与隐私”，再点“信任此电脑”。不要抹掉所有内容和设置。

## 恢复后命令

```powershell
$b='D:\OpenHC-iPad\tools\libimobiledevice'
& "$b\idevicepair.exe" validate
Get-Process iproxy -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Process 'D:\OpenHC-iPad\tools\libimobiledevice\iproxy.exe' -ArgumentList '2222','22' -WindowStyle Hidden
ssh -p 2222 root@127.0.0.1
```

恢复 SSH 后上传 DEB，安装后运行：

```sh
/var/jb/usr/bin/openhc-bridge-check --btstack-ownership
```

## 约束

- 不读取、打印或提交 `openhc-identity.json`、密码、密钥或真实认证字节
- 只用合成数据
- 不盲目执行 Apple Bluetooth 卸载/kill/上电
- 不启用付费 runner 或额度
- 阶段 0 未完成前不展开全量迁移
