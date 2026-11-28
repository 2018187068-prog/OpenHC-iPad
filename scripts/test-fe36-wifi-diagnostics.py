"""Redaction and failure-label regression for FE36 Nearby Simulator diagnostics."""
import importlib.util
from pathlib import Path
import socket
import struct
import threading
import unittest
import ast
import json
import re
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

root = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('cid', root / 'test-fe36-cid-simulator.py')
cid = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cid)
wire_spec = importlib.util.spec_from_file_location('wire', root / 'test-fe35-cli-inbound-simulator.py')
wire = importlib.util.module_from_spec(wire_spec)
wire_spec.loader.exec_module(wire)


def plain_frame(outer, payload):
    body = b'\x7f' + wire.ea(outer) + wire.ea(0) + wire.ea(0) + wire.ea(len(payload)) + payload
    return body + struct.pack('<H', wire.crc16_arc(body))


class DiagnosticTests(unittest.TestCase):
    def early_command(self, kind, channel, body, expected_error=None):
        # Actual host socket pair, independent typed command construction.
        left, right = socket.socketpair()
        left.settimeout(2)
        phases = []
        observer = lambda k, c, s, o, n: cid.observe_early_packet(
            'incoming-accept', k, c, s, o, n, phases.append)
        try:
            wire.send_packet(right, kind, channel, body)
            if expected_error:
                with self.assertRaisesRegex(AssertionError, expected_error):
                    wire.read_command(left, 0x44, b'\x45\x23', observer)
            else:
                wire.read_command(left, 0x44, b'\x45\x23', observer)
            return phases
        finally:
            left.close()
            right.close()

    def test_early_exact_accept_command(self):
        phases = self.early_command(1, 0, b'\x44\xf4\x02\x45\x23')
        self.assertIn('-opcode-62532-declared-length-2', phases[-1])

    def test_actual_driver_early_order_and_bridge_assertions(self):
        for start, expected in (((7, 0x2345, plain_frame(0, b'\x00')), EOFError),
                                ((1, 0, b'\x41\xf4\x03SECRET'), AssertionError),
                                ((7, 0x9999, plain_frame(0, b'\x00')), AssertionError),
                                ((7, 0x2345, plain_frame(4, b'\x00')), AssertionError)):
            left, right = socket.socketpair()
            right.settimeout(2)
            phases, errors = [], []
            def drive():
                try:
                    wire.drive_peer(left, 'success', phases.append,
                        observe_early=lambda branch, k, c, s, o, n: cid.observe_early_packet(
                            branch, k, c, s, o, n, phases.append))
                except Exception as error:
                    errors.append(error)
            thread = threading.Thread(target=drive)
            thread.start()
            try:
                wire.send_packet(right, 1, 0, b'\x01\xf4\x00')
                self.assertEqual(wire.read_packet(right), (4, 0, b'\x60\x01\x02'))
                wire.send_packet(right, 1, 0, b'\x42\xf4\x03\x10\x00\x02')
                self.assertEqual(wire.read_packet(right), (4, 0, b'\x85\x02\x00\x10'))
                # Independent minimal bytes satisfying the existing SDP checks.
                sdp = b'\x19\xfe\x35\x08\x10\x09\x00\x04\x35\x0c'
                wire.send_packet(right, 1, 0, b'\x30\xf4' + bytes([len(sdp)]) + sdp)
                self.assertEqual(wire.read_packet(right)[2][0], 0x90)
                self.assertEqual(wire.read_packet(right)[2][0], 0x82)
                wire.send_packet(right, 1, 0, b'\x44\xf4\x02\x45\x23')
                self.assertEqual(wire.read_packet(right)[2][0], 0x80)
                wire.send_packet(right, *start)
                if expected is EOFError:
                    self.assertEqual(wire.read_packet(right)[0:2], (7, 0x2345))
                    self.assertEqual(wire.read_packet(right)[0:2], (7, 0x2345))
                right.shutdown(socket.SHUT_WR)
                thread.join(2)
                self.assertFalse(thread.is_alive())
                self.assertEqual(len(errors), 1)
                self.assertIsInstance(errors[0], expected)
                branches = [item.split('-kind-')[0] for item in phases if item.startswith('early-')]
                self.assertEqual(list(dict.fromkeys(branches)), [
                    'early-initial-state', 'early-control-listener', 'early-control-sdp',
                    'early-incoming-accept', 'early-bridge-start'])
                if expected is AssertionError:
                    self.assertIn(cid.safe_label(str(errors[0])), ('bridge-start-transport', 'bridge-start-frame'))
                self.assertNotIn('SECRET', repr(phases))
            finally:
                left.close()
                right.close()
                thread.join(2)

    def test_early_unexpected_close_opcode_channel_and_length_still_fail(self):
        cases = [
            (1, 0, b'\x41\xf4\x03\x45\x23\x00', 'command header', 62529, 3),
            (1, 0, b'\x41\xf4\x02\x45\x23', 'command opcode', 62529, 2),
            (1, 7, b'\x44\xf4\x02\x45\x23', 'command header', 62532, 2),
            (1, 0, b'\x44\xf4\x01\x45\x23', 'command parameter length', 62532, 1),
            (1, 0, b'\x44\xf4\x02XX', 'command parameters', 62532, 2),
            (7, 0, b'never-log-payload', 'command header', None, None),
            (1, 0, b'X', 'command header', None, None),
        ]
        for kind, channel, body, label, opcode, length in cases:
            with self.subTest(kind=kind, channel=channel, label=label, body_size=len(body)):
                phases = self.early_command(kind, channel, body, label)
                self.assertTrue(phases[0].startswith('early-incoming-accept-kind-'))
                if opcode is not None:
                    self.assertIn('-opcode-' + str(opcode) + '-declared-length-' + str(length), phases[-1])
                self.assertNotIn('never-log', repr(phases))

    def test_early_truncated_command_retains_header_without_payload(self):
        left, right = socket.socketpair()
        left.settimeout(2)
        phases = []
        try:
            right.sendall(struct.pack('<HHH', 1, 0, 6) + b'X')
            right.shutdown(socket.SHUT_WR)
            with self.assertRaises(EOFError):
                wire.read_command(left, 0x44, b'\x45\x23',
                    lambda k, c, s, o, n: cid.observe_early_packet(
                        'incoming-accept', k, c, s, o, n, phases.append))
            self.assertEqual(len(phases), 1)
            self.assertIn('-size-6-opcode-unavailable-', phases[0])
        finally:
            left.close()
            right.close()

    def test_early_bridge_start_packet_and_unexpected_command_are_typed(self):
        for kind, channel, body in ((7, 0x2345, b'SECRET_FRAME_CONTENT'),
                                    (1, 0, b'\x41\xf4\x03SECRET')):
            left, right = socket.socketpair()
            left.settimeout(2)
            phases = []
            try:
                wire.send_packet(right, kind, channel, body)
                actual = wire.read_packet(left, lambda k, c, s, o, n: cid.observe_early_packet(
                    'bridge-start', k, c, s, o, n, phases.append))
                self.assertEqual(actual, (kind, channel, body))
                self.assertIn('early-bridge-start-kind-' + str(kind), phases[0])
                if kind == 1:
                    self.assertIn('-opcode-62529-declared-length-3', phases[-1])
                self.assertNotIn('SECRET', repr(phases))
            finally:
                left.close()
                right.close()

    def test_early_branch_and_numeric_whitelist_reject_arbitrary_content(self):
        phases = []
        for args in (('SECRET', 1, 0, 5, None, None),
                     ('bridge-start', 1, 0, b'SECRET', None, None)):
            with self.assertRaises(ValueError):
                cid.observe_early_packet(*args, phases.append)
        self.assertEqual(phases, [])

    def test_phase_observer_has_no_disk_writes_and_is_bounded(self):
        tree = ast.parse((root / 'test-fe36-cid-simulator.py').read_text())
        case = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == '_run_case')
        phase = next(node for node in case.body if isinstance(node, ast.FunctionDef) and node.name == 'phase')
        self.assertFalse(any(isinstance(node, ast.Attribute) and node.attr in ('write_text', 'write_bytes', 'open')
                             for node in ast.walk(phase)))
        self.assertIn('4095', ast.unparse(phase))

    def test_flush_attempts_both_files_if_one_write_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            guard = Path(directory)
            write_text = Path.write_text
            def write(path, *args, **kwargs):
                if path.name == 'proxy-phases.log':
                    raise OSError('SECRET filesystem detail')
                return write_text(path, *args, **kwargs)
            with patch.object(Path, 'write_text', write):
                with self.assertRaisesRegex(OSError, '^proxy-evidence-write-failed$'):
                    cid.flush_proxy_evidence(guard, ['early-incoming-accept'], ['123 early-incoming-accept'])
            self.assertIn('123 early-incoming-accept', (guard / 'proxy-timing.log').read_text())

    def test_case_finally_retains_early_metadata_after_protocol_failure(self):
        # Actual TCP sockets/threads; Simulator launch/process observations are
        # injected and are not Apple runtime evidence.
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            args = SimpleNamespace(data_dir=str(path), udid='injected', bundle_id='injected')
            finished = threading.Event()
            real_drive = wire.drive_peer
            peers = []
            def drive(conn, case, phase, **kwargs):
                try:
                    real_drive(conn, case, phase, **kwargs)
                finally:
                    finished.set()
            def launch(argv, **kwargs):
                peer = socket.create_connection(('127.0.0.1', int(argv[-3].split(':')[1])), timeout=2)
                peers.append(peer)
                wire.send_packet(peer, 1, 0, b'\x41\xf4\x03SECRET')
                self.assertTrue(finished.wait(2))
                # No observer rewrite occurred even on the error path.
                guard = path / 'Documents/auth-cid-cleanup_failure'
                self.assertFalse((guard / 'proxy-phases.log').exists())
                return subprocess.CompletedProcess([], 0, 'injected: 12345', '')
            try:
                with patch.object(wire, 'ROOT', path), patch.object(wire, 'drive_peer', side_effect=drive), \
                     patch.object(cid.subprocess, 'run', side_effect=launch), \
                     patch.object(cid, 'simulator_process_exited', return_value=True):
                    with self.assertRaises(cid.IsolatedCaseFailure):
                        cid.run_case(args, wire, 'cleanup_failure')
                evidence = path / 'artifacts/scan-owner/simulator-cases/fe36-cid-cleanup_failure'
                phases = (evidence / 'proxy-phases.log').read_text()
                self.assertIn('early-initial-state-kind-1', phases)
                self.assertIn('-opcode-62529-declared-length-3', phases)
                self.assertIn('assertion-command-header', phases)
                self.assertIn('daemon-finished', phases)
                self.assertNotIn('SECRET', phases)
                certificate = json.loads((evidence / 'case-outcome.json').read_text())
                self.assertEqual(certificate['outcome'], 'failed')
                self.assertTrue(certificate['isolation']['safe'])
                try:
                    self.assertEqual(peers[0].recv(1), b'')
                except ConnectionResetError:
                    pass  # unread rejected command body: reset also proves close
            finally:
                for peer in peers:
                    peer.close()

    def test_actual_c_primary_label_snapshot_survives_cleanup_overwrite(self):
        source = (root.parent / 'theos/btstack-probe.c').read_text()
        function = re.search(r'static const char \*inbound_primary_stage\(.*?\n}', source, re.S).group(0)
        snapshot = re.search(r'const char \*const primary_failure_stage = .*?;', source).group(0)
        self.assertLess(source.index(snapshot), source.index('if(tcp>=0 && close(tcp))'))
        self.assertEqual(source.count('primary_failure_stage ='), 1)
        inbound = source[source.index('static int transport_inbound('):source.index('done:;')]
        assigned = {label for expression in re.findall(r'stage\s*=\s*([^;]+);', inbound)
                    for label in re.findall(r'"([A-Z_]+)"', expression)}
        self.assertTrue(assigned <= set(re.findall(r'"([A-Z_]+)"', function)))
        # Run the exact extracted diagnostic C statements, not a Python model.
        compiler = shutil.which('clang') or shutil.which('cc')
        command = [compiler] if compiler else [shutil.which('zig'), 'cc']
        self.assertTrue(command[0], 'existing strict C compiler required')
        program = '#include <stddef.h>\n#include <string.h>\n' + function + '\nint main(void) {\n'
        program += 'int result=1; const char *stage="INCOMING_OPEN";\n' + snapshot + '\n'
        program += 'stage="CLEANUP_UNCONFIRMED";\n'
        program += 'if(strcmp(primary_failure_stage,"INCOMING_OPEN") || strcmp(stage,"CLEANUP_UNCONFIRMED")) return 1;\n'
        program += 'if(strcmp(inbound_primary_stage("SECRET"),"UNCLASSIFIED")) return 2;\n'
        program += 'if(strcmp(inbound_primary_stage(NULL),"UNCLASSIFIED")) return 3;\n'
        program += '{ int result=0; stage="CONTROL_STREAM"; ' + snapshot + '\n'
        program += 'stage="CLEANUP_UNCONFIRMED"; if(strcmp(primary_failure_stage,"NONE")) return 4; }\n'
        program += 'return 0; }\n'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            cfile, executable = path / 'primary.c', path / 'primary.exe'
            cfile.write_text(program)
            built = subprocess.run(command + ['-std=c11', '-Wall', '-Wextra', '-Werror',
                str(cfile), '-o', str(executable)], capture_output=True, timeout=60)
            self.assertEqual(built.returncode, 0, built.stderr.decode(errors='replace'))
            self.assertEqual(subprocess.run([str(executable)], timeout=10).returncode, 0)

    def test_frame_metadata_reports_types_and_never_bytes(self):
        secret_marker = b'NO_LOG_THIS_FRAME_CONTENT'
        frame = plain_frame(4, secret_marker)
        metadata = cid.inspect_nearby_frame(frame, wire.crc16_arc)
        self.assertIs(metadata['header'], True)
        self.assertIs(metadata['crc'], True)
        self.assertEqual(metadata['outer'], 4)
        self.assertIs(metadata['encrypted'], False)
        self.assertIs(metadata['length'], True)
        rendered = repr(metadata)
        self.assertNotIn(secret_marker.decode(), rendered)
        damaged = frame[:-1] + bytes([frame[-1] ^ 1])
        self.assertIs(cid.inspect_nearby_frame(damaged, wire.crc16_arc)['crc'], False)
        self.assertEqual(cid.inspect_nearby_frame(b'not-frame', wire.crc16_arc)['header'], 'not-nearby')

    def run_failed_receive(self, packet, decode):
        left, right = socket.socketpair()
        left.settimeout(2)
        phases = []
        errors = []

        def check(condition, label):
            if not condition:
                raise AssertionError(label)

        h = type('Harness', (), {
            'ea': staticmethod(wire.ea),
            'encrypted_frame': staticmethod(lambda outer, payload, seed: b'fixture-frame'),
            'decode_frame': staticmethod(decode),
            'crc16_arc': staticmethod(wire.crc16_arc),
            'read_packet': staticmethod(wire.read_packet),
            'send_packet': staticmethod(wire.send_packet),
            'check': staticmethod(check),
        })()

        def drive():
            try:
                cid.wifi_negotiate(left, h, Path('.'), 'wifi_success', phases.append)
            except Exception as error:
                errors.append(error)

        thread = threading.Thread(target=drive)
        thread.start()
        try:
            wire.read_packet(right)  # consume the emitted resource request
            kind, channel, body = packet
            wire.send_packet(right, kind, channel, body)
            thread.join(2)
            self.assertFalse(thread.is_alive())
            self.assertTrue(errors)
            return phases, errors[0]
        finally:
            left.close()
            right.close()
            thread.join(2)

    def test_wrong_transport_packet_preserves_assertion_and_redacts_body(self):
        marker = b'NO_LOG_THIS_CONTROL_BODY'
        phases, error = self.run_failed_receive((1, 0, marker), lambda _body: (4, 1, b''))
        self.assertEqual(str(error), 'FE35 retained for authenticated WiFi negotiation')
        self.assertTrue(any(item.startswith('wifi-response-packet-kind-actual-1-expected-7-channel-actual-0-expected-9029-')
                            for item in phases))
        self.assertIn('wifi-assertion-transport-shape', phases)
        self.assertNotIn(marker.decode(), '\n'.join(phases))

    def test_wrong_data_cid_is_typed_without_frame_content(self):
        marker = b'NO_LOG_THIS_WRONG_CID_FRAME'
        phases, error = self.run_failed_receive((7, 0x4567, marker), lambda _body: (4, 1, b''))
        self.assertEqual(str(error), 'FE35 retained for authenticated WiFi negotiation')
        self.assertTrue(any('kind-actual-7-expected-7-channel-actual-17767-expected-9029-' in item
                            for item in phases))
        self.assertNotIn(marker.decode(), '\n'.join(phases))

    def test_missing_response_records_bounded_read_phase(self):
        left, right = socket.socketpair()
        left.settimeout(.05)
        phases = []
        errors = []

        def check(condition, label):
            if not condition:
                raise AssertionError(label)

        h = type('Harness', (), {
            'ea': staticmethod(wire.ea),
            'encrypted_frame': staticmethod(lambda outer, payload, seed: b'fixture-frame'),
            'decode_frame': staticmethod(lambda _body: (4, 1, b'')),
            'crc16_arc': staticmethod(wire.crc16_arc),
            'read_packet': staticmethod(wire.read_packet),
            'send_packet': staticmethod(wire.send_packet),
            'check': staticmethod(check),
        })()

        def drive():
            try:
                cid.wifi_negotiate(left, h, Path('.'), 'wifi_success', phases.append)
            except Exception as error:
                errors.append(error)

        thread = threading.Thread(target=drive)
        thread.start()
        try:
            wire.read_packet(right)
            thread.join(2)
            self.assertFalse(thread.is_alive())
            self.assertEqual(len(errors), 1)
            self.assertIn('wifi-response-read-error-TimeoutError', phases)
            self.assertEqual(phases[-1], 'wifi-response-read-error-TimeoutError')
        finally:
            left.close()
            right.close()
            thread.join(2)

    def test_malformed_nearby_packet_records_crc_validation_without_payload(self):
        marker = b'NO_LOG_THIS_ENCRYPTED_PAYLOAD'
        frame = bytearray(plain_frame(4, marker))
        frame[-1] ^= 1

        def reject_crc(_body):
            raise AssertionError('Nearby frame CRC')

        phases, error = self.run_failed_receive((7, 0x2345, bytes(frame)), reject_crc)
        self.assertEqual(str(error), 'Nearby frame CRC')
        self.assertTrue(any(item.startswith('wifi-response-frame-') and '-crc-false-' in item for item in phases))
        self.assertIn('wifi-response-decoder-assertion-nearby-crc', phases)
        self.assertNotIn(marker.decode(), '\n'.join(phases))

    def test_unknown_decoder_assertion_text_is_not_persisted(self):
        marker = 'NO_LOG_THIS_ASSERTION_TEXT'
        frame = plain_frame(4, b'fixture')

        def reject(_body):
            raise AssertionError('decoder detail ' + marker)

        phases, error = self.run_failed_receive((7, 0x2345, frame), reject)
        self.assertIn(marker, str(error))
        self.assertIn('wifi-response-decoder-assertion-unclassified', phases)
        self.assertNotIn(marker, '\n'.join(phases))


if __name__ == '__main__':
    unittest.main()
