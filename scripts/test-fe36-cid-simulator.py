"""Actual production transport/owner/ObjC/Native auth; synthetic BTstack/phone.
Phone crypto is separately coded ObjC from upstream TestPhone, NOT a vendor peer.
Length-prefix proxy is only a fixture control channel; FE36 sees raw JSON bytes.
No frames, PIN, keys or identity values are included in assertion diagnostics.
"""
import json
from pathlib import Path
import shutil
import socket
import struct
import subprocess
import threading
import time

CASES = ('success', 'wrong_pin', 'forged_signature', 'wrong_peer', 'wrong_open_peer',
         'wrong_cid', 'control_cid_reuse', 'extra_connection', 'malformed_open',
         'wrong_data_cid', 'reopened_cid', 'wrong_listener',
         'control_close', 'auth_disconnect', 'stop', 'background', 'deadline', 'send_failure', 'cleanup_failure', 'pending_stop')


def run_case(args, h, case):
    documents = Path(args.data_dir) / 'Documents'
    guard = documents / ('auth-cid-' + case)
    guard.mkdir(parents=True, exist_ok=True)
    (guard / 'ready').write_text('READY\n', encoding='ascii')
    (guard / 'deadline').write_text(str(int(time.time()) + 120), encoding='ascii')
    (guard / 'heartbeat').write_text('POWER_DRIVER_OWNS_THIS\n', encoding='ascii')
    result = documents / 'fe35-cli-result'
    result.unlink(missing_ok=True)
    daemon = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    daemon.bind(('127.0.0.1', 0))
    daemon.listen(1)
    daemon.settimeout(45)
    phone = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    phone.bind(('127.0.0.1', 0))
    phone.listen(1)
    phone.settimeout(6)
    (guard / 'phone-port').write_text(str(phone.getsockname()[1]), encoding='ascii')
    errors, step = [], ['accept']
    pending = []
    auth_cid, control_cid = 0x3456, 0x2345
    peer = bytes.fromhex('a1a2a3a4a5a6')

    def packet(conn):
        return pending.pop(0) if pending else h.read_packet(conn)

    def command(conn, ocf, params):
        kind, channel, body = packet(conn)
        h.check((kind, channel, body) == (1, 0, struct.pack('<HB', 0xf400 | ocf, len(params)) + params),
                'CID cleanup command component=' + hex(ocf))

    def cleanup(conn, owned_auth=True, remote_auth_closed=False):
        step[0] = 'typed_cleanup'
        if owned_auth and not remote_auth_closed:
            command(conn, 0x41, struct.pack('<HB', auth_cid, 0))
            if case == 'pending_stop':
                (guard / 'stop').write_text('STOP\n', encoding='ascii')
                h.check(conn.recv(1) == b'', 'pending verified candidate revoked before unacknowledged close')
                return
            h.send_event(conn, 0x81, struct.pack('<H', auth_cid))
        command(conn, 0x31, struct.pack('<I', 0x10002))
        command(conn, 0x43, bytes([17, 0]))
        command(conn, 1, b'')
        h.send_event(conn, 0x60, bytes([2]))
        command(conn, 0x41, struct.pack('<HB', control_cid, 0))
        h.send_event(conn, 0x81, struct.pack('<H', control_cid))
        command(conn, 0x31, struct.pack('<I', 0x10001))
        command(conn, 0x43, bytes([16, 0]))
        command(conn, 1, b'')
        if case == 'cleanup_failure':
            conn.shutdown(socket.SHUT_RDWR)
        else:
            h.send_event(conn, 0x60, bytes([2]))
            h.check(conn.recv(1) == b'', 'CID transport socket released')

    def flow(conn):
        step[0] = 'fe36_incoming'
        incoming_peer = bytes([0x77]) * 6 if case == 'wrong_peer' else peer
        incoming_cid = control_cid if case == 'control_cid_reuse' else auth_cid
        incoming_channel = 18 if case == 'wrong_listener' else 17
        h.send_event(conn, 0x82, incoming_peer + bytes([incoming_channel]) + struct.pack('<H', incoming_cid))
        if case in ('wrong_peer', 'control_cid_reuse', 'wrong_listener'):
            cleanup(conn, owned_auth=False)
            return
        h.read_command(conn, 0x44, struct.pack('<H', auth_cid))
        open_peer = bytes([0x78]) * 6 if case == 'wrong_open_peer' else peer
        open_cid = auth_cid + 1 if case == 'wrong_cid' else auth_cid
        mtu = 0 if case == 'malformed_open' else 37
        h.send_event(conn, 0x80, bytes([0]) + open_peer + struct.pack('<H', 0x5678) +
                     bytes([17]) + struct.pack('<HHB', open_cid, mtu, 1))
        if case in ('wrong_open_peer', 'wrong_cid', 'malformed_open'):
            cleanup(conn)
            return
        if case == 'wrong_data_cid':
            h.send_packet(conn, 7, auth_cid + 1, b'{}')
            cleanup(conn)
            return
        if case == 'reopened_cid':
            h.send_event(conn, 0x80, bytes([0]) + peer + struct.pack('<H', 0x5678) +
                         bytes([17]) + struct.pack('<HHB', auth_cid, 37, 1))
            cleanup(conn)
            return
        if case == 'extra_connection':
            h.send_event(conn, 0x82, peer + bytes([17]) + struct.pack('<H', auth_cid + 1))
            cleanup(conn)
            return
        if case == 'control_close':
            h.send_event(conn, 0x81, struct.pack('<H', control_cid))
            cleanup(conn)
            return
        if case == 'auth_disconnect':
            h.send_event(conn, 0x81, struct.pack('<H', auth_cid))
            cleanup(conn, remote_auth_closed=True)
            return
        if case in ('stop', 'background', 'deadline'):
            if case in ('stop', 'background'):
                (guard / 'stop').write_text('STOP\n', encoding='ascii')
            cleanup(conn)
            return
        if case == 'send_failure':
            request = json.dumps({'oper_type': 1, 'data': json.dumps({'deviceId': 'SYNTHETIC_PHONE',
                                  'has_pin': True, 'usb_connection': False}), 'version': 'SYNTHETIC_PHONE_VERSION'}).encode()
            for at in range(0, len(request), 37):
                h.send_packet(conn, 7, auth_cid, request[at:at + 37])
            conn.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack('ii', 1, 0))
            return  # Actual reset; send/read/cleanup must fail without key.
        step[0] = 'same_pin_real_crypto_proxy'
        with phone.accept()[0] as peer_socket:
            peer_socket.settimeout(6)
            for exchange in range(4):
                size, = struct.unpack('!I', h.exact(peer_socket, 4))
                h.check(0 < size <= 4096, 'bounded synthetic phone request')
                request = h.exact(peer_socket, size)
                at = 0
                while at < size:
                    n = min(1 + at % 37, size - at)
                    h.send_packet(conn, 7, auth_cid, request[at:at + n])
                    at += n
                response = bytearray()
                failed = False
                while True:
                    kind, channel, body = h.read_packet(conn)
                    if kind == 1:
                        pending.append((kind, channel, body))
                        failed = True
                        break
                    h.check((kind, channel) == (7, auth_cid) and 0 < len(body) <= 37,
                            'all auth SEND bytes use owned CID and negotiated MTU')
                    response.extend(body)
                    h.check(len(response) <= 4096, 'bounded auth JSON reply')
                    try:
                        json.loads(response)
                        break
                    except (ValueError, UnicodeError):
                        continue
                peer_socket.sendall(struct.pack('!I', 0 if failed else len(response)))
                if not failed:
                    peer_socket.sendall(response)
                if failed:
                    h.check(case in ('wrong_pin', 'forged_signature'), 'positive pairing cannot terminate before reply')
                    break
            h.check(case != 'success' or exchange == 3, 'complete handshake PAKE1 PAKE2 signed exchange')
        cleanup(conn)

    def serve():
        try:
            with daemon.accept()[0] as conn:
                conn.settimeout(6)
                h.drive_peer(conn, 'success', lambda s: step.__setitem__(0, s), auth_flow=flow)
        except Exception as error:
            errors.append((step[0], type(error).__name__))

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    launch = subprocess.run(['xcrun', 'simctl', 'launch', args.udid, args.bundle_id,
                             'tcp:' + str(daemon.getsockname()[1]), 'Documents/' + guard.name,
                             'auth_' + case], capture_output=True, text=True, timeout=30)
    h.check(launch.returncode == 0, 'CID fixture launch')
    for _ in range(80):
        if result.exists():
            break
        time.sleep(.25)
    thread.join(8)
    daemon.close()
    phone.close()
    h.preserve_case_evidence(documents, guard, 'fe36-cid-' + case)
    h.check(not thread.is_alive() and not errors, 'CID daemon completed: ' + repr(errors))
    h.check(result.exists() and result.read_text().strip() == '0', 'CID production-code assertions ' + case)
    trace = (guard / 'scan-events').read_text()
    h.check('CID_ASSERT_FAIL=' not in trace, 'all named CID assertions passed')
    h.check(trace.count('TRUSTED_KEY_CALLBACK') == (1 if case == 'success' else 0), 'no key after failed/cancelled transport')
    h.check((guard / 'heartbeat').read_text() == 'POWER_DRIVER_OWNS_THIS\n', 'lease remains sole heartbeat owner')
    shutil.rmtree(guard)
    print('FE36_CID_TRANSPORT_AUTH_CASE_OK=' + case)


def run_all(args, harness):
    for case in CASES:
        run_case(args, harness, case)
    print('FE36_CID_TRANSPORT_AUTH_CASES_OK=' + str(len(CASES)))
