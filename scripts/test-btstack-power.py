"""Synthetic protocol and recovery fault tests. No SSH, device or credentials."""
import importlib.util
import io
import pathlib
import struct
import subprocess
import tempfile
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('power_trial', ROOT / 'scripts/btstack-power-trial.py')
trial = importlib.util.module_from_spec(spec)
spec.loader.exec_module(trial)
BASH = pathlib.Path('C:/Program Files/Git/bin/bash.exe')


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


class ProtocolTests(unittest.TestCase):
    def test_power_and_release(self):
        c = Channel(event(0) + event(1) + event(2) + event(3) + event(0))
        trial.PowerProtocol(c, lambda _: None).run()
        self.assertEqual(c.sent, [bytes.fromhex(x) for x in
            ('01000000030001f400', '01000000040002f40101', '01000000040002f40100')])

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
    def test_shared_executable_is_unverified_role_not_proven_competition(self):
        for name in ('CarPlay Simulator', 'CarPlay Simulato', 'carplay_services'):
            with self.subTest(name=name):
                t = trial.Trial(None, io.StringIO())
                t.execute = lambda *a, **k: (0, '')
                t.service = lambda label: None if label == trial.LABEL else 'registered'
                t.processes = lambda: ['10 1 S /usr/sbin/bluetoothd', '27078 1 S ' + name]
                with self.assertRaisesRegex(RuntimeError, '^SHARED_HELPER_ROLE_UNVERIFIED='):
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
