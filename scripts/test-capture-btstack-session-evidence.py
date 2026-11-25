import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location(
    'capture_evidence', Path(__file__).with_name('capture-btstack-session-evidence.py'))
capture_evidence = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture_evidence)


def fixture(start='100', end='101', owner='5', comm='CarPlay Simulator',
            owner_rc='0', ps_rc='0', guard_rc='113', marker='0'):
    return f'''CAPTURE_BEGIN={start}
OWNER_RC={owner_rc}
SESSION_SOCKET_OWNER_PID={owner}
SESSION_SOCKET_APPLICATION_BYTES=0
SESSION_SOCKET_OWNER_QUERY_OK
PROCESS_RC={ps_rc}
PROCESS_BEGIN
  1 0 S /sbin/launchd
  {owner} 1 S {comm}
PROCESS_END
MARKER={marker}
GUARD_RC={guard_rc}
CAPTURE_END={end}
'''


class CaptureTests(unittest.TestCase):
    def test_fresh_broker_owner_is_current_process_snapshot(self):
        result = capture_evidence.parse_capture(fixture())
        self.assertTrue(result['snapshot_complete'])
        self.assertEqual(result['broker_owner_pid'], 5)
        self.assertEqual(result['broker_comm_pid'], 5)
        self.assertEqual(result['shared_helper_pids'], [5])
        self.assertFalse(result['ownership_marker'])
        self.assertFalse(result['recovery_active'])
        self.assertEqual(result['capture_window_seconds'], 1)
        self.assertEqual(result['active_session_pids'], [])

    def test_other_helper_and_live_guard_are_preserved_as_metadata(self):
        raw = fixture(guard_rc='0').replace('PROCESS_END', '  8 1 S CarPlay Simulato\nPROCESS_END')
        result = capture_evidence.parse_capture(raw)
        self.assertEqual(result['shared_helper_pids'], [5, 8])
        self.assertTrue(result['recovery_active'])

    def test_missing_owner_failed_command_and_wide_window_stay_unknown(self):
        for raw in (
            fixture(owner_rc='1'),
            fixture(end='106'),
            fixture().replace('SESSION_SOCKET_OWNER_PID=5\n', ''),
            fixture(guard_rc='1'),
        ):
            with self.subTest(raw=raw):
                self.assertFalse(capture_evidence.parse_capture(raw)['snapshot_complete'])

    def test_remote_command_is_fixed_and_owner_probe_has_zero_application_bytes(self):
        command = capture_evidence.REMOTE_COMMAND
        self.assertIn('openhc-bridge-check --session-owner', command)
        self.assertIn('ps -axo pid,ppid,state,comm', command)
        self.assertIn('SESSION_SOCKET_APPLICATION_BYTES=0', fixture())
        for forbidden in ('send(', 'recv(', 'BTstack power', 'kill '):
            self.assertNotIn(forbidden, command)


if __name__ == '__main__':
    unittest.main()
