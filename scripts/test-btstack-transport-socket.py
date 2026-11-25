"""Build the control-channel adapter and exercise a synthetic BTstack Unix socket.

Requires clang. This test runs only a local AF_UNIX mock; it cannot contact an iPad.
"""
from pathlib import Path
import os
import socket
import struct
import subprocess
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = b'OPENHC-SYNTHETIC-CONTROL-v1'


def exact(conn, size):
    data = bytearray()
    while len(data) < size:
        part = conn.recv(size - len(data))
        if not part:
            raise EOFError('peer_closed')
        data.extend(part)
    return bytes(data)


def send_frame(conn, packet_type, channel, body):
    conn.sendall(struct.pack('<HHH', packet_type, channel, len(body)) + body)


def recv_frame(conn):
    packet_type, channel, size = struct.unpack('<HHH', exact(conn, 6))
    return packet_type, channel, exact(conn, size)


def command(conn, expected_ocf, expected_params):
    packet_type, channel, size = struct.unpack('<HHH', exact(conn, 6))
    assert (packet_type, channel, size) == (1, 0, 3 + len(expected_params))
    packet = exact(conn, size)
    opcode, length = struct.unpack('<HB', packet[:3])
    assert opcode == 0xF400 | expected_ocf
    assert length == len(expected_params)
    assert packet[3:] == expected_params


def opened(cid, profile='strict', status=0):
    addr_handle = bytes.fromhex('0102030405067856')
    params = bytes([status]) + addr_handle + bytes([7]) + struct.pack('<HH', cid, 512) + bytes([1])
    declared = 15 if profile == 'strict' else 16
    return bytes([0x80, declared]) + params


def run_case(executable, case):
    with tempfile.TemporaryDirectory(prefix='oh-transport-') as guard:
        Path(guard, 'ready').write_text('READY\n', encoding='ascii')
        Path(guard, 'deadline').write_text(str(int(__import__('time').time()) + 120) + '\n', encoding='ascii')
        endpoint = str(Path(guard) / 'btstack.sock')
        errors = []
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(endpoint)
        server.listen(1)
        server.settimeout(3)

        def serve():
            try:
                conn, _ = server.accept()
                with conn:
                    conn.settimeout(6)
                    command(conn, 1, b'')
                    send_frame(conn, 4, 0, bytes([0x60, 1, 2]))
                    command(conn, 0x40, bytes.fromhex('ffeeddccbbaa') + bytes([7]))
                    if case == 'open_timeout':
                        return
                    if case == 'security_event':
                        # The client may read the outer header and event code/length only.
                        conn.sendall(struct.pack('<HHH', 4, 0, 8) + bytes([0x31, 6]))
                        try:
                            extra = conn.recv(32)
                            assert extra == b'', 'no command expected after event rejection'
                        except (ConnectionResetError, OSError):
                            pass
                        return
                    profile = 'reference' if case == 'reference_event' else 'strict'
                    if case == 'bad_length':
                        event = bytearray(opened(0x1234, profile))
                        event[1] = 12
                        send_frame(conn, 4, 0, bytes(event))
                        return
                    cid = 0x1234
                    if case == 'create_failure':
                        payload = (bytes([0x80, 14, 0x56]) + bytes.fromhex('0102030405060000') +
                                   bytes([7]) + struct.pack('<HH', 0xBEEF, 512))
                        send_frame(conn, 4, 0, payload)
                        assert conn.recv(1) == b'', 'failed open must not disconnect an unowned CID'
                        return
                    send_frame(conn, 4, 0, opened(cid, profile))
                    packet_type, channel, body = recv_frame(conn)
                    assert (packet_type, channel, body) == (7, cid, PAYLOAD)
                    if case == 'delayed_echo':
                        time.sleep(2.3)
                    if case == 'echo_mismatch':
                        send_frame(conn, 7, cid, b'wrong')
                    elif case not in ('close_timeout', 'echo_timeout'):
                        send_frame(conn, 7, cid, PAYLOAD)
                    command(conn, 0x41, struct.pack('<HB', cid, 0))
                    if case != 'close_timeout':
                        send_frame(conn, 4, 0, bytes([0x81, 2]) + struct.pack('<H', cid))
            except Exception as error:
                errors.append(error)

        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        profile = {'reference_event': 'auto'}.get(case, 'auto')
        started_epoch = int(time.time())
        proc = subprocess.run([executable, endpoint, '--transport', 'AA:BB:CC:DD:EE:FF',
                               '7', profile, guard], capture_output=True, text=True, timeout=8)
        thread.join(7)
        server.close()
        assert not thread.is_alive(), case
        assert not errors, (case, errors, proc.stdout, proc.stderr)
        success = case in ('strict_event', 'reference_event', 'delayed_echo')
        profile_received = case in ('strict_event', 'reference_event', 'delayed_echo',
                                    'echo_mismatch', 'close_timeout', 'echo_timeout')
        assert proc.returncode == (0 if success else 1), (case, proc.returncode, proc.stdout, proc.stderr)
        assert ('BTSTACK_SYNTHETIC_CONTROL_ECHO_OK' in proc.stdout) == success, (case, proc.stdout)
        assert ('BTSTACK_RFCOMM_CLOSE_CONFIRMED' in proc.stdout) == success, (case, proc.stdout)
        assert ('BTSTACK_OPENED_PROFILE=' in proc.stdout) == profile_received, (case, proc.stdout)
        if profile_received:
            expected_profile = 'reference-17-len16' if case == 'reference_event' else 'strict-17'
            assert 'BTSTACK_OPENED_PROFILE=' + expected_profile in proc.stdout, (case, proc.stdout)
        if case == 'echo_timeout':
            assert 'BTSTACK_SYNTHETIC_CONTROL_FAILED=ECHO_TIMEOUT' in proc.stdout, (case, proc.stdout)
        heartbeat = Path(guard, 'heartbeat')
        assert heartbeat.exists(), (case, 'adapter did not refresh guard heartbeat')
        heartbeat_value = int(heartbeat.read_text(encoding='ascii').strip())
        if case == 'delayed_echo':
            assert heartbeat_value >= started_epoch + 1, 'long I/O did not keep guard heartbeat fresh'
        assert 'AA:BB:CC:DD:EE:FF' not in proc.stdout + proc.stderr
        return proc.stdout


def main():
    with tempfile.TemporaryDirectory(prefix='oh-transport-build-') as directory:
        executable = str(Path(directory) / 'transport')
        subprocess.run(['clang', '-std=c11', '-Wall', '-Wextra', '-Werror',
                        '-DOPENHC_BTSTACK_TEST', '-DOPENHC_TRANSPORT_TEST_TIMEOUTS',
                        '-DOPENHC_TRANSPORT_TEST_HEARTBEAT',
                        str(ROOT / 'theos/btstack-probe.c'), '-o', executable], check=True)
        for case in ('strict_event', 'reference_event', 'delayed_echo', 'bad_length',
                     'create_failure', 'open_timeout', 'echo_mismatch', 'close_timeout',
                     'echo_timeout', 'security_event'):
            output = run_case(executable, case)
            print('BTSTACK_TRANSPORT_SOCKET_CASE_OK=' + case)
        print('BTSTACK_TRANSPORT_SOCKET_TESTS_OK=10')
        # Re-open and reuse the same RFCOMM channel in separate daemon clients.
        run_case(executable, 'strict_event')
        run_case(executable, 'strict_event')
        print('BTSTACK_TRANSPORT_SOCKET_REOPEN_OK=2')


if __name__ == '__main__':
    main()
