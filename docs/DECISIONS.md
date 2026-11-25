# Decisions and Evidence

## 2026-11-25: Isolated validation harness

- The reference repositories at `8132399bea6aa86d68da6d3e1d9e3e001c0a7643` and `ce9d1d50758f67307deb3f00c901a8e82894930c` are clean and remain read-only.
- `D:\OpenHC-iPad` was absent before this work, so the validation project was created there.
- Reuse reference Kotlin 2.1.20 and Gradle 8.13 for the first compiler probe; this is a reproducibility choice, not proof that they are optimal or compatible until CI output confirms the iOS target.
- A local static bridge is the smallest useful experiment. Its hello API says nothing about protocol portability.
- Windows reports no registered WSL distribution. GitHub CLI is unauthenticated. SSH config contains only `aliyun-vps` and `singa-vps`; neither is an iPad alias and neither was contacted. No xcrun, Theos, clang or ldid command was found on Windows.
- Gradle 8.13 was downloaded and parsed the new project on Windows; it disabled both Apple targets and the JVM test task could not start because only a Java 8 JRE is installed. No Kotlin compilation, simulator, CI or device result is claimed.
- An isolated JDK 8 archive download into the OS temp directory stalled at roughly 69%; its curl process was stopped. The partial temp archive could not be removed because the terminal policy rejected the deletion command.
- Stage 0 is not passed until the physical iPad run.

## Open platform question

`MalformedMessageException` in the reference extends `java.io.IOException`. Native migration needs an explicit common exception type and call-site policy; do not silently replace it during unrelated compilation work.

## 2026-11-25: User-reported physical bridge pass; minimal WiFi parser probe

The user reported `KOTLIN_BRIDGE_OK` from the physical device after install/run instructions. Record this as user-reported evidence, with no agent SSH session, architecture output or on-device artifact hash claimed. Gate 1 is passed at that evidence level; this does not complete Stage 0.

Extract WifiMode/WifiConnectionInfo without parser edits. Exclude the adjacent WifiLinkMessages object and its JVM-only charset conversion. Preserve IOException ancestry on JVM via an explicit actual exception and use Exception on Native. Keep message/cause, wire fields, validation and existing acceptance of leading zeroes in numeric port text; do not alter protocol semantics to compile. Audit session IOException catches before migrating session code. All new probe credentials are synthetic and never emitted in probe output.
