"""Failure-only harness regression; no Apple, daemon, phone or process pass claim."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('sim', Path(__file__).with_name('test-fe35-cli-inbound-simulator.py'))
sim = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sim)


class Socket:
    def bind(self, _): pass
    def listen(self, _): pass
    def settimeout(self, _): pass
    def getsockname(self): return ('127.0.0.1', 12345)
    def close(self): pass


class Thread:
    def __init__(self, **_): pass
    def start(self): pass
    def is_alive(self): return False


class EvidenceTests(unittest.TestCase):
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
