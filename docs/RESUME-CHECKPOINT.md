# FE35 Bridge Checkpoint

Updated 2026-11-26. Repo: `D:\OpenHC-iPad`, branch `stage0-auth-validation`.

## Verified Revision

- Tested SHA: `bc589e1812e93d937a9d3fed9e82a5b1b61a5ea3`.
- macOS workflow `45757974503`: success. JVM 35/35; iOS Simulator 33/33; iOS arm64 framework/header and Theos rootless arm64 DEB passed.
- C synthetic transport socket mock compiled and executed 5 inbound cases with 158 wire assertions, including normal close, bridge exception, accept timeout, and daemon cleanup. It links a bridge test double, not Kotlin/Native.
- The same CLI dispatcher (`theos/main.m`) ran `--fe35-bridge-smoke` in iOS Simulator against the actual Kotlin/Native framework and reported `FE35_PUBLIC_KOTLIN_BRIDGE_CLI_SMOKE_OK`. The Theos production adapter also calls the exported `OHCBFe35ControlBridge` API; generated Objective-C header signatures were checked and package compilation/linking passed.

## Scope And Remaining Work

`--btstack-control-inbound` accepts bounded bridge configuration from stdin, feeds bounded RFCOMM frames to the public bridge adapter, dispatches `SEND_FRAME`, `OPEN_AUTH_LISTENER`, and `CLOSE_AUTH_LISTENER`, registers the event UUID, returns the assigned channel through `listenerReady`, and cleans up its service/CID. The socket mock verifies this C path with a test double; a real-BTstack-free socket run combining that C path with the production Objective-C/Kotlin implementation remains unverified. Do not describe it as a single end-to-end C/K/N socket execution.

No device, radio, pairing, identity file, or real authentication data was used. Authentication handshake, DMSDP, and media remain unimplemented. Do not send synthetic protocol frames to a device. Existing physical evidence is historical and must not be repeated.
