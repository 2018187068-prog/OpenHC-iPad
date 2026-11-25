import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('gate', Path(__file__).with_name('btstack-session-gate.py'))
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class SessionGateTests(unittest.TestCase):
    def test_confirmed_broker_is_distinct_from_activity(self):
        self.assertEqual(gate.classify(snapshot_complete=True, broker_owner_pid=27078,
            broker_comm_pid=27078, shared_helper_pids=(27078,), ownership_marker=False), 'BROKER')
        self.assertEqual(gate.classify(snapshot_complete=True, broker_owner_pid=27078,
            broker_comm_pid=27078, shared_helper_pids=(27078,)), 'UNKNOWN')
        self.assertEqual(gate.classify(snapshot_complete=True, broker_owner_pid=27078,
            broker_comm_pid=27078, shared_helper_pids=(27078,), active_session_pids=(91,),
            ownership_marker=False), 'ACTIVE_SESSION')

    def test_positive_active_signal_wins_but_marker_alone_is_unknown(self):
        self.assertEqual(gate.classify(snapshot_complete=True, active_session_pids=(91,),
            ownership_marker=False), 'ACTIVE_SESSION')
        self.assertEqual(gate.classify(snapshot_complete=True, ownership_marker=True), 'UNKNOWN')

    def test_missing_or_conflicting_metadata_is_unknown(self):
        cases = (
            dict(snapshot_complete=False, ownership_marker=False),
            dict(snapshot_complete=True, shared_helper_pids=(27078,), ownership_marker=False),
            dict(snapshot_complete=True, broker_owner_pid=27078, broker_comm_pid=11,
                 ownership_marker=False),
            dict(snapshot_complete=True, recovery_active=True, ownership_marker=False),
            dict(snapshot_complete=True),
        )
        for evidence in cases:
            with self.subTest(evidence=evidence):
                self.assertEqual(gate.classify(**evidence), 'UNKNOWN')

    def test_extra_unexplained_shared_helper_prevents_broker_classification(self):
        self.assertEqual(gate.classify(snapshot_complete=True, broker_owner_pid=27078,
            broker_comm_pid=27078, shared_helper_pids=(27078, 991), ownership_marker=False), 'UNKNOWN')

    def test_clear_is_only_a_bounded_snapshot_result(self):
        self.assertEqual(gate.classify(snapshot_complete=True, ownership_marker=False), 'CLEAR_SNAPSHOT')


if __name__ == '__main__':
    unittest.main(verbosity=2)
