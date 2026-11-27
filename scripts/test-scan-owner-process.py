"""Native private-channel/guard software checks. No hardware or deployment.

Windows: actually run portable strict-C protocol, cross-compile POSIX sources;
explicitly NOT process-runtime acceptance. Linux/macOS: actual exec/socket/fence
and owner-core tests. Test admission and Trial recovery effects are inert.
"""
import argparse
import os
from pathlib import Path
import shutil
import socket
import struct
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'theos/scan-owner'
FRAME = struct.Struct('>4sBBHQQqIi')
ARM, TAKEOVER, BEAT, COMPLETE, RESTORE, DELEGATE, OK, DENIED = 1, 2, 3, 4, 5, 6, 128, 255


def compile_programs(destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    compiler = [shutil.which('zig'), 'cc'] if shutil.which('zig') else [shutil.which('cc') or 'cc']
    strict = ['-std=c11', '-Wall', '-Wextra', '-Werror']
    protocol = destination / ('lease-protocol.exe' if os.name == 'nt' else 'lease-protocol')
    subprocess.run(compiler + strict + [str(SOURCE / 'ScanLeaseProtocol.c'),
                   str(ROOT / 'scripts/scan-owner-process-tests.c'), '-o', str(protocol)], check=True, timeout=120)
    subprocess.run([str(protocol)], check=True, timeout=10)
    target = ['-target', 'x86_64-linux-musl'] if os.name == 'nt' else []
    binaries = {}
    shared = [str(SOURCE / p) for p in ('ScanLeaseProtocol.c', 'ScanLeaseChannel.c')]
    for name, sources, test in (
        ('guard-deny', ['ScanGuardProcess.c'], False),
        ('broker-deny', ['ScanBrokerProcess.c'], False),
        ('guard-test', ['ScanGuardProcess.c'], True),
        ('broker-test', ['ScanOwner.c', 'ScanOwnerPeer.c', '../../scripts/scan-owner-process-fixture.c'], True),
    ):
        exe = destination / name
        flags = ['-DOPENHC_SCAN_OWNER_TEST', '-DOPENHC_SCAN_OWNER_PROCESS_TEST'] if test else []
        subprocess.run(compiler + target + strict + flags + shared +
                       [str(SOURCE / p) for p in sources] + ['-o', str(exe)], check=True, timeout=120)
        binaries[name] = exe.resolve()
    return binaries


def frame(op, sequence, generation=1, deadline=None, flags=0, status=0):
    if deadline is None:
        deadline = int(time.monotonic() * 1000) + 240000
    return FRAME.pack(b'OHCL', 1, op, 0, generation, sequence, deadline, flags, status)


def exact(sock, count):
    data = b''
    while len(data) < count:
        part = sock.recv(count - len(data))
        if not part:
            raise EOFError('guard closed')
        data += part
    return data


def wait_text(path, text, seconds=4):
    limit = time.monotonic() + seconds
    while time.monotonic() < limit:
        if path.is_file() and text in path.read_text(encoding='ascii'):
            return
        time.sleep(.02)
    raise AssertionError('missing bounded guard evidence: ' + text)


def native_now(binaries):
    # Same C clock as the native guard, no Python/macOS clock-epoch assumption.
    return int(subprocess.check_output([str(binaries['broker-test']), 'clock'], timeout=3))


class Broker:
    """Test broker with real private guard child; NEVER deployment authorization."""
    def __init__(self, binaries, directory, listener=None, missing=False):
        self.directory = Path(directory)
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.log = open(self.directory / 'broker.log', 'wb')
        if listener is None:
            self.socket, inherited = socket.socketpair()
            self.socket.settimeout(3)
        else:
            self.socket, inherited = None, listener
        self.process = subprocess.Popen([str(binaries['broker-test']), 'relay', str(binaries['guard-test']),
            str(self.directory), 'missing_ready' if missing else 'normal'],
            stdin=inherited, stdout=self.log, stderr=subprocess.STDOUT, close_fds=True)
        if listener is None:
            inherited.close()
        self.deadline = native_now(binaries) + 240000
        self.sequence = 0

    def exchange(self, op, *, fragments=False, **changes):
        self.sequence += 1
        request = frame(op, self.sequence, deadline=self.deadline, **changes)
        if fragments:
            for offset in range(0, len(request), 3):
                self.socket.sendall(request[offset:offset + 3])
        else:
            self.socket.sendall(request)
        reply = FRAME.unpack(exact(self.socket, FRAME.size))
        assert reply[2] == OK, ('guard rejected', reply[2])
        assert reply[4:7] == FRAME.unpack(request)[4:7], 'generation/sequence/deadline reply fence'
        return reply

    def close(self):
        if self.socket:
            self.socket.close()
        self.process.wait(timeout=18)
        self.log.close()


def runtime_checks(binaries, base):
    checks = 0
    for name in ('guard-deny', 'broker-deny'):
        environment = dict(os.environ, OPENHC_ROLE='root', OPENHC_GUARD_READY='1', OPENHC_ALLOW='1')
        result = subprocess.run([str(binaries[name]), 'START', '/tmp/forged', 'mobile'],
                                env=environment, capture_output=True, timeout=3)
        assert result.returncode == 78 and b'DEPLOYMENT_DENY_ALL' in result.stderr
        checks += 1
    for case in ('normal', 'disconnect', 'owner_death', 'cleanup_unknown', 'exit_unknown',
                 'missing_ready', 'guard_crash', 'lost_heartbeat'):
        directory = base / case
        directory.mkdir(mode=0o700)
        result = subprocess.run([str(binaries['broker-test']), 'owner', str(binaries['guard-test']),
            str(directory), case], capture_output=True, text=True, timeout=14)
        assert result.returncode == 0, (case, result.stdout, result.stderr)
        assert 'INHERITED_FD_ALLOWLIST_EOF' in result.stdout
        if case == 'guard_crash':
            assert (directory / 'fence').exists() and not (directory / 'restore.once').exists()
            # Crash releases flock but durable unresolved fence prevents takeover.
            other = Broker(binaries, directory)
            try:
                try:
                    other.exchange(ARM)
                except (OSError, EOFError):
                    pass
                else:
                    raise AssertionError('unresolved fence admitted competitor')
            finally:
                other.close()
        else:
            wait_text(directory / 'events', 'INERT_RESTORE_ONCE')
            events = (directory / 'events').read_text(encoding='ascii')
            assert events.count('INERT_RESTORE_ONCE') == 1
            assert not (directory / 'fence').exists()
            if case in ('owner_death', 'cleanup_unknown', 'exit_unknown', 'missing_ready', 'lost_heartbeat'):
                assert events.count('DELEGATE_ONCE') == 1 and 'PARENT_EXIT_OBSERVED' in events
            if case in ('cleanup_unknown', 'exit_unknown', 'lost_heartbeat'):
                assert 'LIVE_UNKNOWN_NO_RESTORE' in result.stdout
            if case == 'missing_ready':
                assert 'OWNER_WORK_AFTER_GUARD_READY' not in result.stdout
        (directory / 'owner.log').write_text(result.stdout + result.stderr, encoding='utf-8')
        print('SCAN_OWNER_PROCESS_CASE_OK=' + case)
        checks += 1
    for case, overrides in (('stale_generation', {'generation': 2}),
                            ('forged_role', {'flags': 1}), ('unknown_opcode', {'op': 90})):
        broker = Broker(binaries, base / case)
        try:
            broker.exchange(ARM, fragments=True)
            broker.exchange(TAKEOVER)
            kwargs = dict(overrides)
            op = kwargs.pop('op', BEAT)
            try:
                broker.exchange(op, **kwargs)
            except AssertionError as exc:
                assert 'guard rejected' in str(exc)
            else:
                raise AssertionError('forged/stale frame accepted')
        finally:
            broker.close()
        wait_text(broker.directory / 'events', 'INERT_RESTORE_ONCE')
        checks += 1
    broker = Broker(binaries, base / 'one_owner')
    broker.exchange(ARM, fragments=True)
    contender = Broker(binaries, broker.directory)
    try:
        try:
            contender.exchange(ARM)
        except (OSError, EOFError):
            pass
        else:
            raise AssertionError('competing owner admitted')
    finally:
        contender.close()
    broker.exchange(TAKEOVER)
    broker.exchange(COMPLETE, flags=7, status=1)
    broker.exchange(RESTORE)
    broker.close()
    assert (broker.directory / 'events').read_text().count('INERT_RESTORE_ONCE') == 1
    checks += 1
    for case, payload in (('forged_path', b'/tmp/owner START root'),
                          ('forged_guard_marker', b'READY PONG role=root')):
        broker = Broker(binaries, base / case)
        try:
            broker.exchange(ARM)
            broker.socket.sendall(payload.ljust(FRAME.size, b'\0'))
            assert broker.socket.recv(1) == b'', 'unframed authority/path accepted'
        finally:
            broker.close()
        wait_text(broker.directory / 'events', 'INERT_RESTORE_ONCE')
        checks += 1
    broker = Broker(binaries, base / 'immutable_budget')
    try:
        broker.exchange(ARM)
        # Client cannot renew even by one millisecond, nor use replay sequence.
        broker.deadline += 1
        try:
            broker.exchange(BEAT)
        except AssertionError as exc:
            assert 'guard rejected' in str(exc)
        else:
            raise AssertionError('absolute budget extended')
    finally:
        broker.close()
    wait_text(broker.directory / 'events', 'INERT_RESTORE_ONCE')
    checks += 1
    broker = Broker(binaries, base / 'partial_frame_deadline')
    try:
        broker.exchange(ARM)
        broker.socket.sendall(b'O')
        assert broker.socket.recv(1) == b'', 'partial frame kept capability indefinitely'
    finally:
        broker.close()
    wait_text(broker.directory / 'events', 'INERT_RESTORE_ONCE')
    checks += 1
    broker = Broker(binaries, base / 'replayed_writer')
    try:
        broker.exchange(ARM)
        broker.sequence = 0
        try:
            broker.exchange(BEAT)
        except AssertionError as exc:
            assert 'guard rejected' in str(exc)
        else:
            raise AssertionError('second/replayed heartbeat sequence admitted')
    finally:
        broker.close()
    wait_text(broker.directory / 'events', 'INERT_RESTORE_ONCE')
    checks += 1
    broker = Broker(binaries, base / 'actual_deadline')
    broker.deadline = native_now(binaries) + 1000
    try:
        broker.exchange(ARM)
        broker.exchange(TAKEOVER)
        # Actual monotonic expiry, no clock/lease extension or injected timer.
        wait_text(broker.directory / 'events', 'UNRESOLVED_FENCE_RETAINED', seconds=3)
        assert (broker.directory / 'fence').exists()
        assert not (broker.directory / 'restore.once').exists(), 'deadline with live execution is not safe restore'
    finally:
        broker.close()
    checks += 1
    # Only a directory fd and connected socket can bootstrap guard. No marker
    # or stdin payload can replace them; deployment binary denied above.
    invalid = subprocess.run([str(binaries['guard-test'])], input=b'READY role=root /tmp/run',
                             capture_output=True, timeout=3)
    assert invalid.returncode == 78
    checks += 1
    print('SCAN_OWNER_REAL_PROCESS_CASES_OK=' + str(checks))
    print('PROCESS_BOUNDARY=real-POSIX-owner-core-guard-exec-fs-IPC;injected-admission-and-inert-Trial-effects')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='openhc-lease-process-') as temp:
        output = args.output or Path(temp)
        output.mkdir(parents=True, exist_ok=True)
        binaries = compile_programs(output / 'bin')
        if os.name == 'nt':
            print('POSIX_PROCESS_RUNTIME_PENDING=Windows-cross-compile-only-no-Linux-or-Apple-runtime')
        else:
            runtime_checks(binaries, output)


if __name__ == '__main__':
    main()
