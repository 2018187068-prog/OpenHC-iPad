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
         'control_close', 'auth_disconnect', 'stop', 'background', 'deadline', 'send_failure', 'cleanup_failure', 'pending_stop',
         'late_cleanup_data')
WIFI_CASES = ('wifi_success', 'wifi_pending', 'wifi_duplicate', 'wifi_stop', 'wifi_expiry',
              'wifi_malformed', 'wifi_unsupported', 'wifi_tcp_failure', 'wifi_disconnect',
              'wifi_cleanup_failure')


def safe_label(value):
    labels = {
        'FE35 retained for authenticated WiFi negotiation': 'transport-shape',
        'actual encrypted Nearby WiFi frame': 'nearby-envelope',
        'Nearby frame header': 'nearby-header',
        'Nearby frame CRC': 'nearby-crc',
        'EA unterminated': 'nearby-ea',
        'Nearby seed TLV': 'nearby-seed-tlv',
        'Nearby frame exact length': 'nearby-exact-length',
        'pinned WiFi data-channel acceptance role and frequency': 'wifi-accept-payload',
        'unsupported channel NO_CHANNEL': 'wifi-unsupported-payload',
        'duplicate request repeats original frequency': 'wifi-duplicate-accept',
        'network and listener ready before peer MAC request': 'wifi-listener-request',
        'reference connection info uses actual listening TCP port': 'wifi-connection-info',
        'all auth SEND bytes use owned CID and negotiated MTU': 'auth-send-shape',
        'bounded auth JSON reply': 'auth-reply-bound',
    }
    return labels.get(value, 'unclassified')


def safe_exception_name(error):
    known = {'AssertionError', 'EOFError', 'TimeoutError', 'error', 'IndexError',
             'ValueError', 'UnicodeError', 'struct.error'}
    name = type(error).__name__
    return name if name in known else 'other'


def inspect_nearby_frame(frame, crc16):
    """Return framing metadata only; never retain or render frame contents."""
    result = {'frame_bytes': len(frame), 'header': False, 'crc': 'unavailable',
              'outer': 'unavailable', 'encrypted': 'unavailable', 'length': 'unavailable'}
    if not frame or frame[0] != 0x7f:
        result['header'] = 'not-nearby'
        return result
    result['header'] = True
    if len(frame) >= 3:
        expected_crc = struct.unpack('<H', frame[-2:])[0]
        result['crc'] = expected_crc == crc16(frame[:-2])
    def ea(at):
        value = 0
        for i in range(4):
            pos = at + i
            if pos >= len(frame):
                return None
            byte = frame[pos]
            value |= (byte & 0x7f) << (7 * i)
            if byte & 0x80:
                return value, pos + 1
        return None
    outer = ea(1)
    if outer is None:
        return result
    result['outer'] = outer[0]
    flag = ea(outer[1])
    if flag is None:
        return result
    result['encrypted'] = bool(flag[0] & 1)
    flag_length = ea(flag[1])
    if flag_length is None:
        return result
    payload_length_at = flag_length[1] + flag_length[0]
    payload_length = ea(payload_length_at)
    if payload_length is None:
        return result
    payload_start = payload_length[1]
    result['payload_bytes'] = max(0, len(frame) - payload_start - 2)
    result['length'] = payload_start + payload_length[0] + 2 == len(frame)
    return result


def wifi_negotiate(conn, h, guard, case, phase):
    """Actual Nearby wire packets; injected loopback network, no WiFi hardware effects."""
    cid = 0x2345

    def tlv(tag, value=b''):
        return h.ea(tag) + h.ea(len(value)) + value

    def send(outer, payload):
        frame = h.encrypted_frame(outer, payload, bytes(range(0xe1, 0xe9)))
        for at in range(0, len(frame), 17):
            h.send_packet(conn, 7, cid, frame[at:at + 17])

    def check(condition, label):
        try:
            h.check(condition, label)
        except AssertionError:
            phase('wifi-assertion-' + safe_label(label))
            raise

    def receive(outer):
        phase('wifi-response-read-start')
        try:
            kind, channel, body = h.read_packet(conn)
        except Exception as error:
            phase('wifi-response-read-error-' + safe_exception_name(error))
            raise
        shape = ('kind-actual-' + str(kind) + '-expected-7-channel-actual-' + str(channel) +
                 '-expected-' + str(cid) + '-size-' + str(len(body)))
        if kind == 1 and len(body) >= 3:
            opcode, length = struct.unpack('<HB', body[:3])
            shape += '-opcode-' + hex(opcode) + '-parameters-' + str(length)
        elif kind == 4 and len(body) >= 2:
            shape += '-event-' + hex(body[0]) + '-parameters-' + str(body[1])
        phase('wifi-response-packet-' + shape)
        check((kind, channel) == (7, cid), 'FE35 retained for authenticated WiFi negotiation')
        metadata = inspect_nearby_frame(body, h.crc16_arc)
        metadata['outer_expected'] = outer
        metadata['encrypted_expected'] = True
        phase('wifi-response-frame-' + '-'.join(
            key + '-' + str(value).lower().replace(' ', '_') for key, value in metadata.items()))
        try:
            got, encrypted, payload = h.decode_frame(body)
        except AssertionError as error:
            phase('wifi-response-decoder-assertion-' + safe_label(str(error)))
            raise
        except Exception as error:
            phase('wifi-response-decoder-error-' + safe_exception_name(error))
            raise
        phase('wifi-response-decoded-outer-' + str(got) + '-expected-' + str(outer) +
              '-encrypted-' + str(encrypted) + '-expected-1-payload-bytes-' + str(len(payload)))
        check((got, encrypted) == (outer, 1), 'actual encrypted Nearby WiFi frame')
        return payload

    phase('wifi-resource-request')
    if case == 'wifi_malformed':
        send(4, tlv(1, b'\x83'))  # missing required capability TLV
        return
    channel = 8 if case == 'wifi_unsupported' else 3
    request = tlv(1, h.ea(channel) + tlv(3))
    send(4, request)
    if case == 'wifi_pending':
        # Safe typed state marker is flushed by the actual C loop only after the common
        # pending-request event. No arbitrary delay or new protocol/owner deadline.
        status = guard.parent / 'fe35-cli-status.log'
        bound = time.monotonic() + 2
        while time.monotonic() < bound:
            if status.exists() and 'BTSTACK_WIFI_NETWORK_PENDING' in status.read_text():
                break
            time.sleep(.005)
        h.check(status.exists() and 'BTSTACK_WIFI_NETWORK_PENDING' in status.read_text(),
                'actual common request is pending before network readiness')
        h.check(not (guard / 'tcp-port').exists(), 'listener cannot start before confirmed negotiation')
        (guard / 'network-ready').write_text('SYNTHETIC_READY\n', encoding='ascii')
    reply = receive(4)
    if case == 'wifi_unsupported':
        check(reply == tlv(2, h.ea(8) + h.ea(255)), 'unsupported channel NO_CHANNEL')
        (guard / 'stop').write_text('STOP\n', encoding='ascii')
        return
    expected = tlv(2, h.ea(3) + h.ea(1) + tlv(3, b'\x01' + h.ea(2437)))
    check(reply == expected, 'pinned WiFi data-channel acceptance role and frequency')
    if case == 'wifi_duplicate':
        send(4, request)
        check(receive(4) == expected, 'duplicate request repeats original frequency')
    result = tlv(7, h.ea(3) + h.ea(1))
    send(4, result)
    check(receive(33) == tlv(1), 'network and listener ready before peer MAC request')
    if case == 'wifi_duplicate':
        send(4, result)  # must not create another listener/MAC request
    send(33, tlv(2, b'02:12:34:56:78:9a'))
    connection = receive(33)
    port = int((guard / 'tcp-port').read_text())
    expected_info = ('127.0.0.2##SYNTHETIC\n02:11:22:33:44:55\nsynthetic-pass\n2437'
                     '##version:3##' + str(port) + '##hicarApIp:127.0.0.1').encode()
    check(connection == tlv(3, expected_info), 'reference connection info uses actual listening TCP port')
    phase('wifi-info-sent-control-still-owned')
    if case == 'wifi_duplicate':
        send(33, tlv(2, b'02:12:34:56:78:9a'))  # no second connection-info send
    if case == 'wifi_stop':
        (guard / 'stop').write_text('STOP\n', encoding='ascii')
        return
    if case == 'wifi_expiry':
        return  # retain original owner deadline; cleanup parser waits for expiry, no new budget
    if case == 'wifi_disconnect':
        h.send_event(conn, 0x81, struct.pack('<H', cid))
        return
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp:
        tcp.settimeout(6)
        # This is the injected network proxy's real source, not configured phone WiFi.
        # The negative case supplies a different trusted association to the actual C accept gate.
        tcp.bind(('127.0.0.1', 0))
        tcp.connect(('127.0.0.1', port))
        phase('wifi-actual-tcp-connect')
        check(tcp.recv(1) == b'', 'owned TCP boundary is closed at bounded slice completion')


def consume_negative_auth_close(kind, channel, body, auth_cid):
    """Recognize exactly one production auth-CID close command.

    read_packet returns the complete command body: opcode (u16), parameter
    length (u8), then CID (u16) and status (u8). Malformed or unrelated
    commands stay in the pending queue for strict cleanup parsing.
    """
    expected = struct.pack('<HBHB', 0xf441, 3, auth_cid, 0)
    return kind == 1 and channel == 0 and body == expected


def negative_inform(response, case):
    outer = json.loads(response)
    if not isinstance(outer, dict):
        raise AssertionError('auth envelope object required')
    if outer.get('oper_type') != 3:
        return False
    inner = json.loads(outer['data'])
    if not isinstance(inner, dict):
        raise AssertionError('auth message object required')
    if inner.get('message') != 0x8080:
        return False
    expected = {'wrong_pin': 17, 'forged_signature': 29}.get(case)
    payload = inner.get('payload')
    if (expected is None or type(inner['message']) is not int or
            type(outer['oper_type']) is not int or not isinstance(payload, dict) or
            type(payload.get('errorCode')) is not int or payload['errorCode'] != expected):
        raise AssertionError('unexpected auth INFORM terminal')
    return True


def acknowledge_negative_close(packet, auth_cid, send_ack, already_closed=False):
    if already_closed or not consume_negative_auth_close(*packet, auth_cid):
        raise AssertionError('exact one-shot auth close required')
    send_ack()
    return True


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
    diagnostics = []
    def phase(label):
        step[0] = label
        if diagnostics and diagnostics[-1] == label:
            return
        diagnostics.append(label)
        (guard / 'proxy-phases.log').write_text('\n'.join(diagnostics) + '\n', encoding='ascii')
    pending = []
    auth_cid, control_cid = 0x3456, 0x2345
    peer = bytes.fromhex('a1a2a3a4a5a6')

    def packet(conn):
        return pending.pop(0) if pending else h.read_packet(conn)

    def command(conn, ocf, params):
        phase('cleanup-command-' + hex(ocf))
        kind, channel, body = packet(conn)
        if kind == 1 and len(body) >= 3:
            opcode, length = struct.unpack('<HB', body[:3])
            phase('received-command-' + hex(opcode) + '-length-' + str(length))
        h.check((kind, channel, body) == (1, 0, struct.pack('<HB', 0xf400 | ocf, len(params)) + params),
                'CID cleanup command component=' + hex(ocf))

    def cleanup(conn, owned_auth=True, remote_auth_closed=False, auth_services=True):
        step[0] = 'typed_cleanup'
        if owned_auth and not remote_auth_closed:
            command(conn, 0x41, struct.pack('<HB', auth_cid, 0))
            if case == 'pending_stop':
                (guard / 'stop').write_text('STOP\n', encoding='ascii')
                h.check(conn.recv(1) == b'', 'pending verified candidate revoked before unacknowledged close')
                return
            h.send_event(conn, 0x81, struct.pack('<H', auth_cid))
        if auth_services:
            command(conn, 0x31, struct.pack('<I', 0x10002))
            command(conn, 0x43, bytes([17, 0]))
            command(conn, 1, b'')
            h.send_event(conn, 0x60, bytes([2]))
        command(conn, 0x41, struct.pack('<HB', control_cid, 0))
        if case == 'late_cleanup_data':
            # A real crypto candidate exists; this unexpected FE35 payload
            # before the close ACK must revoke it, never be silently skipped.
            h.send_packet(conn, 7, control_cid, b'{}')
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
        phase('phone-accept')
        terminal_auth_closed = False
        with phone.accept()[0] as peer_socket:
            peer_socket.settimeout(6)
            for exchange in range(4):
                phase('exchange-' + str(exchange) + '-phone-header-read')
                size, = struct.unpack('!I', h.exact(peer_socket, 4))
                h.check(0 < size <= 4096, 'bounded synthetic phone request')
                request = h.exact(peer_socket, size)
                at = 0
                phase('exchange-' + str(exchange) + '-auth-input-write')
                while at < size:
                    n = min(1 + at % 37, size - at)
                    h.send_packet(conn, 7, auth_cid, request[at:at + n])
                    at += n
                response = bytearray()
                failed = False
                while True:
                    phase('exchange-' + str(exchange) + '-auth-output-read')
                    kind, channel, body = h.read_packet(conn)
                    if kind == 1:
                        # A negative authenticator result is followed by the
                        # production transport's typed auth-CID close. That
                        # close is the terminal acknowledgement for this
                        # exchange and must not be replayed into cleanup(),
                        # which would wait for a second close and then report
                        # a misleading EOF. Preserve unrelated commands for
                        # the normal cleanup parser.
                        if consume_negative_auth_close(kind, channel, body, auth_cid):
                            # The transport waits for the remote close event
                            # before releasing the listener/control CIDs.
                            # Acknowledging it here preserves the real cleanup
                            # sequence; merely consuming the command would
                            # make the daemon close the connection as unknown.
                            terminal_auth_closed = acknowledge_negative_close(
                                (kind, channel, body), auth_cid,
                                lambda: h.send_event(conn, 0x81, struct.pack('<H', auth_cid)),
                                terminal_auth_closed)
                            phase('auth-close-ack-0x81-sent')
                        else:
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
                terminal_inform = not failed and negative_inform(response, case)
                if terminal_inform:
                    phase('exchange-' + str(exchange) + '-validated-inform')
                phase('exchange-' + str(exchange) + '-phone-response-write')
                peer_socket.sendall(struct.pack('!I', 0 if failed else len(response)))
                if not failed:
                    peer_socket.sendall(response)
                if failed:
                    h.check(case in ('wrong_pin', 'forged_signature'), 'positive pairing cannot terminate before reply')
                    break
                if terminal_inform:
                    # INFORM is a real ordered SEND followed by local failure.
                    # Phone consumes it as failure and sends no further request.
                    phase('negative-inform-delivered-auth-close-read')
                    terminal_auth_closed = acknowledge_negative_close(
                        h.read_packet(conn), auth_cid,
                        lambda: h.send_event(conn, 0x81, struct.pack('<H', auth_cid)),
                        terminal_auth_closed)
                    phase('auth-close-ack-0x81-sent')
                    break
            h.check(case not in ('success',) + WIFI_CASES or exchange == 3,
                    'complete handshake PAKE1 PAKE2 signed exchange')
        if case in ('wrong_pin', 'forged_signature'):
            h.check(terminal_auth_closed, 'negative auth terminal close acknowledged')
        if case in WIFI_CASES:
            phase('wifi-auth-cid-confirmed-release')
            command(conn, 0x41, struct.pack('<HB', auth_cid, 0))
            h.send_event(conn, 0x81, struct.pack('<H', auth_cid))
            command(conn, 0x31, struct.pack('<I', 0x10002))
            command(conn, 0x43, bytes([17, 0]))
            command(conn, 1, b'')
            h.send_event(conn, 0x60, bytes([2]))
            wifi_negotiate(conn, h, guard, case, phase)
            cleanup(conn, owned_auth=False, auth_services=False)
            return
        cleanup(conn, owned_auth=not terminal_auth_closed,
                remote_auth_closed=terminal_auth_closed)

    def serve():
        try:
            with daemon.accept()[0] as conn:
                conn.settimeout(6)
                h.drive_peer(conn, 'success', lambda s: step.__setitem__(0, s), auth_flow=flow)
        except Exception as error:
            label = safe_label(str(error)) if isinstance(error, AssertionError) else 'none'
            errors.append((step[0], safe_exception_name(error), label))
            phase('exception-' + safe_exception_name(error) + '-assertion-' + label)
        finally:
            phase('daemon-finished')

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        launch = subprocess.run(['xcrun', 'simctl', 'launch', args.udid, args.bundle_id,
                             'tcp:' + str(daemon.getsockname()[1]), 'Documents/' + guard.name,
                             'auth_' + case], capture_output=True, text=True, timeout=30)
        h.check(launch.returncode == 0, 'CID fixture launch')
        for _ in range(80):
            if result.exists():
                break
            time.sleep(.25)
        thread.join(8)
    finally:
        daemon.close()
        phone.close()
        h.preserve_case_evidence(documents, guard, 'fe36-cid-' + case)
        destination = h.ROOT / 'artifacts/scan-owner/simulator-cases' / ('fe36-cid-' + case)
        if (guard / 'proxy-phases.log').is_file():
            shutil.copyfile(guard / 'proxy-phases.log', destination / 'proxy-phases.log')
    h.check(not thread.is_alive() and not errors, 'CID daemon completed: ' + repr(errors))
    h.check(result.exists() and result.read_text().strip() == '0', 'CID production-code assertions ' + case)
    trace = (guard / 'scan-events').read_text()
    h.check('CID_ASSERT_FAIL=' not in trace, 'all named CID assertions passed')
    boundary = case in ('success', 'wifi_success', 'wifi_pending', 'wifi_duplicate', 'wifi_cleanup_failure')
    h.check(trace.count('TRUSTED_KEY_CALLBACK') == int(boundary), 'only bounded-auth or owned TCP boundary consumes key')
    h.check((guard / 'heartbeat').read_text() == 'POWER_DRIVER_OWNS_THIS\n', 'lease remains sole heartbeat owner')
    shutil.rmtree(guard)
    print('FE36_CID_TRANSPORT_AUTH_CASE_OK=' + case)


def run_all(args, harness):
    for case in CASES:
        run_case(args, harness, case)
    print('FE36_CID_TRANSPORT_AUTH_CASES_OK=' + str(len(CASES)))
    for case in WIFI_CASES:
        run_case(args, harness, case)
    print('FE36_NEARBY_TCP_TRANSPORT_CASES_OK=' + str(len(WIFI_CASES)))
