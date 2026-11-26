# CPU QR App: focused validation review (2026-11-27)

This is a proposed next run, not executed validation. No push, rerun, device
connection or installation was performed for this review.

## Completed run and artifact audit

Run `45875853812`, source `6d1731813d95e8e60f7628a7a06f95848668c6f2`,
completed **failure**. Apple framework/Native tests succeeded. Synthetic FE35
passed with `FE35_KN_INBOUND_ASSERTIONS=190`, `SCAN_NATIVE_SOCKET_TESTS_OK=8`
and `FE35_AND_SCAN_KN_ASSERTIONS=434`, including ready_timeout/cleanup_failure.
This does not establish a device result or explain previous intermittent failures.
Helper integration/package passed; the healthy installed helper remains untouched.

App failed before UIKit execution: ScanQRCode.m supplied CGImageAlphaInfo where
CGImageCreate requires CGBitmapInfo under Werror. The local explicit conversion
preserves 8-bit gray, 8 bits/pixel, one byte/pixel, no alpha. The adjacent test
RGBA alpha constant now has the same explicit conversion. Werror stays enabled.
CPU golden/scales 2,3,4/bounds/repeated generation passed; system decoder and UIKit
lifecycle did not run. There is **no App DEB or new App executable hash**.

Host failed separately: Linux C feature visibility/SIGPIPE/peer-PID errors are
addressed by local parent commit `94ac20bf7bb3d80020e78c3733549da376c4d476`;
JVM tests did not run because Maven plugin/BOM downloads returned HTTP429.
Neither failure is waived. This Windows host has no installed Linux runtime or
Apple SDK; prior strict Linux cross-compilation is not runtime test evidence.

Apple artifact `15145905964`, 12401684 bytes, local path:
`C:\Users\quesi\AppData\Local\Temp\openhc-run-45875853812\apple-artifact.zip`.
SHA256 matches the supplied GitHub digest:
`aef52fb49f3d3737e190703b195a9ce5b39ec0ca7dbb2a898d1077a4fb86a60c`.
BUILD.txt first line is exactly the source above; Xcode16.4/iOS SDK18.5,
Kotlin2.1.20/Gradle8.13/JDK17. The ZIP contains device framework and both crypto
targets, but no Simulator framework. The two generated device header copies
match and include all four scan-session selectors checked by the reuse verifier.

| Reused member | SHA256 |
| --- | --- |
| iosArm64 framework binary | `2375aa11636183f8828f3694ce36aacfb5fc8036fa0506aaeb4112d61a6863a3` |
| iosArm64 framework header | `18ff9794601d195522dac9c17fca742e76286af80241180bd4a97ceb4af46f1a` |
| iosArm64/libcrypto.a | `104872be4dc8240c73f825e401a1799c6b03fcae49932b29cdb43781b823e3c8` |
| iosArm64/libopenhc_crypto.a | `7d4af63fdba2cbacad6759038a244d5e406643670cfea851179f4de1a5fc1277` |
| iosSimulatorArm64/libcrypto.a | `985527ef672637e8b865cbc5ddd6ecb5711af5fe65fb8bc5fb84f7dfd5a3dfac` |
| iosSimulatorArm64/libopenhc_crypto.a | `e62d3d9e72700f014c00f0e0a48bd200c7af6ed7867c2c5d107e0ca7af2a8ed9` |

The helper DEB in this archive is NOT the installed healthy pin and is not reused.
No CLI package is restored. App installation remains closed; healthy helper
executable pin remains
`34a3c3ca5d85d4e3863ff7631acec6dce8c636423be68b49edfe356810a6fc55`.

## Proposed single focused run

`.github/workflows/scan-app-focused.yml` is dispatch-only, explicitly named as
focused acceptance, with a separate required result. Existing full stage0 CI
and its failure are unchanged. Publication/dispatch is for the coordinator to
authorize after review; nothing was triggered here.

1. Linux: execute the three affected real C suites (including default-SIGPIPE
   regression), CPU QR, archive policy, reuse-fencing tests, and JVM tests.
   A download429 remains a failed JVM step; no dependency/repository change.
2. Mac: verify ZIP digest, BUILD source, identical generated headers and required
   selectors, reject any framework/crypto source/build-input diff or untracked
   input against 6d173181, then restore only device framework and crypto.
   The source guard covers bridge/native/Gradle/config/crypto build inputs;
   current changes are ObjC UI and theos C, outside those framework inputs.
3. Run the three real Darwin C suites, preserving SO_NOSIGPIPE and LOCAL_PEERPID,
   then strict arm64 iPhoneOS C11/Werror object compilation of both changed C
   sources. This covers 94ac20b's Darwin/iOS compilation and Darwin runtime
   behavior without rebuilding or replacing the helper executable.
4. With the same Xcode16.4, build only
   `gradle :bridge:linkReleaseFrameworkIosSimulatorArm64 --no-daemon --stacktrace`.
   The Simulator framework is absent from the ZIP and cannot be claimed reused.
   Static crypto is reused; Gradle dependency cache contains no identity/config.
5. Run `bash scripts/check-scan-ui.sh`: real CPU C golden, actual UIKit compilation,
   system decoder three scales with UTF8 Chinese/leading zero/4-module border,
   repeat and invalid bounds, lifecycle Start/Stop/late events/failure/expiry and
   actual system background delivery; build rootless App DEB and check xz,
   numeric root ownership, precise modes/layout/no links/no scripts, arm64,
   code signature and production otool dependencies without CoreImage/OpenGLES.
   CIDetector remains linked only into the test executable. Native archive
   writer tests run before the App build on the runner's real dpkg-deb.

The App result runs even if the independent Darwin C suite fails; neither result
can turn the required focused check green unless all jobs succeed. Upload scope
is BUILD/logs/scan-ui only, never a helper/CLI/identity/config/device-log bundle.
Failure or missing DEB keeps installation closed; no pin is inferred from ZIP
existence. A successful focused result is not full stage0 CI acceptance.

## Delivery prerequisite and minimal commands (not executed)

GitHub dispatch requires the workflow file registered on the default branch.
This is a new workflow; merely pushing it to the candidate branch is insufficient.
The coordinator can publish this workflow file alone to default without matching
the existing full-stage0 push path filter, then publish the reviewed candidate
with a `[skip ci]` commit trailer to suppress its push workflows, and dispatch the
focused workflow at the exact candidate ref. This does not suppress dispatch.
Do not publish the candidate by an ordinary unqualified push that starts full Mac.

```text
gh workflow run scan-app-focused.yml --repo 2018187068-prog/OpenHC-iPad --ref <reviewed-candidate-ref>
```

The resulting run's head SHA must equal the reviewed candidate SHA before audit.
Policy reference: GitHub Docs "Skipping workflow runs" (skip directives affect
push/pull_request), and "Manually running a workflow" (default-branch registration).

Local review already executed on Windows: real pinned ZIP audit, five reuse
fencing/restore tests, real CPU C golden/scales/bounds/repeats, YAML parsing and
diff whitespace check. None compiles UIKit. No new App pin, package or device
acceptance exists. After focused Apple success, audit its new ZIP/BUILD/DEB and
executable hashes, then coordinator App-only update and user stable Start/PONG
are still required. The old CoreImage crash remains unaccepted; phone cannot
connect, production backend disabled.
