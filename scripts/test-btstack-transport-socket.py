"""Build the control-channel adapter and exercise a synthetic BTstack Unix socket.

Requires clang. This test runs only a local AF_UNIX mock; it cannot contact an iPad.
"""
from pathlib import Path
import os
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = b'OPENHC-SYNTHETIC-CONTROL-v1'
UPSTREAM_PHONE_FIRST = (
    '7f8080801b81818105838d3031323334353637383941420085810290db30313233343536373839414243444546303132'
    '333435363738394142434445463031323334353637383941424344454630313233343536373839414243444546262630'
    '26263026264645444342413938373635343332313026263192a7303132333435363738393a3b3c3d3e3f404142434445'
    '464748494a4b4c4d4e4f50515253545556343b'
)
WIRE_ASSERTIONS = 0


def wire_check(condition, context):
    global WIRE_ASSERTIONS
    WIRE_ASSERTIONS += 1
    if not condition:
        raise AssertionError(context)


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
    wire_check((packet_type, channel, size) == (1, 0, 3 + len(expected_params)), 'command_header')
    packet = exact(conn, size)
    opcode, length = struct.unpack('<HB', packet[:3])
    wire_check(opcode == 0xF400 | expected_ocf, 'command_opcode')
    wire_check(length == len(expected_params), 'command_length')
    wire_check(packet[3:] == expected_params, 'command_payload')


def bridge_config(device_id='synthetic-device'):
    encoded = device_id.encode('ascii')
    return bytes([1, len(encoded)]) + encoded + bytes([16]) + bytes(16) + bytes([16]) + bytes(16) + bytes([16]) + bytes(16)


def opened(cid, profile='strict', status=0):
    addr_handle = bytes.fromhex('0102030405067856')
    params = bytes([status]) + addr_handle + bytes([7]) + struct.pack('<HH', cid, 512) + bytes([1])
    declared = 15 if profile == 'strict' else 16
    return bytes([0x80, declared]) + params


def run_case(executable, case):
    with tempfile.TemporaryDirectory(prefix='oh-transport-') as guard:
        Path(guard, 'ready').write_text('READY\n', encoding='ascii')
        Path(guard, 'deadline').write_text(str(int(__import__('time').time()) + 120) + '\n', encoding='ascii')
        Path(guard, 'heartbeat').write_text('POWER_DRIVER_OWNS_THIS\n', encoding='ascii')
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
            assert 'BTSTACK_SYNTHETIC_CONTROL_FAILED=ECHO_TIMEOUT_OR_IO' in proc.stdout, (case, proc.stdout)
        expected_failure = {
            'bad_length': 'OPEN_EVENT_REJECTED',
            'create_failure': 'CREATE_FAILED',
            'open_timeout': 'OPEN_EVENT_TIMEOUT_OR_IO',
            'close_timeout': 'CLOSE_UNCONFIRMED',
            'security_event': 'OPEN_EVENT_REJECTED',
        }.get(case)
        if expected_failure:
            assert 'BTSTACK_SYNTHETIC_CONTROL_FAILED=' + expected_failure in proc.stdout, (case, proc.stdout)
        heartbeat = Path(guard, 'heartbeat')
        assert heartbeat.read_text(encoding='ascii') == 'POWER_DRIVER_OWNS_THIS\n', (
            case, 'transport must not take ownership of guard heartbeat')
        assert 'AA:BB:CC:DD:EE:FF' not in proc.stdout + proc.stderr
        return proc.stdout


def run_inbound_case(executable, case):
    with tempfile.TemporaryDirectory(prefix='oh-inbound-') as guard:
        Path(guard, 'ready').write_text('READY\n', encoding='ascii')
        Path(guard, 'deadline').write_text(str(int(time.time()) + 120) + '\n', encoding='ascii')
        Path(guard, 'heartbeat').write_text('POWER_DRIVER_OWNS_THIS\n', encoding='ascii')
        endpoint = str(Path(guard) / 'btstack.sock')
        errors = []
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(endpoint)
        server.listen(1)

        def serve():
            try:
                conn, _ = server.accept()
                with conn:
                    conn.settimeout(4)
                    command(conn, 1, b'')
                    send_frame(conn, 4, 0, bytes([0x60, 1, 2]))
                    command(conn, 0x42, bytes([16, 0, 2]))
                    if case == 'rfcomm_failure':
                        send_frame(conn, 4, 0, bytes([0x85, 2, 4, 16]))
                        wire_check(conn.recv(1) == b'', 'failed_rfcomm_no_owned_cleanup')
                        return
                    send_frame(conn, 4, 0, bytes([0x85, 2, 0, 16]))
                    packet_type, channel, size = struct.unpack('<HHH', exact(conn, 6))
                    packet = exact(conn, size)
                    opcode, length = struct.unpack('<HB', packet[:3])
                    wire_check((packet_type, channel, opcode, length) == (1, 0, 0xF430, size - 3), 'control_sdp_header')
                    wire_check(b'\xfe\x35' in packet[3:], 'control_sdp_uuid')
                    wire_check(bytes([16]) in packet[3:], 'control_sdp_channel')
                    if case == 'sdp_failure':
                        send_frame(conn, 4, 0, bytes([0x90, 5, 4]) + struct.pack('<I', 0x1ffff))
                        command(conn, 0x43, bytes([16, 0]))
                        command(conn, 1, b'')
                        send_frame(conn, 4, 0, bytes([0x60, 1, 2]))
                        wire_check(conn.recv(1) == b'', 'failed_sdp_no_unowned_handle_cleanup')
                        return
                    send_frame(conn, 4, 0, bytes([0x90, 5, 0]) + struct.pack('<I', 0x10001))
                    if case == 'incoming_timeout':
                        time.sleep(.3)
                        command(conn, 0x31, struct.pack('<I', 0x10001))
                        command(conn, 0x43, bytes([16, 0]))
                        command(conn, 1, b'')
                        send_frame(conn, 4, 0, bytes([0x60, 1, 2]))
                        return
                    cid = 0x2345
                    incoming = bytes([0x82, 9]) + bytes.fromhex('a1a2a3a4a5a6') + bytes([16]) + struct.pack('<H', cid)
                    send_frame(conn, 4, 0, incoming)
                    command(conn, 0x44, struct.pack('<H', cid))
                    if case == 'daemon_cleanup':
                        return
                    if case == 'accept_failure':
                        failed = bytes([0x80, 14, 0x04]) + bytes.fromhex('010203040506') + struct.pack('<H', 0x5678) + bytes([16]) + struct.pack('<HH', cid, 512)
                        send_frame(conn, 4, 0, failed)
                    else:
                        opened = bytes([0x80, 15, 0]) + bytes.fromhex('010203040506') + struct.pack('<H', 0x5678) + bytes([16]) + struct.pack('<HHB', cid, 512, 1)
                        send_frame(conn, 4, 0, opened)
                        packet_type, channel, body = recv_frame(conn)
                        wire_check((packet_type, channel, body) ==
                            (7, cid, bytes([0x7f, 0x80, 0x80, 0x80])), 'bridge_start_frame')
                        send_frame(conn, 7, cid, bytes([0xff]) if case == 'bridge_exception' else
                                   bytes.fromhex(UPSTREAM_PHONE_FIRST))
                        if case != 'bridge_exception':
                            command(conn, 0x42, bytes([16, 0, 2]))
                            send_frame(conn, 4, 0, bytes([0x85, 2, 0x71, 16]))
                            command(conn, 0x42, bytes([17, 0, 2]))
                            send_frame(conn, 4, 0, bytes([0x85, 2, 0, 17]))
                            packet_type, channel, size = struct.unpack('<HHH', exact(conn, 6))
                            service = exact(conn, size)
                            opcode, param_length = struct.unpack('<HB', service[:3])
                            wire_check((packet_type, channel, opcode, param_length) == (1, 0, 0xF430, size - 3), 'auth_sdp_header')
                            wire_check(b'\x1c\x00\x00\xfe\x36' in service[3:], 'auth_sdp_uuid128')
                            wire_check(bytes([17]) in service[3:], 'auth_sdp_channel')
                            send_frame(conn, 4, 0, bytes([0x90, 5, 0]) + struct.pack('<I', 0x10002))
                            packet_type, channel, response = recv_frame(conn)
                            wire_check((packet_type, channel, response) ==
                                (7, cid, bytes([0x7f, 0x80, 0x80, 0x81, 0x04])), 'listener_ready_response')
                            send_frame(conn, 4, 0, bytes([0x81, 2]) + struct.pack('<H', cid))
                    if case in ('success', 'bridge_exception'):
                        if case == 'success':
                            command(conn, 0x31, struct.pack('<I', 0x10002))
                            command(conn, 0x43, bytes([17, 0]))
                            command(conn, 1, b'')
                            send_frame(conn, 4, 0, bytes([0x60, 1, 2]))
                        command(conn, 0x41, struct.pack('<HB', cid, 0))
                        send_frame(conn, 4, 0, bytes([0x81, 2]) + struct.pack('<H', cid))
                    command(conn, 0x31, struct.pack('<I', 0x10001))
                    command(conn, 0x43, bytes([16, 0]))
                    command(conn, 1, b'')
                    send_frame(conn, 4, 0, bytes([0x60, 1, 2]))
                    try:
                        conn.recv(1)
                    except OSError:
                        pass
            except Exception as error:
                errors.append(error)

        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        device_id = 'synthetic-exception' if case == 'bridge_exception' else 'synthetic-device'
        proc = subprocess.run([executable, endpoint, '--btstack-control-inbound', guard],
                              input=bridge_config(device_id), capture_output=True, timeout=8)
        stdout = proc.stdout.decode('utf-8', errors='replace')
        stderr = proc.stderr.decode('utf-8', errors='replace')
        thread.join(5)
        server.close()
        assert not thread.is_alive(), (case, proc.stdout, proc.stderr)
        assert not errors, (case, errors, proc.stdout, proc.stderr)
        success = case == 'success'
        assert proc.returncode == (0 if success else 1), (case, proc.returncode, stdout, stderr)
        wire_check(stdout.count('BTSTACK_TEST_BRIDGE_CLOSE_CALLED') == 1, 'bridge_closed_once')
        assert Path(guard, 'heartbeat').read_text(encoding='ascii') == 'POWER_DRIVER_OWNS_THIS\n'
        assert ('BTSTACK_FE35_BRIDGE_SESSION_OK' in stdout) == success, (case, stdout)
        assert ('BTSTACK_FE35_DISCONNECT_CONFIRMED' in stdout) == success, (case, stdout)
        assert 'BTSTACK_FE35_INBOUND_FAILED=BRIDGE_EVENT_DISPATCH' in stdout if case == 'bridge_exception' else True
        assert 'BTSTACK_FE35_INBOUND_FAILED=ACCEPT_FAILED' in stdout if case == 'accept_failure' else True
        assert 'BTSTACK_FE35_INBOUND_FAILED=INCOMING_TIMEOUT' in stdout if case == 'incoming_timeout' else True
        assert 'a1:a2:a3:a4:a5:a6' not in stdout.lower() + stderr.lower()
        return stdout


def main():
    with tempfile.TemporaryDirectory(prefix='oh-transport-build-') as directory:
        sigpipe_test = str(Path(directory) / 'sigpipe-test')
        subprocess.run(['clang', '-std=c11', '-Wall', '-Wextra', '-Werror',
                        str(ROOT / 'scripts/btstack-sigpipe-test.c'),
                        str(ROOT / 'scripts/fe35-control-bridge-test-stub.c'),
                        '-o', sigpipe_test], check=True)
        subprocess.run([sigpipe_test], check=True, timeout=4)
        executable = str(Path(directory) / 'transport')
        subprocess.run(['clang', '-std=c11', '-Wall', '-Wextra', '-Werror',
                        '-DOPENHC_BTSTACK_TEST', '-DOPENHC_TRANSPORT_TEST_TIMEOUTS',
                        '-DOPENHC_TRANSPORT_TEST_HEARTBEAT',
                        str(ROOT / 'theos/btstack-probe.c'),
                        str(ROOT / 'scripts/fe35-control-bridge-test-stub.c'), '-o', executable], check=True)
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
        before_inbound_assertions = WIRE_ASSERTIONS
        for case in ('success', 'bridge_exception', 'accept_failure', 'incoming_timeout', 'daemon_cleanup',
                     'rfcomm_failure', 'sdp_failure'):
            run_inbound_case(executable, case)
            print('BTSTACK_INBOUND_SOCKET_CASE_OK=' + case)
        print('BTSTACK_INBOUND_SOCKET_TESTS_OK=7')
        print('BTSTACK_INBOUND_WIRE_ASSERTIONS_OK=' + str(WIRE_ASSERTIONS - before_inbound_assertions))
        # Same production C, real socket deadlines/cleanup, fixed diagnostic
        # headers. Runs on existing host/owner routes, no new demo/workflow.
        subprocess.run([sys.executable, str(ROOT / 'scripts/test-fe35-incoming-boundary.py')], check=True)


if __name__ == '__main__':
    main()
