# FE35 Bridge Checkpoint

Updated 2026-11-26. Repo: `D:\OpenHC-iPad`, branch `stage0-auth-validation`.

## Last Verified Baseline

- Tested HEAD/SHA: `e810378c5f3d9e34ebd09a9a7c85f545d79cf2b1`.
- macOS workflow `45751891681`: success. Static iOS arm64 framework/header check passed; JVM 35/35 and iOS Simulator 33/33 passed, including the full synthetic Nearby frame/session fixture on both targets.
- Theos rootless package step passed. `fe35-bridge-smoke.m` compiled and linked into the arm64 tool; it exercises the exported `OHCBFe35ControlBridge` API when invoked with `--fe35-bridge-smoke`. This is compile/link evidence, not a device run.
- The workflow takes about 3m54s and keeps framework, shared tests, synthetic transport/guard checks, and package validation on every relevant push.
- The ObjC smoke initializes arrays with exported `OHCBKotlinByteArray arrayWithSize:` as declared by generated `OpenHCBridge.h`.

## Candidate Work Pending CI

`theos/btstack-probe.c::transport_inbound` now feeds bounded RFCOMM bytes to the public bridge via `theos/fe35-control-bridge.m`, dispatches frame/listener events, registers the requested UUID, returns the actual channel through `listenerReady`, and cleans up services/CID. The CLI receives a bounded binary bridge config on stdin; Trial accepts it from an inherited caller FD and sends it through the bounded WORKING window. The socket test uses a bridge test double to exercise the C path; it does not claim to execute K/N inside the C mock. Production Objective-C wrapper invokes the public `OHCBFe35ControlBridge` methods and is compiled/linked by the Theos package workflow.

Locally verified: Python syntax, diff checks, and guarded Trial tests 25/25. Pending: macOS C socket mock execution/assertion count, ObjC framework compile/link, JVM/Native tests, and rootless package. Run one workflow after the complete change; record its final SHA/run ID. Do not send synthetic frames to a device. Auth handshake, DMSDP, and media remain out of scope.
