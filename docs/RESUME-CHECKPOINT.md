# FE35 Bridge Checkpoint

Updated 2026-11-26. Repo: `D:\OpenHC-iPad`, branch `stage0-auth-validation`.

## Verified Revision

- Tested SHA: `fe29b49a0a020a14e1dc087d3e5894ce084f88b1`.
- macOS workflow `45765343940`: success. JVM 35/35 and iOS Simulator 33/33; iOS arm64 framework/header and Theos rootless arm64 DEB passed.
- The same iOS Simulator process executed `main.m --btstack-control-inbound`, `btstack-probe.c::transport_inbound`, production Objective-C adapter, and Kotlin/Native against a synthetic BTdaemon peer. Three cases passed with 190 assertions: success 86, listener-registration failure/cleanup 72, incoming timeout 32; assertions cover fragmented/coalesced frames, listener UUID/channel callbacks, encrypted command-4 bytes, cleanup ordering, and bounded completion.
- The simulator-only peer uses host loopback TCP because host and Simulator have separate Unix-socket `/tmp` namespaces; production Theos transport remains Unix socket. No bridge double is used in this fixture.

## Scope And Remaining Work

Offline FE35 control negotiation through the real C/Objective-C/Kotlin-Native bridge is verified end-to-end with synthetic bytes. This does not implement or verify authentication, HiCar/DMSDP, or media. Device acceptance still requires separately scheduled real-Honor-phone testing after current ownership/transport prerequisites are met; do not repeat historical probes or send synthetic frames to a device.

No device, radio, pairing, real identity file, or real authentication data was used in this CI run.

## Local FE35 Config Provider

- Source/test SHA: `8e7ccf357155460c2237a7e50de9c42726937322`; macOS CI `45769151355` succeeded. Provider tests 3/3, Trial/guard 25/25, simulator end-to-end fixture 190 assertions, JVM/Native tests and framework/Theos build passed.
- `scripts/btstack-power-trial.py --mode inbound` accepts an explicit identity file or existing `OPENHC_IDENTITY_DIR/openhc-identity.json`, and a bounded Bluetooth-address FD. Provider reuses upstream `IdentityAssets` schema; device ID is derived with upstream `DeviceId`; existing `nearbyKeys` are passed through without claiming protocol-fixed constants. Encoded bytes travel only via anonymous pipe/inherited FD and existing bounded remote stdin; no values enter argv/env/logs. CI tests are synthetic only.
- Address provider implementation is in progress in the current worktree: Trial will query local BD_ADDR via HCI Read BD_ADDR only inside its existing WORKING callback, then feed the raw result through the existing bounded address FD/provider path. This is source-only and synthetic-tested so far; C compile/socket and macOS CI still pending. Theos CLI adds `--btstack-local-address RUN_DIR`, emitting exactly six binary bytes on stdout and no address text. Do not run on-device until CI is green and a user window is scheduled.
