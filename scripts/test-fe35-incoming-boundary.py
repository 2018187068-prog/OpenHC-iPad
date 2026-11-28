"""Actual production C incoming/cleanup socket regression, no device contact.

The bridge and owner callback are existing test effects. Production framing,
incoming deadline and cleanup code execute unchanged. Four explicit modes inject
one send/close error at the OS boundary; the remaining cases use real socket IO.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import socket
import struct
import subprocess
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('incoming_peer', ROOT / 'scripts/test-fe35-cli-inbound-simulator.py')
peer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(peer)


def event(code, params):
    body = bytes([code, len(params)]) + params
    return struct.pack('<HHH', 4, 0, len(body)) + body


def run_case(executable, case, mode):
    evidence = peer.IncomingBoundary()
    commands, errors = [], []
    with tempfile.TemporaryDirectory(prefix='oh-incoming-') as directory:
        guard = Path(directory)
        (guard / 'ready').write_text('READY\n', encoding='ascii')
        (guard / 'deadline').write_text(str(int(time.time()) + 120) + '\n', encoding='ascii')
        (guard / 'heartbeat').write_text('POWER_DRIVER_OWNS_THIS\n', encoding='ascii')
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.bind(('127.0.0.1', 0))
        server.listen(1)
        server.settimeout(8)

        def command(conn, ocf, params):
            before = len(commands)
            def observed(kind, channel, size, opcode, length):
                if opcode is not None:
                    commands.append(dict(kind=kind, channel=channel, size=size, opcode=opcode,
                                         length=length, at_ns=time.monotonic_ns()))
            peer.read_command(conn, ocf, params, observed)
            assert len(commands) == before + 1

        def serve():
            try:
                with server.accept()[0] as conn:
                    conn.settimeout(6)
                    if case == 'original_strict_late':
                        def delayed(label):
                            evidence.stage(label)
                            if label == 'control_sdp_ack_after':
                                time.sleep(.35)
                        try:
                            peer.drive_peer(conn, 'success', evidence.stage,
                                            observe_early=evidence.typed, observe_boundary=delayed)
                        except AssertionError as error:
                            assert 'expected_ocf=0xf444 actual=(kind=1,channel=0,size=7)' in str(error)
                        else:
                            raise AssertionError('original strict peer must reject timed-out cleanup')
                        return
                    evidence.stage('initial_state')
                    command(conn, 1, b'')
                    conn.sendall(event(0x60, b'\x02'))
                    evidence.stage('register_control_channel')
                    command(conn, 0x42, bytes([16, 0, 2]))
                    conn.sendall(event(0x85, bytes([0, 16])))
                    evidence.stage('register_fe35_sdp')
                    kind, channel, body = peer.read_packet(conn)
                    assert (kind, channel, body[:2]) == (1, 0, b'\x30\xf4')
                    assert body[2] == len(body) - 3
                    peer.assert_service_record(body[3:], b'\x19\xfe\x35', 16)
                    ack = event(0x90, b'\x00' + struct.pack('<I', 0x10001))
                    incoming = event(0x82, bytes.fromhex('a1a2a3a4a5a6') + bytes([16]) + struct.pack('<H', 0x2345))
                    evidence.stage('control_sdp_ack_before')
                    # Prequeued event provides a deterministic before-deadline
                    # control, without changing the C deadline or mocking time.
                    conn.sendall(ack + incoming if case == 'prequeued_open' else ack)
                    evidence.stage('control_sdp_ack_after')
                    if case.startswith('late_'):
                        time.sleep(.35)  # deliberately exceeds original test150ms
                        evidence.stage('incoming_send_before')
                        conn.sendall(incoming)
                        evidence.stage('incoming_send_after')
                    if case == 'prequeued_open':
                        command(conn, 0x44, struct.pack('<H', 0x2345))
                        conn.sendall(event(0x80, b'\x00' + bytes.fromhex('010203040506') +
                                           struct.pack('<H', 0x5678) + bytes([16]) +
                                           struct.pack('<HHB', 0x2345, 512, 1)))
                        kind, channel, body = peer.read_packet(conn)
                        assert (kind, channel, body) == (7, 0x2345, b'\x7f\x80\x80\x80')
                        conn.sendall(event(0x81, struct.pack('<H', 0x2345)))
                        command(conn, 0x41, struct.pack('<HB', 0x2345, 0))
                        conn.sendall(event(0x81, struct.pack('<H', 0x2345)))
                    if mode != 1:
                        command(conn, 0x31, struct.pack('<I', 0x10001))
                    if mode != 2:
                        command(conn, 0x43, bytes([16, 0]))
                    if mode != 3:
                        command(conn, 1, b'')
                        if case == 'late_barrier_eof':
                            return
                        if case == 'barrier_timeout':
                            assert conn.recv(1) == b''
                            return
                        if case == 'barrier_wrong_channel':
                            body = b'\x60\x01\x02'
                            conn.sendall(struct.pack('<HHH', 4, 1, 3) + body)
                        else:
                            conn.sendall(event(0x60, b'\x02'))
                    assert conn.recv(1) == b'', 'no extra command, actual socket closed'
            except BaseException as error:
                # Persist only a fixed error label; raw fixture exception remains
                # in the local assertion, not in the diagnostic certificate.
                errors.append(error)

        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        try:
            proc = subprocess.run([str(executable), 'tcp:' + str(server.getsockname()[1]),
                                   directory, str(mode)], capture_output=True, text=True, timeout=10)
            thread.join(7)
            assert not thread.is_alive(), case
            assert not errors, (case, errors, proc.stdout, proc.stderr)
            assert proc.returncode == 0, (case, proc.returncode, proc.stdout, proc.stderr)
            cleanup = case in ('prequeued_open', 'missing_clean', 'late_clean')
            assert re.findall(r'^FE35_INCOMING_C_COMPLETION=(.*)$', proc.stdout, re.M) == ['1,' + str(int(cleanup)) + ',1'], (case, proc.stdout)
            assert 'FE35_INCOMING_C_CALLBACKS=1,1,1\n' in proc.stdout
            assert 'FE35_INCOMING_C_FAULTS=' + str(int(mode != 0)) + '\n' in proc.stdout
            assert proc.stdout.count('BTSTACK_TEST_BRIDGE_CLOSE_CALLED\n') == 1
            stage = 'CONTROL_DISCONNECTED_EARLY' if case == 'prequeued_open' else 'INCOMING_TIMEOUT'
            assert 'BTSTACK_FE35_INBOUND_PRIMARY_STAGE=' + stage + '\n' in proc.stdout
            certificate = evidence.finish(proc.stdout, not thread.is_alive())
            assert certificate['native_records'] == certificate['cleanup_records'] == 1
            start, deadline, end, received, cleanup_start, cleanup_end, status, confirmed = certificate['native_ms']
            assert 0 < deadline - start <= 150
            assert start <= end <= cleanup_start <= cleanup_end
            assert status == 1 and confirmed == int(cleanup)
            if case == 'prequeued_open':
                assert received == 0 and end < deadline
                assert certificate['cleanup_facts'] == [1,1,0,0,1,1,1,0,0,0]
            else:
                assert received == -1 and end >= deadline
                failure = {1:8, 2:9, 3:10, 4:11}.get(mode, 0 if cleanup else 10)
                expected = [int(cleanup or mode == 4), int(mode != 4),0,0,0,0,0,0,0,failure]
                assert certificate['cleanup_facts'] == expected, (case,certificate)
                if not mode:
                    # Reproduce the exact observed *shape*, independently learn
                    # the actual opcode; this does not identify the old run's opcode.
                    source = certificate['events'] if case == 'original_strict_late' else commands
                    first = next(c for c in source if c.get('opcode') == 0xf431)
                    assert (first['kind'],first['channel'],first['size'],first['length']) == (1,0,7,4)
            assert (guard / 'heartbeat').read_text(encoding='ascii') == 'POWER_DRIVER_OWNS_THIS\n'
            assert not any(x in proc.stdout + proc.stderr for x in ('a1a2a3a4a5a6', 'KEY!', 'hicar://'))
            return dict(case=case, mode=mode, protocol_status=1, cleanup_confirmed=cleanup,
                        certificate=certificate, commands=commands, native_stdout=proc.stdout)
        finally:
            server.close()


def diagnostic_regression():
    left, right = socket.socketpair()
    try:
        left.settimeout(2)
        right.settimeout(2)
        boundary = peer.IncomingBoundary()
        peer.send_packet(left, 1, 0, struct.pack('<HB', 0xf431, 4) + b'KEY!')
        try:
            peer.read_command(right, 0x44, struct.pack('<H', 0x2345),
                              lambda *args: boundary.typed('incoming-accept', *args))
        except AssertionError as error:
            assert 'expected_ocf=0xf444' in str(error)
        else:
            raise AssertionError('strict accept assertion must still reject cleanup command')
        assert peer.exact(right, 4) == b'KEY!', 'diagnostic consumes fixed header only, never payload'
        certificate = boundary.finish('untrusted text KEY! hicar://\n', True)
        assert len(certificate['events']) == 2
        assert certificate['events'][1]['opcode'] == 0xf431
        assert certificate['events'][1]['length'] == 4
        assert 'KEY!' not in json.dumps(certificate) and 'hicar://' not in json.dumps(certificate)
        for _ in range(100):
            boundary.stage('incoming_send_before')
        bounded = boundary.finish('', False)
        assert len(bounded['events']) == 32 and bounded['truncated']
        try:
            boundary.stage('KEY!')
        except ValueError:
            pass
        else:
            raise AssertionError('diagnostic label allowlist')
    finally:
        left.close()
        right.close()


def run_suite(executable, output=None):
    diagnostic_regression()
    cases = [('prequeued_open',0), ('missing_clean',0), ('late_clean',0),
             ('late_barrier_eof',0), ('original_strict_late',0),
             ('barrier_wrong_channel',0), ('barrier_timeout',0),
             ('remove_handle_send_failure',1), ('remove_channel_send_failure',2),
             ('barrier_send_failure',3), ('socket_close_failure',4)]
    rows = []
    for case, mode in cases:
        rows.append(run_case(executable, case, mode))
        print('FE35_INCOMING_PRODUCTION_C_SOCKET_CASE_OK=' + case)
    if output:
        Path(output).write_text(json.dumps(dict(boundary='actual-production-C-real-loopback;injected-bridge-owner-and-four-syscall-faults;not-device',
                                               results=rows), indent=2) + '\n', encoding='ascii')
    print('FE35_INCOMING_PRODUCTION_C_SOCKET_CASES_OK=' + str(len(rows)))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--executable', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.executable:
        run_suite(args.executable, args.output)
    else:
        with tempfile.TemporaryDirectory(prefix='oh-incoming-build-') as directory:
            executable = Path(directory) / 'incoming-test'
            subprocess.run(['clang','-std=c11','-Wall','-Wextra','-Werror',
                            str(ROOT / 'scripts/fe35-incoming-boundary-test.c'),
                            str(ROOT / 'scripts/fe35-control-bridge-test-stub.c'),
                            '-o',str(executable)], check=True)
            run_suite(executable, args.output)


if __name__ == '__main__':
    main()
