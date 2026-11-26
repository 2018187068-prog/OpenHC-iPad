# FE35 Bridge Checkpoint

Updated 2026-11-26. Repo: `D:\OpenHC-iPad`, branch `stage0-auth-validation`.

## Verified Revision

- Current tested SHA: `b4c66242c775af7470504fb365cba3a02d8d9fc6`.
- macOS workflow `45775185368`: success. New C Unix-socket fixture covered local-address success, HCI command failure, and timeout (3/3); existing Trial suite 26/26, provider 3/3, simulator bridge fixture, JVM/Native tests, iOS framework/header build, and Theos rootless arm64 package passed.
- The actual inbound CLI now obtains the controller BD_ADDR with HCI `Read BD_ADDR` inside the existing WORKING callback, validates the bounded HCI completion, reverses HCI wire byte order, passes six bytes internally through an anonymous pipe to the existing identity provider, then runs the existing inbound command. Address output is binary-only between the remote CLI and Trial process; no address or identity values enter argv, environment, or logs.
- Tested SHA: `fe29b49a0a020a14e1dc087d3e5894ce084f88b1`.
- macOS workflow `45765343940`: success. JVM 35/35 and iOS Simulator 33/33; iOS arm64 framework/header and Theos rootless arm64 DEB passed.
- The same iOS Simulator process executed `main.m --btstack-control-inbound`, `btstack-probe.c::transport_inbound`, production Objective-C adapter, and Kotlin/Native against a synthetic BTdaemon peer. Three cases passed with 190 assertions: success 86, listener-registration failure/cleanup 72, incoming timeout 32; assertions cover fragmented/coalesced frames, listener UUID/channel callbacks, encrypted command-4 bytes, cleanup ordering, and bounded completion.
- The simulator-only peer uses host loopback TCP because host and Simulator have separate Unix-socket `/tmp` namespaces; production Theos transport remains Unix socket. No bridge double is used in this fixture.

## Scope And Remaining Work

Offline FE35 control negotiation through the real C/Objective-C/Kotlin-Native bridge is verified end-to-end with synthetic bytes. This does not implement or verify authentication, HiCar/DMSDP, or media. Device acceptance still requires separately scheduled real-Honor-phone testing after current ownership/transport prerequisites are met; do not repeat historical probes or send synthetic frames to a device.

No device, radio, pairing, real identity file, or real authentication data was used in this CI run.

## Local FE35 Config Provider

- Provider source/test SHA `8e7ccf357155460c2237a7e50de9c42726937322` and current automatic-address path are validated by `45775185368`. Provider reuses the upstream `IdentityAssets` schema and `DeviceId` algorithm; existing `nearbyKeys` are consumed without treating them as protocol constants. Synthetic C fixtures verify HCI `Read BD_ADDR` opcode, wire byte order, status rejection, and bounded timeout. No address or identity values are logged. No device operation was performed.
- Exact local command after a user schedules the real-device window: `python scripts/btstack-power-trial.py --execute --mode inbound --identity-file <existing openhc-identity.json path>`; alternatively set the existing `OPENHC_IDENTITY_DIR` and omit `--identity-file`. A missing/unavailable identity file fails as `IDENTITY_CONFIG_UNAVAILABLE` before SSH/device work. Trial still requires its existing fresh session evidence where applicable, ownership preflight, and ready independent guard; don't reuse historical evidence as current.
