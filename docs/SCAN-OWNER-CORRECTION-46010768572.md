# Focused owner compile correction — 2026-11-27

Task task_75908bb05334 / ctx_cd7e457a1251. This is a bounded correction to
dd061e5ccee8a62da9424d037cfae12ae09e172d on stage0-auth-validation.

## Completed run evidence

Run 46010768572 completed with focused-host, owner-apple and required all
failure. There is no new App package or device acceptance from this run.
The coordinator supplied completed metadata; this task did not query that run.
Both existing local ZIP digests were independently rechecked without downloading:

- Host artifact 15204446530: SHA256
  5cc77678523547b197aa1cae837efe731e781e7c286e24861a3978e7a4c54e1d.
- Apple artifact 15203073267: SHA256
  92d74e0684e519af97cc60d46311991ea111e4938a2193f1b338e4571e2eb99a.
- ZIP directory: C:/Users/quesi/AppData/Local/Temp/openhc-run-46010768572.

Host owner compilation failed at scan-owner-tests.c:10 under GCC Werror for
misleading indentation. Coordinator's artifact audit found JVM XML 47 tests
with zero failure/error/skip; existing socket, CPU QR, archive15, owner-probe3
and crypto6 passed. These are evidence for dd061e5, not the corrected source.

Apple built current device/Simulator frameworks and Native tests; Native XML
45/45 had zero failure/error/skip. Darwin deny-all/551 and affected sockets
passed. iphoneos selected LOCAL_PEERTOKEN/SOL_LOCAL, without device runtime
validation. The actual deployment compile log contains nine ARC switch errors:
case jumps enter the lifetime of strongly capturing blocks at original
ScanOwnerRuntime.m lines 151, 155, 160 and 178. This task read that exact archived
log. Simulator deployment compilation, original 3 FE35 + 8 native + 11 owner
integration, new UIKit isolation and current App packaging were not reached.

## Exact correction boundary

1. scripts/scan-owner-tests.c: explicit braces for deadline initialization, six
   independent peer-freshness branches and guard-failure if/else; no assertion
   or control-flow semantics change.
2. theos/scan-owner/ScanOwnerRuntime.m: a lexical block around each of
   OHC_ARM_GUARD, OHC_TAKEOVER, OHC_RUN_WORKER and OHC_REQUEST_RESTORE. All
   non-brace/non-whitespace tokens remain identical. Executor scheduling,
   captures, callbacks, fence, completion, heartbeat and guard decisions remain
   unchanged. No other Objective-C source needs this switch-scope correction.
3. This task-specific report is the only additional committed file. Existing
   mixed report/history changes stay outside the index.

## Actual local validation and limits

- Windows, existing Zig: python scripts/test-scan-owner.py exited 0, reporting
  SCAN_OWNER_PRODUCTION_DENY_ALL_OK and SCAN_OWNER_TEST_ADAPTER_CHECKS=551.
- Source check verified exactly four added scope pairs with no other runtime
  tokens changed, and reviewed all repository theos/scripts Objective-C switch
  sites (only the runtime contains a switch).
- Existing Git Bash -n passed separately for check-scan-owner-apple.sh,
  test-fe35-cli-smoke-simulator.sh and check-scan-ui.sh. Literal harness compile
  inputs resolve; deployment entry has no OPENHC_SCAN_OWNER_TEST flag.
- git diff --check passed. No Werror/compiler/assertion relaxation.
- No GCC in PATH or checked common installed locations; no Linux/GCC runtime
  or Apple SDK compilation is claimed. No environment was installed.

## Single focused submission and pending gates

Submit the three explicit paths above with [skip ci], push the current feature
branch once, verify remote SHA, then dispatch workflow 431974121 once with
validation_scope=owner. Record the exact commit/run receipt in the newest local
HANDOFF-CURRENT.md and docs/RESUME-CHECKPOINT.md sections and a temporary receipt;
those mixed historical files must remain unstaged. Read initial metadata once,
then await coordinator completion notice without watch/poll/duplicate dispatch.

The unchanged workflow owns full focused host checks and one macos-15 combined
entry: bash scripts/check-scan-owner-apple.sh /absolute/pinned-source.zip. Only
verified crypto from artifact15145905964 is reused; current frameworks and
Native tests rebuild from corrected-source inputs. No old framework restore,
legacy full stage0 or healthy helper package build. All original protocol,
typed completion, owner, CPU QR/system decoder/UI and App archive gates remain.
Previous dd061e5 compiled artifacts are not corrected-SHA acceptance.

Production admission stays deny-all: restricted root-controlled caller policy
and target-native Trial independent guard actor remain absent. Synthetic
admission/daemon/lease fixture boundaries confer no production authority.
Rootless Dopamine/Theos DEB/macOS-15/ldid -S remains unchanged. Installer/App/
healthy-helper pins are untouched. No device, identity, credential, radio,
power, Showcase or BAA operation; no phone-connectivity/full-S0/stability claim.
