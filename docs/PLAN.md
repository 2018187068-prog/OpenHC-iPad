# OpenHC-iPad Stage 0 Plan

Target: iPad mini 4 Wi-Fi (A8, 2 GB), iPadOS 15.8.8, Dopamine rootless, Sileo DEB. Development is Windows + WSL2/Theos; no local Mac is available.

The Kotlin/Native protocol library plus Objective-C/C platform layer is a hypothesis under test, not a selected architecture. JVM/JAR execution on iPad is out of scope. Kotlin 2.1.20 and Gradle 8.13 mirror the read-only reference project's pins. The initial bridge deliberately contains no protocol behavior.

Stage 0 gate 1: build an `iosArm64` static framework, expose an Objective-C callable self-check, link it into a Theos rootless command-line package, inspect arm64/minimum OS/link dependencies and signing, then run on the physical iPad and observe `KOTLIN_BRIDGE_OK`. A macOS CI build is a prerequisite because this workstation has no Apple toolchain. CI or simulator evidence does not count as physical-device evidence.

Gate 2: copy the fixed-revision `WifiChannels.kt` into common Kotlin and test JVM/Native behavior for channel/frequency mappings, boundaries and exceptions. Evaluate the minimal `WifiConnectionInfo` dependency closure separately. Do not change protocol behavior to make compilation pass. `MalformedMessageException` extends `java.io.IOException`; record an explicit Native replacement point before migrating callers.

Later gates cover authentication vectors (SPEKE3072, X25519, Ed25519, AES-GCM, HKDF), BTstack FE35/FE36 channels/SDP/actual channel numbers/authentication requirements/I/O/close, and hotspot IP/SSID/BSSID/frequency. Showcase MISManager and bridge100 are references only; bridge MAC is not assumed to equal BSSID. The password is local-only. Ordinary RFCOMM connection is not evidence of a real HiCar handshake.

Identity files and keys are excluded. All tests use synthetic values; logs must not contain passwords or keys. Reference repositories remain read-only.
