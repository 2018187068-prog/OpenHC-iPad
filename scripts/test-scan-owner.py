"""Run the actual portable owner core; only OS evidence/lease effects are fake.
No device, socket, identity, Trial or controller operation is performed here.
"""
import os
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('owner_sim_driver', ROOT / 'scripts/test-fe35-cli-inbound-simulator.py')
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)


def guard_observation(completed=1199, cleanup=True, tick_first=False):
    """Injected numeric observations; production owner behavior is tested in C."""
    lines = []
    def phase(e, state, now, deadline, worker=1):
        lines.append(f'OWNER_PHASE effect={e} state={state} generation=1 now={now} deadline=240100 phase_deadline={deadline} worker_started={worker}')
    phase(0, 1, 100, 3100, 0)
    phase(5, 1, 101, 3100, 0)
    phase(1, 2, 101, 3101, 0)
    phase(2, 3, 102, 3101)
    phase(3, 3, 200, 3101)
    phase(4, 3, 200, 3101)
    delegated = not cleanup or completed >= 1200
    if cleanup and delegated:
        lines.append(f'OWNER_EXPIRY cause=phase state=4 now={1200 if tick_first else completed} phase_deadline=1200')
    phase(6, 4, 1200 if cleanup and delegated and tick_first else completed, 1200)
    phase(8 if delegated else 7, 6 if delegated else 5, completed,
          1200 if delegated else completed + 3000)
    phase(9, 0, completed + 1, 1200 if delegated else completed + 3000)
    decision = 2 if cleanup and delegated else 1 if cleanup else 3
    return '\n'.join(lines) + '\n', f'OWNER_GUARD_DECISION={decision}\n', decision


def guard_regressions(exe, tmp):
    checks = 0
    def verify(status, trace, cleanup, expected, process=False):
        nonlocal checks
        try:
            actual = driver.validate_owner_guard_trace(status, trace, cleanup, process=process)
        except AssertionError as error:
            assert str(error).startswith('owner_guard_'), 'fixed redacted assertion label'
            actual = 0
        # Same extracted native fixture routine, actual compiled local C.
        status_path = Path(tmp) / 'owner-status.log'
        status_path.write_text(status, encoding='ascii')
        delegated = 'OWNER_GUARD_DECISION=1' not in trace
        result = subprocess.run([str(exe), str(status_path), str(int(cleanup)), str(int(delegated))],
                                capture_output=True, text=True, check=True, timeout=10)
        assert actual == expected and int(result.stdout) == expected, (actual, result.stdout, expected)
        checks += 1
    for completed in (1199, 1200, 1201, 1217):
        for tick_first in (False, True):
            status, trace, decision = guard_observation(completed, tick_first=tick_first)
            verify(status, trace, True, decision)
    status, trace, decision = guard_observation(201, cleanup=False)
    verify(status, trace, False, decision)
    pending_recovery = '\n'.join(status.splitlines()[:-1]) + '\n'
    verify(pending_recovery, trace, False, decision, process=True)
    try:
        driver.validate_owner_guard_trace(pending_recovery, trace, False)
    except AssertionError as error:
        assert str(error) == 'owner_guard_release_count'
    else:
        raise AssertionError('synthetic verified recovery requires release')
    checks += 1
    late, trace, _ = guard_observation(1217)
    expiry = 'OWNER_EXPIRY cause=phase state=4 now=1217 phase_deadline=1200\n'
    for bad in (
        late.replace(expiry, ''),                           # boolean alone is insufficient
        late.replace('now=1217 phase_deadline=1200\n', 'now=1199 phase_deadline=1200\n', 1),
        late.replace('state=4 now=1217', 'state=5 now=1217'),
        late.replace('generation=1', 'generation=2', 1),
        late.replace('deadline=240100', 'deadline=240101', 1),
        late.replace('effect=8 state=6', 'effect=7 state=5'),
        late.replace('OWNER_PHASE effect=8', expiry + 'OWNER_PHASE effect=8'),
        late.replace('effect=4 state=3 generation=1 now=200', 'effect=4 state=3 generation=1 now=99'),
        late.replace('OWNER_PHASE effect=8', late.splitlines()[-2] + '\nOWNER_PHASE effect=8'),
        late.replace(expiry, 'OWNER_EXPIRY cause=clock state=4 now=1217 last_now=200\n'),
        late[:late.index('OWNER_PHASE effect=6')],
        '',
    ):
        verify(bad, trace, True, 0)
    # Existing separately sampled effect time may cross the boundary even when
    # the exact completion tick (RESTORING deadline-3000) was still timely.
    timely, trace, _ = guard_observation()
    timely = timely.replace('now=1199', 'now=1201').replace('now=1200 deadline', 'now=1202 deadline')
    verify(timely, trace, True, 1)
    # Trace marker is independently checked by Python, never arbitrary output.
    for bad_trace in ('', 'OWNER_GUARD_DECISION=1\n', trace + trace):
        try:
            driver.validate_owner_guard_trace(late, bad_trace, True)
        except AssertionError as error:
            assert str(error) == 'owner_guard_native_trace_agreement'
        else:
            raise AssertionError('contradictory native marker accepted')
        checks += 1
    print(f'SCAN_OWNER_GUARD_EVIDENCE_REGRESSIONS={checks};BOUNDARY=injected-traces-actual-C-parser')


compiler = [shutil.which("zig"), "cc"] if shutil.which("zig") else [shutil.which("cc") or "cc"]
with tempfile.TemporaryDirectory(prefix="openhc-owner-") as tmp:
    for test in (False, True):
        exe = Path(tmp) / ("owner-test" if test else "owner-deny")
        if os.name == "nt": exe = exe.with_suffix(".exe")
        cmd = compiler + ["-std=c11", "-Wall", "-Wextra", "-Werror"]
        if test: cmd += ["-DOPENHC_SCAN_OWNER_TEST"]
        cmd += [str(ROOT / p) for p in ("theos/scan-owner/ScanOwner.c",
            "theos/scan-owner/ScanOwnerPeer.c", "scripts/scan-owner-tests.c")]
        subprocess.run(cmd + ["-o", str(exe)], check=True, timeout=120)
        subprocess.run([str(exe)], check=True, timeout=10)
    # Compile the exact pure-C native fixture evidence predicate without Apple
    # UI/framework stubs; this does not claim Objective-C or Simulator execution.
    fixture = (ROOT / 'scripts/scan-owner-sim-fixture.m').read_text()
    predicate = fixture.split('static int fixture_guard_decision(', 1)[1].split('/* OWNER_GUARD_EVIDENCE_END */', 1)[0]
    source = Path(tmp) / 'guard-evidence.c'
    source.write_text('#include <stdio.h>\n#include <stdlib.h>\n#include <string.h>\n#include "' +
                      (ROOT / 'theos/scan-owner/ScanOwner.h').as_posix() + '"\n' +
                      'static int fixture_guard_decision(' + predicate +
                      '\nint main(int argc,char **argv) { if(argc!=4)return 2; printf("%d\\n",fixture_guard_decision(argv[1],atoi(argv[2]),atoi(argv[3]))); return 0; }\n')
    exe = Path(tmp) / ('guard-evidence.exe' if os.name == 'nt' else 'guard-evidence')
    subprocess.run(compiler + ['-std=c11', '-Wall', '-Wextra', '-Werror', str(source), '-o', str(exe)],
                   check=True, timeout=120)
    guard_regressions(exe, tmp)
