"""Synthetic protocol and recovery fault tests. No SSH, device or credentials."""
import importlib.util
import io
import pathlib
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('power_trial', ROOT / 'scripts/btstack-power-trial.py')
trial = importlib.util.module_from_spec(spec)
spec.loader.exec_module(trial)
BASH = shutil.which('bash') or 'C:/Program Files/Git/bin/bash.exe'


def event(state):
    return struct.pack('<HHHBBB', 4, 0, 3, 0x60, 1, state)


class Channel:
    def __init__(self, data):
        self.data = data
        self.sent = []

    def settimeout(self, value):
        pass

    def recv(self, size):
        # Every read is fragmented to exercise exact framing.
        result, self.data = self.data[:1], self.data[1:]
        return result

    def sendall(self, data):
        self.sent.append(data)

    def close(self):
        pass


class ProtocolTests(unittest.TestCase):
    def test_power_and_release(self):
        c = Channel(event(0) + event(1) + event(2) + event(3) + event(0))
        trial.PowerProtocol(c, lambda _: None).run()
        self.assertEqual(c.sent, [bytes.fromhex(x) for x in
            ('01000000030001f400', '01000000040002f40101', '01000000040002f40100')])

    def test_working_callback_runs_before_single_release(self):
        c = Channel(event(0) + event(1) + event(2) + event(3) + event(0))
        observed = []
        trial.PowerProtocol(c, lambda _: None).run(
            on_working=lambda: observed.append(len(c.sent)))
        self.assertEqual(observed, [2])
        self.assertEqual(len(c.sent), 3)


class FakeTransport:
    def __init__(self, channel):
        self.channel = channel

    def open_channel(self, *args, **kwargs):
        return self.channel


class FakeSSH:
    def __init__(self, channel):
        self.transport = FakeTransport(channel)

    def get_transport(self):
        return self.transport


class FakeRemoteChannel:
    def __init__(self, output=b'METADATA_ONLY\n', status=0, error=None, exit_ready=True):
        self.output = output
        self.status = status
        self.error = error
        self.exit_ready = exit_ready
        self.command = None

    def settimeout(self, _):
        pass

    def set_combine_stderr(self, _):
        pass

    def exec_command(self, command):
        self.command = command
        if self.error:
            raise self.error

    def recv_ready(self):
        if self.error:
            raise self.error
        return bool(self.output)

    def recv(self, size):
        result, self.output = self.output[:size], self.output[size:]
        return result

    def exit_status_ready(self):
        return self.exit_ready

    def recv_exit_status(self):
        return self.status

    def close(self):
        pass


class FakeCommandTransport(FakeTransport):
    def __init__(self, protocol_channel, remote_channel):
        super().__init__(protocol_channel)
        self.remote_channel = remote_channel

    def open_session(self, **_):
        return self.remote_channel


class IntegratedModeTests(unittest.TestCase):
    def make_trial(self, callback_result=None):
        channel = Channel(event(0) + event(1) + event(2) + event(3) + event(0))
        events = []
        t = trial.Trial(FakeSSH(channel), io.StringIO())
        t.preflight = lambda: events.append('PREFLIGHT')
        t.arm = lambda: events.append('GUARD_READY')
        t.takeover = lambda: events.append('TAKEOVER')
        t.restore = lambda: (events.append('RESTORE') or True)
        def run_transport():
            events.append('TRANSPORT')
            if callback_result:
                raise callback_result
            events.append('TRANSPORT_EXIT_CONFIRMED')
        t.run_inbound_transport = run_transport
        return t, channel, events

    def test_inbound_order_is_working_transport_exit_off_restore(self):
        t, channel, events = self.make_trial()
        self.assertEqual(t.run(mode='inbound'), 0)
        self.assertEqual(events, ['PREFLIGHT', 'GUARD_READY', 'TAKEOVER',
                                  'TRANSPORT', 'TRANSPORT_EXIT_CONFIRMED', 'RESTORE'])
        self.assertEqual(len(channel.sent), 3)
        self.assertEqual(channel.sent[-1], bytes.fromhex('01000000040002f40100'))

    def test_confirmed_transport_failures_release_then_restore_once(self):
        for failure in (RuntimeError('ACCEPT_FAILED'), RuntimeError('CLOSE_FAILED')):
            with self.subTest(failure=failure):
                t, channel, events = self.make_trial(failure)
                self.assertEqual(t.run(mode='inbound'), 1)
                self.assertEqual(events.count('RESTORE'), 1)
                self.assertEqual(channel.sent[-1], bytes.fromhex('01000000040002f40100'))

    def test_timeout_or_ssh_loss_yields_recovery_to_guard(self):
        for failure in (trial.LeaseUncertain('TIMEOUT'), trial.LeaseUncertain('SSH_LOSS')):
            with self.subTest(failure=failure):
                t, channel, events = self.make_trial(failure)
                self.assertEqual(t.run(mode='inbound'), 1)
                self.assertEqual(events.count('RESTORE'), 0)
                self.assertEqual(len(channel.sent), 2)
                self.assertTrue(t.guard_owns_recovery)

    def test_host_invocation_is_noop_without_execute(self):
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/btstack-power-trial.py')],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertIn('NO_DEVICE_ACTION', result.stdout)

    def test_real_inbound_command_uses_fixed_argv_and_bounded_metadata_output(self):
        remote = FakeRemoteChannel(output=b'INCOMING=1\nACCEPTED=1\n')
        t = trial.Trial(FakeSSH(Channel(b'')), io.StringIO())
        t.client = FakeSSH(Channel(b''))
        t.client.transport = FakeCommandTransport(Channel(b''), remote)
        t.state = trial.REMOTE_BASE + '/generated-run-id'
        t.run_inbound_transport()
        import shlex
        self.assertEqual(shlex.split(remote.command), [trial.TIMER, '-k', '2',
            str(trial.INBOUND_RUN_SECONDS), '/var/jb/usr/bin/openhc-bridge-check',
            '--btstack-control-inbound', t.state])
        self.assertIn('INCOMING=1', t.log.getvalue())

    def test_ssh_loss_timeout_and_cancel_are_unconfirmed(self):
        lost = FakeRemoteChannel(error=OSError('SSH_LOST'))
        t = trial.Trial(FakeSSH(Channel(b'')), io.StringIO())
        t.client.transport = FakeCommandTransport(Channel(b''), lost)
        with self.assertRaisesRegex(trial.LeaseUncertain, 'OSError'):
            t.run_inbound_transport()

        cancel = FakeRemoteChannel(error=KeyboardInterrupt())
        t.client.transport = FakeCommandTransport(Channel(b''), cancel)
        with self.assertRaisesRegex(trial.LeaseUncertain, 'KeyboardInterrupt'):
            t.run_inbound_transport()

        hung = FakeRemoteChannel(output=b'', exit_ready=False)
        t.client.transport = FakeCommandTransport(Channel(b''), hung)
        ticks = iter(range(100))
        with mock.patch.object(trial.time, 'monotonic', side_effect=lambda: next(ticks)), \
             mock.patch.object(trial.time, 'sleep'):
            with self.assertRaisesRegex(trial.LeaseUncertain, 'TIMEOUT'):
                t.run_inbound_transport()

    def test_working_callback_failure_still_releases_once(self):
        c = Channel(event(0) + event(1) + event(2) + event(3) + event(0))
        with self.assertRaisesRegex(RuntimeError, 'CALLBACK_FAIL'):
            trial.PowerProtocol(c, lambda _: None).run(
                on_working=lambda: (_ for _ in ()).throw(RuntimeError('CALLBACK_FAIL')))
        self.assertEqual(c.sent[-1], bytes.fromhex('01000000040002f40100'))
        self.assertEqual(len(c.sent), 3)

    def test_failure_still_releases(self):
        c = Channel(event(0) + struct.pack('<HHHBB', 4, 0, 2, 0x62, 0) + event(0))
        with self.assertRaisesRegex(RuntimeError, 'POWERON_FAILED'):
            trial.PowerProtocol(c, lambda _: None).run()
        self.assertEqual(c.sent[-1], bytes.fromhex('01000000040002f40100'))

    def test_rejects_unexpected_frames(self):
        for data, error in [
            (struct.pack('<HHH', 4, 0, 1025), 'OVERSIZE'),
            (struct.pack('<HHHBBB', 4, 1, 3, 0x60, 1, 2), 'SHAPE'),
            (struct.pack('<HHHBBB', 4, 0, 3, 0x60, 2, 2), 'SHAPE'),
            (struct.pack('<HHHBBB', 4, 0, 3, 0x60, 1, 5), 'SHAPE'),
            (struct.pack('<HHHBB', 4, 0, 2, 0x17, 0), 'PEER_SECURITY'),
            (b'', 'EOF')]:
            with self.subTest(error=error), self.assertRaisesRegex(RuntimeError, error):
                trial.PowerProtocol(Channel(data)).state(time.monotonic() + 1)

    def test_only_power_commands_allowed(self):
        for opcode, value in [(3, None), (2, 2), (1, 1)]:
            with self.assertRaises(ValueError):
                trial.PowerProtocol(Channel(b'')).command(opcode, value)

    def test_flood_bounded(self):
        c = Channel(struct.pack('<HHHBB', 4, 0, 2, 0x61, 0) * 513)
        with self.assertRaisesRegex(RuntimeError, 'EVENT_LIMIT'):
            trial.PowerProtocol(c).state(time.monotonic() + 2)


MOCK = r'''#!/bin/sh
dir=$(dirname "$0")
kind=$(basename "$0" .sh)
case "$kind" in
timer) shift 3; exec "$@" ;;
clock) cat "$dir/now" ;;
sleeper) n=$(cat "$dir/now"); echo $((n + 1)) > "$dir/now" ;;
ps)
    [ ! -f "$dir/ps-fail" ] || exit 1
    if [ -f "$dir/stack-process" ]; then
        if [ -f "$dir/bare-name" ]; then echo ' 10 1 S BTdaemon';
        else echo ' 10 1 S /var/jb/usr/bin/BTdaemon'; fi
    fi
    [ ! -f "$dir/apple-process" ] || echo ' 20 1 S /usr/sbin/bluetoothd'
    ;;
ctl)
    verb=$1; target=${2##*/}; target=${target%.plist}
    if [ "$verb" = print ]; then
        [ ! -f "$dir/print-fail" ] || exit 1
        [ -f "$dir/$target" ] && exit 0
        exit 113
    fi
    echo "$verb $target" >> "$dir/actions"
    case "$verb:$target" in
    unload:ch.ringwald.BTstack)
        [ ! -f "$dir/stack-stuck" ] && [ ! -f "$dir/bare-name" ] || exit 1
        rm -f "$dir/ch.ringwald.BTstack" "$dir/stack-process" ;;
    load:com.apple.BlueTool) touch "$dir/com.apple.BlueTool" ;;
    load:com.apple.bluetoothd)
        [ ! -f "$dir/apple-fail" ] || exit 1
        touch "$dir/com.apple.bluetoothd" "$dir/apple-process" ;;
    load:ch.ringwald.BTstack) touch "$dir/ch.ringwald.BTstack" ;;
    *) exit 1 ;;
    esac ;;
*) exit 1 ;;
esac
'''


class GuardTests(unittest.TestCase):
    def run_guard(self, trigger='request', fault=None):
        with tempfile.TemporaryDirectory(prefix='oh-power-') as temp:
            d = pathlib.Path(temp)
            guard = d / 'guard.sh'
            guard.write_text((ROOT / 'scripts/btstack-power-recovery.sh').read_text(),
                             encoding='utf-8', newline='\n')
            for kind in ('timer', 'clock', 'sleeper', 'ps', 'ctl'):
                (d / (kind + '.sh')).write_text(MOCK, encoding='utf-8', newline='\n')
            for f in ('ch.ringwald.BTstack', 'stack-process', 'com.apple.BTServer.le'):
                (d / f).touch()
            (d / 'now').write_text('100\n', newline='\n')
            (d / 'deadline').write_text(('103' if trigger == 'deadline' else '220') + '\n', newline='\n')
            (d / 'heartbeat').write_text(('0' if trigger == 'heartbeat' else '100') + '\n', newline='\n')
            if trigger == 'request':
                (d / 'restore-request').touch()
            if fault:
                (d / fault).touch()
            args = [str(BASH), guard.as_posix(),
                    d.as_posix(), *[(d / (k + '.sh')).as_posix() for k in
                    ('ctl', 'timer', 'ps', 'clock', 'sleeper')],
                    'ch.ringwald.BTstack.plist', 'com.apple.BlueTool.plist',
                    'com.apple.bluetoothd.plist', (d / 'unused-socket').as_posix()]
            p = subprocess.run(args, capture_output=True, text=True, timeout=25)
            self.assertTrue((d / 'result').exists(), p.stdout + p.stderr)
            actions = (d / 'actions').read_text() if (d / 'actions').exists() else ''
            result = (d / 'result').read_text().strip()
            self.assertTrue((d / 'ready').exists(), p.stderr)
            self.assertTrue((d / 'restoring').exists(), p.stderr)
            if not fault:
                self.assertEqual(p.returncode, 0, p.stderr + p.stdout)
                self.assertEqual(result, 'RESTORED')
                self.assertEqual(actions.splitlines(), ['unload ch.ringwald.BTstack',
                    'load com.apple.BlueTool', 'load com.apple.bluetoothd', 'load ch.ringwald.BTstack'])
                # launchd restart after successful recovery is a no-op.
                subprocess.run(args, check=True, capture_output=True, timeout=5)
                self.assertEqual((d / 'actions').read_text(), actions)
            else:
                self.assertNotEqual(p.returncode, 0)
                self.assertEqual(result, 'FAILED')
                self.assertNotIn('load ch.ringwald.BTstack', actions.splitlines())
                if fault in ('stack-stuck', 'bare-name', 'ps-fail', 'print-fail'):
                    self.assertNotIn('load com.apple.BlueTool', actions)
            return p.stdout

    def test_request(self):
        self.assertIn('TRIGGER_REQUEST', self.run_guard())

    def test_deadline(self):
        self.assertIn('TRIGGER_DEADLINE', self.run_guard('deadline'))

    def test_host_disappears(self):
        self.assertIn('TRIGGER_HEARTBEAT', self.run_guard('heartbeat'))

    def test_restore_failures(self):
        for fault in ('stack-stuck', 'bare-name', 'ps-fail', 'print-fail', 'apple-fail'):
            with self.subTest(fault=fault):
                self.run_guard(fault=fault)


class DriverTests(unittest.TestCase):
    def test_shared_executable_without_current_evidence_is_blocked(self):
        for name in ('CarPlay Simulator', 'CarPlay Simulato', 'carplay_services'):
            with self.subTest(name=name):
                t = trial.Trial(None, io.StringIO())
                t.execute = lambda *a, **k: (0, '')
                t.service = lambda label: None if label in (trial.LABEL, 'com.reng.showcase.bluetooth-recovery') else 'registered'
                t.processes = lambda: ['10 1 S /usr/sbin/bluetoothd', '27078 1 S ' + name]
                with self.assertRaisesRegex(RuntimeError, '^SESSION_METADATA_UNKNOWN=FRESH_EVIDENCE_REQUIRED'):
                    t.preflight()

    def test_shared_helper_requires_matching_fresh_broker_metadata(self):
        evidence = {'captured_at_epoch': time.time(), 'snapshot_complete': True,
                    'shared_helper_pids': [27078], 'broker_owner_pid': 27078,
                    'broker_comm_pid': 27078, 'active_session_pids': [],
                    'recovery_active': False, 'ownership_marker': False}
        t = trial.Trial(FakeSSH(Channel(event(0))), io.StringIO())
        t.session_evidence = evidence
        t.execute = lambda *a, **k: (0, '')
        t.service = lambda label: None if label in (trial.LABEL, 'com.reng.showcase.bluetooth-recovery') else 'registered'
        t.processes = lambda: ['10 1 S /usr/sbin/bluetoothd',
                               '27078 1 S CarPlay Simulator']
        t.preflight()
        self.assertIn('SESSION_METADATA_CLASSIFICATION=BROKER', t.log.getvalue())

    def test_shared_helper_unknown_session_metadata_blocks(self):
        evidence = {'captured_at_epoch': time.time(), 'snapshot_complete': True,
                    'shared_helper_pids': [27078], 'active_session_pids': [],
                    'recovery_active': False, 'ownership_marker': False}
        t = trial.Trial(FakeSSH(Channel(event(0))), io.StringIO())
        t.session_evidence = evidence
        t.execute = lambda *a, **k: (0, '')
        t.service = lambda label: None if label in (trial.LABEL, 'com.reng.showcase.bluetooth-recovery') else 'registered'
        t.processes = lambda: ['10 1 S /usr/sbin/bluetoothd',
                               '27078 1 S CarPlay Simulator']
        with self.assertRaisesRegex(RuntimeError, '^SESSION_METADATA_BLOCKED=UNKNOWN'):
            t.preflight()

    def test_bare_helper_with_spaces_and_absolute_path(self):
        for comm in ('CarPlay Simulator', '/var/jb/usr/bin/CarPlay Simulator'):
            self.assertTrue(trial.Trial.named(['27078 1 S ' + comm], 'CarPlay Simulator'))
        self.assertFalse(trial.Trial.named(['27078 1 S OtherCarPlay Simulator'], 'CarPlay Simulator'))

    def test_failed_readiness_never_takes_over(self):
        t = trial.Trial(None, io.StringIO())
        t.preflight = lambda: None
        def fail():
            raise RuntimeError('RECOVERY_READY_TIMEOUT')
        t.arm = fail
        t.takeover = lambda: self.fail('takeover without ready handshake')
        self.assertEqual(t.run(), 1)

    def test_unload_failure_stops_before_btstack_restart(self):
        t = trial.Trial(None, io.StringIO())
        t.assert_guard = lambda: None
        calls = []
        def control(verb, target):
            calls.append((verb, target))
            raise RuntimeError('UNLOAD_FAILED')
        t.control = control
        with self.assertRaisesRegex(RuntimeError, 'UNLOAD_FAILED'):
            t.takeover()
        self.assertEqual(calls, [('unload', trial.BLUETOOTHD)])

    def test_guard_already_restoring_blocks_takeover(self):
        t = trial.Trial(None, io.StringIO())
        t.execute = lambda *a, **k: (0, 'RESTORING\n')
        with self.assertRaisesRegex(RuntimeError, 'GUARD_ALREADY'):
            t.assert_guard()


if __name__ == '__main__':
    unittest.main(verbosity=2)
