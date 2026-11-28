"""Injected process-state regressions plus real host loopback; no Apple pass claim."""
import importlib.util
import contextlib
import errno
import io
import json
from pathlib import Path
import socket
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
import threading
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('sim', Path(__file__).with_name('test-fe35-cli-inbound-simulator.py'))
sim = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sim)
cid_spec = importlib.util.spec_from_file_location('cid', Path(__file__).with_name('test-fe36-cid-simulator.py'))
cid = importlib.util.module_from_spec(cid_spec)
cid_spec.loader.exec_module(cid)


class Socket:
    def setsockopt(self, *_): pass
    def bind(self, _): pass
    def listen(self, _): pass
    def settimeout(self, _): pass
    def getsockname(self): return ('127.0.0.1', 12345)
    def close(self): pass
    def shutdown(self, _): pass


class Thread:
    def __init__(self, **_): pass
    def start(self): pass
    def is_alive(self): return False
    def join(self, _): pass


class EvidenceTests(unittest.TestCase):
    def inbound_failure(self, timeout=False, result=False, status=1, states=('exited',),
                        stdout='synthetic: 12345', alive=False, expect_success=False, through_main=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            documents = root / 'Documents'
            documents.mkdir()
            (documents / 'fe35-cli-status.log').write_text('previous-case-must-not-be-attributed')
            (documents / 'fe35-cli-result').write_text('0')
            args = SimpleNamespace(data_dir=str(root), udid='synthetic', bundle_id='synthetic')
            launches = []
            def launch(*_, **__):
                launches.append(True)
                if result:
                    (documents / 'fe35-cli-result').write_text(str(status))
                if timeout:
                    raise subprocess.TimeoutExpired('secret-command', 30,
                        output=b'synthetic: 12345', stderr=b'secret PIN key credentials')
                return subprocess.CompletedProcess([], 0, stdout, 'secret PIN key credentials')
            # Deterministic injected process states and monotonic clock; no
            # model of Apple launch behavior is claimed by this regression.
            clock = [0.0]
            observed = []
            sequence = iter(states)
            def observe(_):
                value = next(sequence, states[-1])
                observed.append(value)
                if isinstance(value, Exception): raise value
                return value
            def sleep(seconds): clock[0] += seconds
            joins = []
            closed = []
            class OwnedSocket(Socket):
                def close(self): closed.append(True)
            class PeerThread(Thread):
                def is_alive(self): return alive
                def join(self, seconds): joins.append(seconds)
            with patch.object(sim, 'ROOT', root), \
                 patch.object(sim.threading, 'Thread', PeerThread), patch.object(sim.subprocess, 'run', side_effect=launch), \
                 patch.object(sim.time, 'sleep', side_effect=sleep), patch.object(sim.time, 'monotonic', side_effect=lambda: clock[0]), \
                 patch.object(sim, 'fixture_process_state', side_effect=observe), \
                 patch.object(sim.socket, 'socket', return_value=OwnedSocket()), \
                 patch.object(sim.argparse.ArgumentParser, 'parse_args', return_value=args), \
                 patch.object(sim, 'run_scan_case') as later:
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    if expect_success:
                        sim.run_case(args, 'incoming_timeout')
                    else:
                        with self.assertRaises(subprocess.TimeoutExpired if timeout else AssertionError):
                            if through_main:
                                sim.main()
                            else:
                                sim.run_case(args, 'incoming_timeout')
                        self.assertNotIn('CASE_OK', output.getvalue())
                        self.assertNotIn('FE35_KN_INBOUND_ASSERTIONS', output.getvalue())
                    later.assert_not_called()
            self.assertEqual(len(launches), 1)
            case = 'success' if through_main else 'incoming_timeout'
            evidence = root / ('artifacts/scan-owner/simulator-cases/fe35-' + case)
            raw = (evidence / 'launch-evidence.json').read_text()
            data = json.loads(raw)
            self.assertTrue(data['stale_files_removed']['status'])
            self.assertFalse(data['status_present'])
            self.assertFalse((evidence / 'fe35-cli-status.log').exists())
            self.assertEqual(data['thread_stopped'], not alive)
            self.assertNotIn('secret', raw)
            self.assertNotIn('credentials', raw)
            self.assertTrue(closed)
            self.assertTrue(all(0 <= seconds <= 8 for seconds in joins))
            data['test_clock_elapsed'] = clock[0]
            data['test_observations'] = observed
            return data

    def test_inbound_timeout_persists_partial_launch_and_unproven_exit(self):
        data = self.inbound_failure(timeout=True, states=('present',))
        self.assertEqual(data['failure'], 'launch-timeout')
        self.assertEqual(data['launch']['pid'], 12345)
        self.assertEqual(data['outcome'], 'failed')

    def test_inbound_missing_result_preserves_failed_evidence(self):
        self.assertEqual(self.inbound_failure()['failure'], 'assertion')

    def test_inbound_wrong_result_still_fails(self):
        self.assertEqual(self.inbound_failure(result=True, status=0)['outcome'], 'failed')

    def test_result_is_not_a_process_exit_certificate(self):
        data = self.inbound_failure(result=True, states=('present',))
        self.assertEqual(data['outcome'], 'failed')
        self.assertEqual(data['process_state'], 'present')
        self.assertFalse(data['isolation']['safe'])
        self.assertLessEqual(data['test_clock_elapsed'], 8.000001)

    def test_live_then_exited_within_same_join_budget(self):
        data = self.inbound_failure(result=True, states=('present', 'exited'), expect_success=True)
        self.assertEqual(data['outcome'], 'passed')
        self.assertTrue(data['isolation']['safe'])
        self.assertEqual(data['test_observations'][0], 'present')
        self.assertEqual(data['process_state'], 'exited')

    def test_missing_exact_pid_fails_closed(self):
        data = self.inbound_failure(result=True, stdout='unrecognized output')
        self.assertEqual(data['process_state'], 'unproven')
        self.assertFalse(data['isolation']['safe'])

    def test_permission_observation_failure_stops(self):
        data = self.inbound_failure(result=True, states=('observation-failed',))
        self.assertFalse(data['isolation']['safe'])

    def test_unexpected_observation_exception_stops(self):
        data = self.inbound_failure(result=True, states=(RuntimeError('secret'),))
        self.assertEqual(data['process_state'], 'observation-failed')
        self.assertFalse(data['isolation']['safe'])

    def test_pid_reappearing_after_exit_fails_conservatively(self):
        data = self.inbound_failure(result=True, states=('exited', 'present'))
        self.assertFalse(data['isolation']['safe'])

    def test_thread_still_live_fails_closed(self):
        data = self.inbound_failure(result=True, alive=True)
        self.assertFalse(data['isolation']['safe'])

    def test_actual_main_aborts_next_launch_when_pid_never_exits(self):
        data = self.inbound_failure(result=True, states=('present',), through_main=True)
        self.assertFalse(data['isolation']['safe'])

    def test_fixed_launch_shapes_and_redaction(self):
        data = sim.safe_launch_metadata('secret: 99', 'Request denied secret', 'synthetic')
        self.assertIsNone(data['pid'])
        self.assertEqual(data['stderr_label'], 'Request denied')
        self.assertNotIn('secret', json.dumps(data))
        self.assertIsNone(sim.safe_launch_metadata('synthetic: 1', '', 'synthetic')['pid'])
        self.assertEqual(sim.safe_launch_metadata(None, None, 'synthetic')['stdout_shape'], 'empty')

    def test_process_observation_is_conservative(self):
        with patch.object(sim.sys, 'platform', 'darwin'), patch.object(sim.os, 'kill') as kill:
            self.assertEqual(sim.fixture_process_state(12345), 'present')
            kill.assert_called_once_with(12345, 0)
            kill.side_effect = OSError(errno.ESRCH, 'secret')
            self.assertEqual(sim.fixture_process_state(12345), 'exited')
            kill.side_effect = OSError(errno.EPERM, 'secret')
            self.assertEqual(sim.fixture_process_state(12345), 'observation-failed')
        self.assertEqual(sim.fixture_process_state(None), 'unproven')

    def loopback_launch_timeout(self, write_failure=None, run_main=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = SimpleNamespace(data_dir=str(root), udid='synthetic', bundle_id='synthetic')
            accepted = threading.Event()
            peers = []
            threads = []
            launches = []
            real_thread = threading.Thread
            write_text = Path.write_text
            def thread_factory(**kwargs):
                value = real_thread(**kwargs)
                threads.append(value)
                return value
            def write(path, *args, **kwargs):
                if path.name == write_failure:
                    raise OSError('injected evidence disk failure')
                return write_text(path, *args, **kwargs)
            def blocked_peer(conn, *_):
                accepted.set()
                conn.recv(1)
            def launch(argv, **_):
                launches.append(argv)
                peers.append(socket.create_connection(('127.0.0.1', int(argv[-2].split(':')[1])), timeout=2))
                self.assertTrue(accepted.wait(2))
                raise subprocess.TimeoutExpired('redacted', 30)
            try:
                with patch.object(sim, 'ROOT', root), patch.object(sim, 'drive_peer', side_effect=blocked_peer), \
                     patch.object(sim.subprocess, 'run', side_effect=launch), \
                     patch.object(sim.threading, 'Thread', side_effect=thread_factory), \
                     patch.object(Path, 'write_text', write), \
                     patch.object(sim.argparse.ArgumentParser, 'parse_args', return_value=args), \
                     patch.object(sim, 'run_scan_case') as later:
                    output = io.StringIO()
                    with contextlib.redirect_stdout(output):
                        with self.assertRaises(OSError if write_failure else subprocess.TimeoutExpired):
                            if run_main:
                                sim.main()
                            else:
                                sim.run_case(args, 'incoming_timeout')
                    later.assert_not_called()
                    self.assertNotIn('CASE_OK', output.getvalue())
                    self.assertNotIn('FE35_KN_INBOUND_ASSERTIONS', output.getvalue())
                self.assertEqual(len(launches), 1)
                self.assertTrue(threads and all(not thread.is_alive() for thread in threads))
                if not write_failure:
                    case = 'success' if run_main else 'incoming_timeout'
                    data = json.loads((root / ('artifacts/scan-owner/simulator-cases/fe35-' + case) / 'launch-evidence.json').read_text())
                    self.assertTrue(data['thread_stopped'])
                    self.assertFalse(data['isolation']['safe'])
                    self.assertEqual(data['process_state'], 'unproven')
                self.assertEqual(peers[0].recv(1), b'')
            finally:
                for peer in peers: peer.close()

    def test_launch_timeout_closes_actual_accepted_socket_and_thread(self):
        self.loopback_launch_timeout()

    def test_before_close_evidence_failure_cannot_bypass_socket_thread_cleanup(self):
        self.loopback_launch_timeout(write_failure='launch-evidence-before-close.json')

    def test_after_close_evidence_failure_remains_nonzero_and_cleaned(self):
        self.loopback_launch_timeout(write_failure='launch-evidence.json')

    def test_actual_main_aborts_remaining_cases_on_launch_timeout(self):
        self.loopback_launch_timeout(run_main=True)

    def cid_failure(self, exception):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = SimpleNamespace(data_dir=str(root), udid='synthetic', bundle_id='synthetic')
            def launch(*_, **__):
                guard = root / 'Documents/auth-cid-wrong_pin'
                (guard / 'scan-events').write_text('CID_PHONE_EXCEPTION name=AuthFixture reason=static-assertion\n')
                if exception:
                    raise subprocess.TimeoutExpired('synthetic', 30)
                return subprocess.CompletedProcess([], 1)
            with patch.object(sim, 'ROOT', root), patch.object(cid.socket, 'socket', return_value=Socket()), \
                 patch.object(cid.threading, 'Thread', Thread), patch.object(cid.subprocess, 'run', side_effect=launch):
                with self.assertRaises(cid.UnsafeCaseFailure):
                    cid.run_case(args, sim, 'wrong_pin')
            evidence = root / 'artifacts/scan-owner/simulator-cases/fe36-cid-wrong_pin'
            self.assertIn('AuthFixture', (evidence / 'scan-events').read_text())
            # Injected Thread never starts: the finally flush must still persist
            # the empty in-memory observation, rather than invent peer progress.
            self.assertEqual((evidence / 'proxy-phases.log').read_text(), '\n')
            self.assertEqual((evidence / 'proxy-timing.log').read_text(), '\n')

    def test_cid_launch_failure(self): self.cid_failure(False)
    def test_cid_launch_exception(self): self.cid_failure(True)

    def check_failure(self, process, launch_failure):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            documents = root / 'Documents'
            args = SimpleNamespace(data_dir=str(root), udid='synthetic', bundle_id='synthetic')
            label = ('owner-process-' if process else 'scan-') + 'ready_stop'

            class Broker:
                def __init__(self, binaries, path, listener):
                    self.directory = path
                    path.mkdir(parents=True)
                    self.log = open(path / 'broker.log', 'w')
                    self.process = SimpleNamespace(poll=lambda: 0)
                def close(self): self.log.close()

            def launch(*_, **__):
                guard = documents / label.replace('scan-', 'scan-guard-')
                (guard / 'scan-events').write_text('OWNER_ASSERT_FAIL=synthetic-timeout\n')
                (documents / 'fe35-cli-status.log').write_text('synthetic lease phase\n')
                return subprocess.CompletedProcess([], 1 if launch_failure else 0, 'synthetic pid', '')

            with patch.object(sim, 'ROOT', root), patch.object(sim.socket, 'socket', return_value=Socket()), \
                 patch.object(sim.threading, 'Thread', Thread), patch.object(sim.subprocess, 'run', side_effect=launch), \
                 patch.object(sim.time, 'sleep'), patch.object(sim._process, 'Broker', Broker):
                with self.assertRaisesRegex(AssertionError, 'scan fixture launched' if launch_failure else 'bounded completion'):
                    sim.run_scan_case(args, 'ready_stop', owner=process, process=process)
            evidence = root / 'artifacts/scan-owner/simulator-cases' / label
            self.assertEqual((evidence / 'scan-events').read_text(), 'OWNER_ASSERT_FAIL=synthetic-timeout\n')
            self.assertIn('synthetic lease phase', (evidence / 'fe35-cli-status.log').read_text())
            self.assertTrue((evidence / 'launch-status.txt').is_file())
            if process:
                self.assertEqual((evidence / 'broker-exit.txt').read_text(), 'returncode=0')
            self.assertFalse((evidence / 'fe35-cli-result').exists())

    def test_result_missing(self): self.check_failure(False, False)
    def test_process_result_missing(self): self.check_failure(True, False)
    def test_launch_failure(self): self.check_failure(False, True)
    def test_process_launch_failure(self): self.check_failure(True, True)


if __name__ == '__main__': unittest.main()
