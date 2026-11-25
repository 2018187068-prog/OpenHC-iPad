# Controller ownership and recovery audit — 2026-11-26

Latest continuation: USB SSH is currently unavailable even after the user
confirmed an administrator restart of Apple Mobile Device Service. One host
recheck still found zero USB devices and an empty SSH banner. No more trust
reset, helper stop, unload or power action is requested. Offline signature
audit, startup isolation and a synthetic transport metadata reader are recorded
in `ROLE-PROBE-DIAGNOSTIC.md`. The probe's SIGKILL and endpoint owner PID remain
unresolved. New CI artifacts are not physical evidence. The power trial below
is historical; its procedure is not authorization to repeat it in this session.

The external root-shell capture is complete. The initial audit below was read-only; a subsequent bounded power/restoration trial is recorded in the latest-result section. **The uncontested ownership gate remains incomplete because a shared helper's role was not verified in the initial preflight. Its process name alone does not establish competition.** Existing USB SSH through iproxy PID 39484 / port 2222 was reused. Lockdown pairing was not retried.

## Device evidence

Captured as UID 0, using `/var/jb/usr/bin/launchctl` and `/bin/ps`. Raw local evidence:

- `artifacts/device-validation-20261126/root-ownership-snapshot-20261126-022903.log`
- `artifacts/device-validation-20261126/root-ownership-detail-20261126-023012.log`

| Service/process | Observed state | Interpretation |
| --- | --- | --- |
| `ch.ringwald.BTstack` | running, PID 35779, `/var/jb/usr/bin/BTdaemon`; launchd owns `/tmp/BTstack` listener | Local daemon availability, not HCI ownership |
| `com.apple.bluetoothd` | running, PID 30370, `/usr/sbin/bluetoothd` | Apple Bluetooth has not been relinquished for a BTstack trial |
| `com.apple.BlueTool` | registered, not running; last idle jetsam exit / list status 9 | An on-demand service remains loaded; absence of its process is not an unload |
| `com.apple.BTServer.le` | running, PID 485, `/usr/sbin/BTLEServer` | Apple LE service is still active |
| `com.apple.BTServer.avrcp`, `.map`, `.pbap` | registered, not running | Not evidence of exclusive BTstack ownership |
| `com.apple.BTServer` | no such service, exit 113 | This OS uses subservice labels; do not interpret the missing umbrella label as absence of Apple Bluetooth |
| Showcase | main process PID 27255 present; no `CarDisplaySim` in the process capture | No Bluetooth helper observed; app presence alone does not establish its UI/session state |
| `com.reng.showcase.bluetooth-recovery` | absent, exit 113 | No existing Showcase crash-recovery job can be relied on |

`/var/root/Library/ShowcaseBluetooth/recovery.plist` exists but its ready file does not. `/tmp/showcase_bt_owned` is absent. `/tmp/showcase_bt_ready` exists despite the absent guard/helper: treat it as a stale/unverified marker, not a successful takeover.

`dpkg-query -S` attributes BTdaemon to `com.rostane.showcase`, installed version `1.0~beta5-3`. This is package provenance only, not proof that its executable matches the reference source commit. The earlier version/revision query and local FE35/FE36 service cycles remain passed and were not repeated.

The 0.3.2 binary's `OWNERSHIP_SERVICE_PRINT=UNAVAILABLE_IN_SANDBOX` and `OWNERSHIP_PROCESS_SNAPSHOT=UNAVAILABLE_IN_SANDBOX` are explicit limitations. Its `OWNERSHIP_SNAPSHOT_DONE` only means that limited snapshot completed. The external logs above supply the previously missing service/process evidence; neither output is an ownership PASS.

## Reference implementation and applicability

Read-only Showcase checkout: `ce9d1d50758f67307deb3f00c901a8e82894930c`.

- `source/Showcase.m:357–398`: arm a launchd-owned recovery shell **before** removing Apple services; require its ready handshake. The reference watches the app PID, so it is not a ready-made lifetime guard for an independent OpenHC probe.
- `source/Showcase.m:401–413`: restore **BlueTool first, then bluetoothd**; remove the ownership marker and disarm the guard only after initiating restoration. OpenHC's next probe must additionally verify restored service/process state rather than equate load requests with success.
- `source/Showcase.m:4431–4485`: the non-Taurine rootless path unloads bluetoothd and BlueTool, waits for process exit, then cycles the BTstack launchd job/socket before starting its client. The reference's fixed wait is not proof that the processes exited; the OpenHC gate must check and abort if they remain.
- `source/Showcase.m:4511–4550`: the reference allows one complete daemon/client retry when no controller events arrive, including a wait before restarting. This is not permission for unbounded retries or escalation to force-kill.
- `source/Showcase.m:4588–4617`: the force-kill sequence belongs to a `SHOWCASE_TAURINE` block. This device is Dopamine / iPadOS 15.8.8. Do not copy that branch into this runbook.
- `source/Showcase.m:4776–4787`: stop the session helper, unload BTstack, remove its socket, then return control to Apple.
- `btstack-rootless/port/ios/src/btstack_control_iphone.m:462–471`: rootless `iphone_on` relies on the caller having unloaded Apple's services; `iphone_off` is a no-op. A BTstack OFF event alone cannot prove Apple restoration.
- `btstack-rootless/platform/daemon/src/daemon.c:915–934, 1772–1825`: power requests belong to connected clients; absent requests can trigger a delayed power-off. Retain one client for the entire bounded trial and observe cleanup rather than disconnecting immediately after sending power-on.
- `tests/test_bluetooth_recovery.py` models the reference guard ordering with mocked commands. It is source evidence, not a recovery test on this iPad; no crash/recovery test has been executed here.

The reference's CarPlay helper, full app Start flow and skywalk test scripts have wider effects (including helpers, network state and raw event logging). Do not run them as a HiCar power probe or copy raw HCI/event logging into OpenHC. No pairing database, credentials, real authentication bytes or controller link keys are to be read or logged.

## Next trial: prerequisites and execution order

These are scheduled steps, not device actions already performed. The ownership audit is complete; exclusive ownership, power-on and restored-state gates are still pending.

1. Prepare a separate bounded power-only probe and recovery guard. Current 0.3.2 exposes no powered or live peer option. Use a launchd job with its own OpenHC label, a ready handshake and an absolute deadline that survives SSH loss/probe crash. Include a manual USB recovery path. Verify the guard and cleanup ordering with mocked platform commands before touching the device. Do not rely on Showcase's currently absent guard, existing ready files, or an SSH-shell trap alone.
2. Immediately before a trial, confirm no active Showcase/CarPlay/HiCar session or helper is competing. Keep the Showcase UI idle; do not kill the app or reuse its Start flow. Capture the trial baseline once, including loaded services and daemon PID. If state changed since this audit, resolve that before takeover.
3. Arm the independent guard and positively observe its ready handshake. If readiness is not proved, leave Apple Bluetooth unchanged and stop.
4. In this observed Dopamine configuration, request unload of **only** `/System/Library/LaunchDaemons/com.apple.bluetoothd.plist` and `/System/Library/LaunchDaemons/com.apple.BlueTool.plist` using the discovered launchctl. Check command results, launchd state and process exit with a short bounded wait. Do not unload BTServer subservices merely because they exist. If either required Apple service remains registered/running or the result is ambiguous, restore and fail; do not add kill commands.
5. Under the armed guard, cycle only `/var/jb/Library/LaunchDaemons/ch.ringwald.BTstack.plist` as in the applicable reference branch. Remove the known `/tmp/BTstack` socket only after the old daemon has exited. Verify the new launchd job, socket and daemon PID. Do not reuse the previous client connection across the restart.
6. Open a dedicated probe client and issue one bounded power request. Initial budget: 25 seconds to reach a validated `HCI_STATE_WORKING=2` event, with bounded framing/I/O and numeric metadata only. For this first controlled trial, do not automatically retry; preserve failure state metadata and restore. No discoverability, SDP advertisement, peer pairing, link authentication or AP change in this power-only trial.
7. Whether success, timeout, malformed event, SSH loss or interruption: stop the probe's own work, release its power request and close its channels/client; bound the OFF/close wait. Unload the trial BTstack job and confirm process exit before socket removal. Load **BlueTool, then bluetoothd**. Verify both jobs are registered, bluetoothd is running/healthy, and BlueTool is available on demand; it need not remain running after idle exit. Confirm Apple's pre-existing BTServer LE registration remains available. A load return code or residual ready file is insufficient.
8. Restore the pre-trial BTstack registration as an on-demand, unpowered daemon service after Apple restoration, because it was loaded in the baseline. Do not power it during restoration. Verify the resulting launchd/socket state and no unexpected helper. Only after restored state is observed may the recovery guard be disarmed. Report restoration independently from the power result; a failed restore blocks all further trials and requires the prepared USB recovery procedure.

The future guard must implement the same restoration ordering on abnormal exit and deadline expiry. No guard has been installed or armed by this audit. The above recovery path is reviewed against source but remains untested on this device.

## Latest physical power/restoration result

One trial ran on 2026-11-26 after twelve offline tests passed. Evidence:
`artifacts/device-validation-20261126/power-trial-20261126-024343.log` and
`post-power-helper-audit.log`. The independent launchd guard acknowledged ready.
Apple bluetoothd and BlueTool jobs/processes were observed absent before the
BTstack restart. One client observed `OFF=0`, `INITIALIZING=1`, `WORKING=2`,
`HALTING=3`, then `OFF=0`, within its bounded power/release window.

The guard restored BlueTool before bluetoothd, then the original BTstack
registration, all load requests returning 0. The host verified Apple/LE jobs,
bluetoothd process, BTstack registration/socket and a fresh OFF state before
disarming. A separate post-trial read-only capture confirmed bluetoothd PID
37358, BlueTool 37365, BTLEServer 485, BTdaemon 37392, recovery-job absence
(113), the cleared active lock and per-run `RESTORED` result. There was no phone
connection or peer/security payload logging. This tests normal requested
restoration on device; SSH-loss/deadline failure paths have only mock evidence.

**Qualification:** baseline and restored snapshots both contain
`27078 1 S CarPlay Simulator`. The source identifies this as the rootless
`SVC_HELPER_NAME` (`Showcase.m:242`). Initial `named()` matched only `/name`,
so it failed to reject this bare comm. The power and restored-state observations
remain valid, but the initial `POWER_PREFLIGHT_OK` and overall numeric pass are
insufficient evidence of an uncontested session. Name parsing now accepts bare
or absolute comm values with spaces and rejects the known truncated alias too.
Regression tests cover this case. No helper was killed.

User correction: the user did not start Showcase. The request to stop an
assumed active session was premature and is withdrawn. New read-only captures
find only PID 27078 (device start time 2026-11-25 10:43:00); the earlier Showcase
PID 27255 and Bluetooth helpers are absent. The known BAA broker socket exists,
and the ownership marker is absent. Source `Showcase.m:3500–3516,3613` launches
and preserves a BAA broker using the same executable. `carplay_services.m:6369–6372`
returns into the broker loop before network-session initialization. These facts
are consistent with a persistent broker and do not establish an active CarPlay
session. They do not yet associate the socket's owner with PID 27078: available
tools did not include lsof/Python, and launchctl procinfo returned 45. No process
argv, broker authentication data, certificate/key material or broker logs were
read. No broker requests were sent. Logs: `showcase-process-role-audit*.log` in
the same artifact directory.

The driver now reports `SHARED_HELPER_ROLE_UNVERIFIED` for these shared names,
keeping an explicit role-verification gate rather than declaring competition.
Next use process/socket ownership metadata or a narrow PID/role-only platform
probe; do not kill the broker, ask the user to open Showcase to stop it, or
whitelist the process from socket existence alone.

## Guarded power driver and USB recovery

`scripts/btstack-power-trial.py --execute` uses the existing USB SSH port 2222
and an already trusted SSH host key. Authentication is read from interactive
input/stdin and is not saved. It uploads a root-only, per-run recovery shell and
launchd job under `/var/root/Library/OpenHCStage0Power/<run-id>/`.
`scripts/test-btstack-power.py` exercises synthetic framing and mocked launchctl,
process, heartbeat and deadline behavior without a device.

The independent job `io.github.gcbond.openhc.stage0-power-recovery` starts before
takeover, acknowledges readiness, watches a two-second heartbeat (20-second
expiry), and has a 120-second absolute deadline. It is the sole recovery actor.
The driver refuses takeover with less than 65 seconds remaining. The first
power window permits 25 seconds to WORKING and 15 seconds for OFF, including
the daemon's source-defined ten-second delayed power-off. No raw events are
logged. Apple restoration and power success are reported independently.

If SSH drops, allow the guard to recover before reconnecting over USB. Inspect
only the known per-run `result` and `recovery.log`, plus launchctl/comm snapshots.
If the job is still running, request its existing restoration with:

```sh
touch /var/root/Library/OpenHCStage0Power/<run-id>/restore-request
/var/jb/usr/bin/launchctl print system/io.github.gcbond.openhc.stage0-power-recovery
```

If that job is absent, first confirm its process has exited and no other
recovery actor is running, then run the same uploaded shell with the same fixed
arguments from its `recovery.plist` (no second independent restoration actor).
Do not append kill commands. A failed/unknown BTdaemon-exit or launchd-absence
check stops restoration before returning the controller to Apple; inspect the
failure and resolve that condition before retrying the same ordered guard.
Keep the guard and active lock until restored services, bluetoothd process,
BTstack socket/registration and an OFF state have been independently observed.

## Later phone trial (after the powered gate)

After the power-and-recovery loop passes, arrange a separate bounded session with the user-reported Honor 20 Pro / HarmonyOS 4.0 / HiCar phone, with the user performing the intended phone action. Record the phone's presence/readiness before opening a radio-visible window.

- Implement a live transport probe first; `--btstack-services` currently registers and removes local services while OFF and cannot serve a wireless session. Keep one power lease for the full trial and use the independent recovery guard.
- Validate actual over-air SDP for FE35 and the auth subchannel's UUID. Capture assigned/negotiated RFCOMM channels; the prior local candidates 16/17 are not fixed HiCar channel numbers.
- Follow OpenHC's control/auth role and direction. `NearbySession.kt:501–504` defines FE35 and default FE36 UUIDs; `NearbyAction.kt:157` and `WirelessReceiverSession.kt` allow the peer to provide an auth UUID/channel and change connection direction. Do not assume both channels always listen on the iPad or that generic Bluetooth settings pairing starts HiCar.
- Distinguish a synthetic transport client from a real HiCar session. For transport, exchange only known synthetic data in both directions on both channels, count bytes without dumping payloads, then close/reopen. For the real phone, do not transmit arbitrary synthetic frames into its authentication protocol; do not record real authentication payloads or keys.
- Verify the no-forced-link-authentication requirement using installed runtime evidence. Reference RFCOMM `LEVEL_0` alone does not establish the installed binary's behavior. A phone pairing or an encrypted RFCOMM connection alone is not a HiCar handshake PASS.
- Restore Apple and the baseline service registrations after every session and record that restoration independently. AP/hotspot and full HiCar authentication remain separate gates.
