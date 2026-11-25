# OpenHC iPad Stage 0

Validation harness for an iPad mini 4 (A8, iPadOS 15.8.8, Dopamine rootless) Kotlin/Native and Theos bridge experiment.

The Kotlin/Native + Objective-C/C design is a hypothesis under test. Passing the bridge self-check does not establish protocol portability. See [the plan](docs/PLAN.md), [tasks](TASKS.md), and [validation report](docs/REPORT.md).

The macOS workflow builds an `iosArm64` static framework, runs shared JVM/Native simulator tests, builds a rootless Theos package, and uploads inspectable artifacts. Physical-device validation remains a separate gate.
