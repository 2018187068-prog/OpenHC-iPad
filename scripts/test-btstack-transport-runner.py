"""Synthetic session-plan and runner lifecycle tests; no device or radio."""
import importlib.util
from pathlib import Path
import time
import unittest

spec = importlib.util.spec_from_file_location('runner', Path(__file__).with_name('btstack-transport-runner.py'))
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def phone_initiated_plan(control_channel=8, auth_channel=19, auth_uuid=None):
    return runner.validate_plan((
        runner.control_plan('phone-initiated', control_channel),
        runner.auth_plan('phone-requested-subchannel', auth_channel, auth_uuid or runner.DEFAULT_AUTH_UUID),
    ))


class Adapter:
    def __init__(self, fail=None, mismatch=False, slow_open=False):
        self.fail = fail
        self.mismatch = mismatch
        self.slow_open = slow_open
        self.calls = []
        self.next_id = 0

    def open(self, plan, deadline):
        self.calls.append(('open', plan.name, plan.channel, plan.local_action, plan.source))
        if self.slow_open:
            time.sleep(1.01)
        if self.fail == 'open' and plan.name == 'auth':
            raise RuntimeError('MOCK_OPEN')
        self.next_id += 1
        return self.next_id

    def exchange(self, handle, payload, _deadline):
        self.calls.append(('exchange', handle))
        if self.fail == 'exchange' and handle == 2:
            raise RuntimeError('MOCK_EXCHANGE')
        return b'wrong' if self.mismatch and handle == 2 else payload

    def close(self, handle, _deadline):
        self.calls.append(('close', handle))
        if self.fail == 'close' and handle == 1:
            raise RuntimeError('MOCK_CLOSE')

    def release_power(self, _deadline):
        self.calls.append(('release_power',))
        if self.fail == 'release_power':
            raise RuntimeError('MOCK_RELEASE')


class RunnerTests(unittest.TestCase):
    def test_role_sources_follow_openhc_flows_not_sdp_direction(self):
        normal = phone_initiated_plan()
        self.assertEqual([(p.local_action, p.channel_owner, p.source) for p in normal], [
            ('listen', 'local', 'local-listen-result'),
            ('listen', 'local', 'control-socket-request'),
        ])
        reconnect = runner.validate_plan((
            runner.control_plan('vehicle-reconnect', 7),
            runner.auth_plan('vehicle-reconnect-response', 19, 'f3641400-00b0-4240-ba50-05ca45bf8abc'),
        ))
        self.assertEqual([(p.local_action, p.channel_owner, p.source) for p in reconnect], [
            ('connect', 'peer', 'sdp-result'),
            ('connect', 'peer', 'control-auth-channel-ready'),
        ])

    def test_local_listener_conflicts_only_in_same_local_namespace(self):
        with self.assertRaisesRegex(ValueError, 'LOCAL_LISTENER_CHANNEL_COLLISION'):
            phone_initiated_plan(control_channel=8, auth_channel=8)
        same_number_other_peer_is_valid = runner.validate_plan((
            runner.control_plan('phone-initiated', 8),
            runner.auth_plan('vehicle-reconnect-response', 8),
        ))
        self.assertEqual([p.channel for p in same_number_other_peer_is_valid], [8, 8])

    def test_peer_negotiated_uuid_is_used_without_auth_payload(self):
        uuid = 'f3641400-00b0-4240-ba50-05ca45bf8abc'
        self.assertEqual(phone_initiated_plan(auth_uuid=uuid)[1].uuid, uuid)

    def test_success_close_reopen_and_repeated_run(self):
        adapter = Adapter()
        output = []
        runner_instance = runner.SyntheticTransportRunner(adapter, phone_initiated_plan())
        self.assertTrue(runner_instance.run(output.append))
        self.assertTrue(runner_instance.run(output.append))
        self.assertEqual(adapter.calls.count(('open', 'control', 8, 'listen', 'local-listen-result')), 2)
        self.assertEqual(adapter.calls.count(('close', 1)), 1)
        self.assertEqual(adapter.calls.count(('close', 3)), 1)
        self.assertEqual(adapter.calls.count(('release_power',)), 2)
        self.assertEqual(output.count('TRANSPORT_CHANNEL_CLOSED=control'), 2)

    def test_partial_open_and_io_failure_still_cleanup(self):
        adapter = Adapter(fail='open')
        with self.assertRaisesRegex(RuntimeError, 'MOCK_OPEN'):
            runner.SyntheticTransportRunner(adapter, phone_initiated_plan()).run()
        self.assertIn(('close', 1), adapter.calls)
        self.assertEqual(adapter.calls[-1], ('release_power',))
        adapter = Adapter(fail='exchange')
        with self.assertRaisesRegex(RuntimeError, 'MOCK_EXCHANGE'):
            runner.SyntheticTransportRunner(adapter, phone_initiated_plan()).run()
        self.assertEqual(adapter.calls[-3:], [('close', 2), ('close', 1), ('release_power',)])

    def test_mismatch_or_cleanup_failure_is_not_pass(self):
        with self.assertRaisesRegex(RuntimeError, 'MISMATCH'):
            runner.SyntheticTransportRunner(Adapter(mismatch=True), phone_initiated_plan()).run()
        for fault in ('close', 'release_power'):
            with self.subTest(fault=fault), self.assertRaisesRegex(RuntimeError, 'FAILED'):
                runner.SyntheticTransportRunner(Adapter(fail=fault), phone_initiated_plan()).run()

    def test_overall_deadline_is_enforced_and_cleanup_runs(self):
        adapter = Adapter(slow_open=True)
        with self.assertRaisesRegex(TimeoutError, 'TRANSPORT_DEADLINE'):
            runner.SyntheticTransportRunner(adapter, phone_initiated_plan(), deadline_seconds=1).run()
        self.assertEqual(adapter.calls[-1], ('release_power',))


if __name__ == '__main__':
    unittest.main(verbosity=2)
