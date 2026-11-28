# FE36 INFORM terminal correction

The digest-audited run 46098517235 at
365a4b43c2ab5a91544c6ff1d94fe679d3f932c6 failed at wrong_pin; this is
not a successful owner/UI/package run. The archived static assertion is
negative-auth-terminal, followed by phone_real_crypto_exchange, proxy EOF,
and cleanup uncertainty. Native90/JVM92 and the earlier success case passed
at that old SHA only. Original evidence remains in
D:/orcafile/ci-evidence-46098517235 and audit-46098517235.txt.

## Causal evidence

KotlinAccessoryAuthenticator.receive emits Send(HiChainBuild.inform(error))
before Failed, matching read-only upstream 8132399. Fe36AuthSessionBridge
preserves SEND then FAILED/CLOSE. The native adapter writes SEND before
returning failure and C transport cleanup. The reference error codes are
VERIFY_PROOF_FAILED=17 for wrong PIN and VERIFY_EXCHANGE_FAILED=29 for a
forged signature. Existing wrong-PIN envelope golden contains INFORM 0x8080.

The test phone incorrectly converted every nonempty proxy response to SEND
alone. Thus its rejected() assertion threw after receiving the real INFORM,
its wrapper discarded AuthFixture/static assertion, and its socket closed.
Python attempted another request-header read before draining the pending
auth-CID close. The prior exact six-byte close parser fixed a separate
boundary but could not fix this earlier INFORM interpretation.

## Bounded changes

- scripts/hicar-auth-sim-fixture.m validates the actual error envelope,
  integer message/code and scenario-specific 17/29; retains SEND bytes and
  appends FAILED/CLOSE. Negative checks now require exact ordered actions,
  reference error, nil returned key and unchanged direct-bridge trust.
- scripts/test-fe36-cid-simulator.py validates INFORM, forwards it unaltered,
  reads the exact auth close once and sends 0x81 once, then performs the
  original strict listener/control cleanup. Unexpected/duplicate close or
  failed ACK cannot report success. All 21 case definitions remain intact.
- scripts/fe36-cid-sim-fixture.m records the safe exception name/reason before
  the existing assertion. Unknown external text is redacted. Phone diagnostics
  include static phase and exchange index only; Python records operation,
  command opcode/parameter length and ACK phase, never payload/PIN/key/identity.
  Evidence is copied in finally even on launch failure/exception.
- scripts/test-fe36-negative-terminal.py exercises seven exact command
  checks, twelve INFORM/ACK boundaries and three real Windows loopback
  executions of the actual run_case proxy: wrong PIN, forged signature, and
  cleanup disconnect. Peers and reply bytes are synthetic; no crypto or
  native transport executes in these portable cases. No native integration
  success marker is printed for them.
- scripts/test-simulator-failure-evidence.py retains four earlier cases and
  adds two FE36 launch-failure/exception cases proving finally persistence.

No production implementation, common crypto, timing budget, trust/key callback,
cleanup/delegation assertion, or pinned reuse validation changes. Existing
source manifest already includes all five changed script paths.

## Executed local checks

Windows Python 3.12: command7, INFORM/ACK12, loopback3 and evidence6 pass;
py_compile of the three affected Python scripts passes. Existing Git Bash
bash -n passes for check-scan-owner-apple.sh and
test-fe35-cli-smoke-simulator.sh. Scoped git diff --check passes.

Existing Corretto JDK17 and Gradle8.13 --offline ran :bridge:jvmTest filtered
to Fe36AuthBridgeTest, HiCarAuthSessionTest, RoundTripTest and CVectorsTest:
45 tests, zero failure/error/skip; BUILD SUCCESSFUL. No installation or
repository substitution occurred. Full ObjC/Native/Simulator, process34,
all21 CID, UI70/systemQR3 and packages need the new focused owner CI.
No Apple/POSIX runtime pass is claimed from Windows.

All 16 tracked unrelated dirty file hashes match the task-start snapshot
D:/orcafile/preservation-b01796-start.json (including the originally protected
14 plus retained mixed documents); both historical document byte suffixes
match retained binaries. Index was empty before staging. Native crypto and
framework reuse inputs remain unchanged. The old ready_stop symptom was not
reproduced in one run; its intermittent root cause remains unproven.

Production admission stays deny-all and deployed provider synthetic. This
software correction supplies no Honor/iPad evidence. After the retained
suite passes, next software work is post-auth control/session/lease handoff
into WiFi/TCP with FE35 retained until the phone joins WiFi; DMSDP/media and
target launch/config/BD_ADDR/trust persistence remain unproven. No device,
identity, wireless, installation, helper or pin operation was performed.
