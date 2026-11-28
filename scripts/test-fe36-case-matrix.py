"""Deterministic matrix/process adapters; no Simulator or Native runtime claim."""
import ast
import contextlib
import errno
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

root = Path(__file__).resolve().parent
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, root / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
cid = load('matrix_cid', 'test-fe36-cid-simulator.py')
wire = load('matrix_wire', 'test-fe35-cli-inbound-simulator.py')

class MatrixTests(unittest.TestCase):
    def matrix(self, runner, fails=True):
        with tempfile.TemporaryDirectory() as folder:
            harness = SimpleNamespace(ROOT=Path(folder))
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                if fails:
                    with self.assertRaisesRegex(AssertionError, 'matrix incomplete or failed'):
                        cid.run_all(None, harness, runner)
                else:
                    cid.run_all(None, harness, runner)
            data = json.loads((harness.ROOT / 'artifacts/scan-owner/simulator-cases/fe36-matrix.json').read_text())
            return data, output.getvalue()

    def test_all_original_cases_required_before_suite_ok(self):
        visited=[]
        def run(_args, _h, case):
            visited.append(case);return True
        data,output=self.matrix(run,False)
        self.assertEqual(visited,list(cid.CASES+cid.WIFI_CASES+cid.LIVE_CASES))
        self.assertEqual(len(data),43)
        self.assertTrue(all(e['outcome']=='passed' for e in data))
        self.assertIn('FE36_CID_TRANSPORT_AUTH_CASES_OK=25',output)
        self.assertIn('FE36_NEARBY_TCP_TRANSPORT_CASES_OK=10',output)
        self.assertIn('FE36_LIVE_TCP_CONTROL_CASES_OK=8',output)

    def test_early_and_late_isolated_failures_reach_every_later_target(self):
        visited=[]
        def run(_args,_h,case):
            visited.append(case)
            if case in ('background','wifi_malformed'):
                raise cid.IsolatedCaseFailure('handshake-transport-shape')
            return True
        data,output=self.matrix(run)
        self.assertEqual(visited,list(cid.CASES+cid.WIFI_CASES+cid.LIVE_CASES))
        self.assertEqual([e['case'] for e in data if e['outcome']=='failed'],['background','wifi_malformed'])
        self.assertNotIn('CASES_OK=',output)
        self.assertEqual(data[-1]['outcome'],'passed')

    def test_stuck_case_stops_and_names_unrun(self):
        visited=[]
        def run(_args,_h,case):
            visited.append(case)
            if case=='stop':raise cid.UnsafeCaseFailure('process-or-daemon-still-live')
            return True
        data,output=self.matrix(run)
        stopped=list(cid.CASES).index('stop')
        self.assertEqual(len(visited),stopped+1)
        self.assertEqual(data[stopped]['outcome'],'unsafe')
        self.assertTrue(all(e['outcome']=='unrun' for e in data[stopped+1:]))
        self.assertNotIn('CASES_OK=',output)

    def test_setup_error_and_unproven_isolation_stop_with_redaction(self):
        marker='DO_NOT_LOG_PRIVATE_ERROR'
        for error in (FileNotFoundError(marker),AssertionError(marker)):
            def run(*_):raise error
            data,output=self.matrix(run)
            self.assertEqual(data[0]['outcome'],'unsafe')
            self.assertNotIn(marker,json.dumps(data)+output)
            self.assertTrue(all(e['outcome']=='unrun' for e in data[1:]))
            self.assertNotIn('CASES_OK=',output)

    def test_missing_certificate_cannot_be_promoted(self):
        data,output=self.matrix(lambda *_:None)
        self.assertEqual(data[0]['label'],'missing-isolation-certificate')
        self.assertEqual(data[1]['outcome'],'unrun')
        self.assertNotIn('CASES_OK=',output)

    def test_exact_launch_pid_required(self):
        self.assertEqual(cid.simulator_pid(SimpleNamespace(stdout='org.example.fixture: 12345\n'),'org.example.fixture'),12345)
        for text in ('org.example.fixture: 1','other: 12345','org.example.fixture: 12345\nprivate',None):
            with self.assertRaises(cid.UnsafeCaseFailure):
                cid.simulator_pid(SimpleNamespace(stdout=text),'org.example.fixture')

    def test_host_exit_observation_fails_closed(self):
        with patch.object(cid.sys,'platform','darwin'):
            with patch.object(cid.os,'kill',side_effect=OSError(errno.ESRCH,'absent')):
                self.assertTrue(cid.simulator_process_exited(12345))
            with patch.object(cid.os,'kill',return_value=None) as check:
                self.assertFalse(cid.simulator_process_exited(12345))
                check.assert_called_once_with(12345,0)
            with patch.object(cid.os,'kill',side_effect=OSError(errno.EPERM,'private')):
                with self.assertRaises(cid.UnsafeCaseFailure):cid.simulator_process_exited(12345)
        with patch.object(cid.sys,'platform','win32'):
            with self.assertRaises(cid.UnsafeCaseFailure):cid.simulator_process_exited(12345)

    def lifecycle(self, *, alive=False, exited=True, result=True, launch_code=0):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder);sockets=[]
            class Socket:
                def __init__(self,*_):self.closed=False;sockets.append(self)
                def bind(self,_):pass
                def listen(self,_):pass
                def settimeout(self,_):pass
                def getsockname(self):return ('127.0.0.1',12345)
                def shutdown(self,_):pass
                def close(self):self.closed=True
            class Thread:
                def __init__(self,**_):pass
                def start(self):pass
                def join(self,_):pass
                def is_alive(self):return alive
            def launch(*_,**__):
                guard=folder/'Documents/auth-cid-wrong_pin'
                (guard/'scan-events').write_text('SYNTHETIC_LIFECYCLE_ONLY\n')
                if result:(folder/'Documents/fe35-cli-result').write_text('0')
                return SimpleNamespace(returncode=launch_code,stdout='synthetic: 12345\n')
            def preserve(d,g,label):
                wire.preserve_case_evidence(d,g,label)
            harness=SimpleNamespace(ROOT=folder,check=wire.check,preserve_case_evidence=preserve)
            args=SimpleNamespace(data_dir=str(folder),udid='synthetic',bundle_id='synthetic')
            with patch.object(wire,'ROOT',folder),patch.object(cid.socket,'socket',Socket), \
                 patch.object(cid.threading,'Thread',Thread),patch.object(cid.subprocess,'run',side_effect=launch), \
                 patch.object(cid,'simulator_process_exited',return_value=exited),patch.object(cid.time,'sleep'), \
                 contextlib.redirect_stdout(io.StringIO()):
                try:
                    certificate=cid.run_case(args,harness,'wrong_pin');error=None
                except Exception as caught:
                    certificate=None;error=caught
            evidence=folder/'artifacts/scan-owner/simulator-cases/fe36-cid-wrong_pin'
            data=json.loads((evidence/'case-outcome.json').read_text())
            self.assertTrue((evidence/'scan-events').is_file())
            self.assertTrue(all(s.closed for s in sockets))
            return certificate,error,data

    def test_case_success_requires_both_exit_and_thread_stop(self):
        certificate,error,data=self.lifecycle()
        self.assertIs(certificate,True);self.assertIsNone(error)
        self.assertEqual(data['isolation'],{'safe':True,'thread_stopped':True,'process_exited':True})

    def test_live_process_or_stuck_daemon_cannot_continue(self):
        for kwargs in ({'alive':True},{'exited':False}):
            certificate,error,data=self.lifecycle(**kwargs)
            self.assertIsNone(certificate)
            self.assertIsInstance(error,cid.UnsafeCaseFailure)
            self.assertFalse(data['isolation']['safe'])
            self.assertEqual(data['outcome'],'unsafe')

    def test_process_observer_failure_still_closes_sockets_and_stops_daemon(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder); sockets=[]; threads=[]
            class Socket:
                def __init__(self,*_):self.closed=False;sockets.append(self)
                def bind(self,_):pass
                def listen(self,_):pass
                def settimeout(self,_):pass
                def getsockname(self):return ('127.0.0.1',12345)
                def shutdown(self,_):pass
                def close(self):self.closed=True
            class Thread:
                def __init__(self,**_):threads.append(self)
                def start(self):pass
                def join(self,_):pass
                def is_alive(self):return False
            def launch(*_,**__):return SimpleNamespace(returncode=0,stdout='synthetic: 12345\n')
            harness=SimpleNamespace(ROOT=folder,check=wire.check,preserve_case_evidence=lambda *_:None)
            args=SimpleNamespace(data_dir=str(folder),udid='synthetic',bundle_id='synthetic')
            def observer(_):raise cid.UnsafeCaseFailure('host-process-observation-failed')
            with patch.object(cid.socket,'socket',Socket),patch.object(cid.threading,'Thread',Thread), \
                 patch.object(cid.subprocess,'run',side_effect=launch),patch.object(cid,'simulator_process_exited',side_effect=observer):
                with self.assertRaises(cid.UnsafeCaseFailure):cid.run_case(args,harness,'wrong_pin')
            self.assertTrue(sockets and all(s.closed for s in sockets))
            self.assertTrue(threads)
            evidence=folder/'artifacts/scan-owner/simulator-cases/fe36-cid-wrong_pin/case-outcome.json'
            self.assertTrue(evidence.is_file())
            self.assertIn('host-process-observation-failed',evidence.read_text())

    def test_exited_fixture_missing_result_fails_but_is_isolated(self):
        certificate,error,data=self.lifecycle(result=False)
        self.assertIsInstance(error,cid.IsolatedCaseFailure)
        self.assertEqual(data['label'],'fixture-result')
        self.assertTrue(data['isolation']['safe'])

    def test_launch_failure_stops_even_when_thread_stopped(self):
        _,error,data=self.lifecycle(launch_code=1)
        self.assertIsInstance(error,cid.UnsafeCaseFailure)
        self.assertEqual(data['label'],'fixture-launch')
        self.assertFalse(data['isolation']['safe'])

    def test_every_reachable_literal_assertion_has_fixed_token(self):
        selected={
            'test-fe35-cli-inbound-simulator.py': {'drive_peer','decode_frame','read_ea','read_command','assert_service_record'},
            'test-fe36-cid-simulator.py': {'wifi_negotiate','require_cleanup_command','negative_inform',
                                        'acknowledge_negative_close','_run_case','read_tcp_frame','live_control'},
        }
        checked=0
        for name,functions in selected.items():
            tree=ast.parse((root/name).read_text())
            for function in tree.body:
                if not isinstance(function,ast.FunctionDef) or function.name not in functions:continue
                for node in ast.walk(function):
                    if not isinstance(node,ast.Call):continue
                    label=None
                    func=node.func
                    if ((isinstance(func,ast.Name) and func.id=='check') or
                        (isinstance(func,ast.Attribute) and func.attr=='check')) and len(node.args)>1:
                        label=node.args[1]
                    if isinstance(func,ast.Name) and func.id=='AssertionError' and node.args:label=node.args[0]
                    if isinstance(label,ast.Constant) and isinstance(label.value,str):
                        self.assertNotEqual(cid.safe_label(label.value),'unclassified',label.value);checked+=1
        self.assertGreater(checked,40)
        for case in cid.CASES+cid.WIFI_CASES+cid.LIVE_CASES:
            self.assertEqual(cid.safe_label('CID production-code assertions '+case),'fixture-result')
        self.assertEqual(cid.safe_label('CID daemon completed: DO_NOT_LOG'),'daemon-failure')
        self.assertEqual(cid.safe_label('command header expected_ocf=PRIVATE'),'command-header')
        self.assertEqual(cid.safe_label('DO_NOT_LOG'),'unclassified')

if __name__=='__main__':unittest.main()
