"""Actual production transport/owner/ObjC/Native auth; synthetic BTstack/phone.
Phone crypto is separately coded ObjC from upstream TestPhone, NOT a vendor peer.
Length-prefix proxy is only a fixture control channel; FE36 sees raw JSON bytes.
No frames, PIN, keys or identity values are included in assertion diagnostics.
"""
import json
import errno
import os
from pathlib import Path
import shutil
import socket
import struct
import subprocess
import threading
import time
import re
import sys

CASES = ('success', 'wrong_pin', 'forged_signature', 'wrong_peer', 'wrong_open_peer',
         'wrong_cid', 'control_cid_reuse', 'extra_connection', 'malformed_open',
         'wrong_data_cid', 'reopened_cid', 'wrong_listener',
         'control_close', 'auth_disconnect', 'auth_cid_close_failure',
         'auth_listener_barrier_failure', 'control_cid_close_failure',
         'final_cleanup_barrier_failure', 'stop', 'background', 'deadline', 'send_failure', 'cleanup_failure', 'pending_stop',
         'late_cleanup_data')
WIFI_CASES = ('wifi_success', 'wifi_pending', 'wifi_duplicate', 'wifi_stop', 'wifi_expiry',
              'wifi_malformed', 'wifi_unsupported', 'wifi_tcp_failure', 'wifi_disconnect',
              'wifi_cleanup_failure')
LIVE_CASES = ('wifi_live_disconnect', 'wifi_live_remote_close', 'wifi_live_peer_eof',
              'wifi_live_stop', 'wifi_live_background', 'wifi_live_owner_eof',
              'wifi_live_expiry', 'wifi_live_malformed', 'wifi_live_dmsdp_setup',
              'wifi_live_dmsdp_stop', 'wifi_live_dmsdp_malformed', 'wifi_live_dmsdp_duplicate')


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
        'handshake reply transport header': 'handshake-transport-shape',
        'handshake reply frame bytes': 'handshake-payload',
        'unterminated EA': 'nearby-ea',
        'command opcode': 'command-opcode',
        'command parameter length': 'command-parameter-length',
        'command parameters': 'command-parameters',
        'SDP UUID bytes': 'sdp-uuid',
        'SDP RFCOMM channel bytes': 'sdp-channel',
        'SDP protocol descriptor': 'sdp-protocol',
        'control SDP command': 'control-sdp-command',
        'FE35 service registration': 'control-service-registration',
        'bridge start transport header': 'bridge-start-transport',
        'bridge start frame bytes': 'bridge-start-frame',
        'auth SDP command': 'auth-sdp-command',
        'auth SDP UUID128 callback': 'auth-sdp-uuid',
        'listener response transport header': 'listener-response-transport',
        'encrypted command4 frame marker': 'command4-frame',
        'encrypted command4 plaintext bytes': 'command4-payload',
        'command4 TLV tag': 'command4-tlv',
        'command4 channel and business id': 'command4-channel-business',
        'command4 UUID bytes': 'command4-uuid',
        'actual common request is pending before network readiness': 'wifi-request-pending',
        'listener cannot start before confirmed negotiation': 'wifi-listener-premature',
        'owned TCP boundary is closed at bounded slice completion': 'wifi-tcp-close',
        'CID fixture launch': 'fixture-launch',
        'diagnostic capacity retained': 'diagnostic-capacity',
        'CID transport socket released': 'transport-socket-release',
        'complete handshake PAKE1 PAKE2 signed exchange': 'auth-exchange-complete',
        'negative auth terminal close acknowledged': 'auth-negative-close-ack',
        'pending verified candidate revoked before unacknowledged close': 'auth-pending-revoked',
        'bounded synthetic phone request': 'phone-request-bound',
        'positive pairing cannot terminate before reply': 'auth-positive-premature-terminal',
        'all named CID assertions passed': 'fixture-named-assertions',
        'auth disconnect native status retained': 'auth-cleanup-status',
        'one final native cleanup predicate': 'auth-cleanup-predicate-count',
        'native cleanup evidence matches injected case': 'auth-cleanup-evidence-match',
        'one typed auth disconnect completion': 'auth-completion-count',
        'auth disconnect remains a protocol failure': 'auth-protocol-failure',
        'typed cleanup matches independent native predicate': 'auth-cleanup-predicate-match',
        'guard delegation follows native cleanup certainty': 'auth-cleanup-delegation',
        'only bounded-auth or owned TCP boundary consumes key': 'key-delivery-count',
        'lease remains sole heartbeat owner': 'lease-heartbeat-owner',
        'auth envelope object required': 'auth-envelope-object',
        'auth message object required': 'auth-message-object',
        'unexpected auth INFORM terminal': 'auth-unexpected-inform',
        'exact one-shot auth close required': 'auth-close-one-shot',
        'live TCP frame header': 'tcp-header',
        'live TCP EA bound': 'tcp-ea-bound',
        'live TCP frame bound': 'tcp-frame-bound',
        'live TCP pinned connectId': 'tcp-connect-id',
        'live TCP pinned initiator': 'tcp-initiator',
        'live TCP encrypted business rejection': 'tcp-business-rejection',
        'live TCP encrypted disconnect ACK': 'tcp-disconnect-ack',
        'live TCP owned socket closed after terminal': 'tcp-terminal-close',
        'DMSDP resource response': 'dmsdp-resource-response',
        'DMSDP session negotiation response': 'dmsdp-session-response',
        'DMSDP plaintext OPTIONS': 'dmsdp-options',
        'DMSDP plaintext crypto ACK': 'dmsdp-crypto-ack',
        'DMSDP encrypted TCP keepalive': 'dmsdp-tcp-keepalive',
        'DMSDP owned endpoints close': 'dmsdp-endpoints-close',
        'DMSDP frame bound': 'dmsdp-frame-bound',
        'DMSDP device info response': 'dmsdp-device-info',
        'DMSDP encrypted time sync ACK': 'dmsdp-time-sync',
    }
    # Dynamic assertion families emit only fixed tokens, never their suffix.
    if value.startswith('CID daemon completed: '):
        return 'daemon-failure'
    if value.startswith('command header expected_ocf='):
        return 'command-header'
    if value in {'CID production-code assertions ' + c for c in CASES + WIFI_CASES + LIVE_CASES}:
        return 'fixture-result'
    if value in {'CID cleanup command component=' + hex(c) for c in (1, 0x31, 0x41, 0x43)}:
        return 'cleanup-command'
    return labels.get(value, 'unclassified')


class IsolatedCaseFailure(AssertionError):
    def __init__(self, label, exception='AssertionError'):
        self.label, self.exception = label, exception
        super().__init__('isolated case failed: ' + label)


class UnsafeCaseFailure(AssertionError):
    def __init__(self, label):
        self.label = label
        super().__init__('case isolation unproven: ' + label)


def simulator_pid(launch, bundle_id):
    # simctl reports its launched host process PID. Never parse arbitrary text
    # as a PID and never signal a process to obtain isolation.
    match = re.fullmatch(re.escape(bundle_id) + r': ([1-9][0-9]*)\s*', launch.stdout or '')
    if not match or int(match[1]) <= 1:
        raise UnsafeCaseFailure('launch-pid-unproven')
    return int(match[1])


def simulator_process_exited(pid):
    if sys.platform != 'darwin':
        raise UnsafeCaseFailure('host-process-observation-unavailable')
    try:
        os.kill(pid, 0)  # existence check only; Simulator processes run on host
    except OSError as error:
        if error.errno == errno.ESRCH:
            return True
        raise UnsafeCaseFailure('host-process-observation-failed') from error
    return False  # includes PID reuse: fail closed rather than assume exit


def safe_exception_name(error):
    known = {'AssertionError', 'EOFError', 'TimeoutError', 'error', 'IndexError',
             'ValueError', 'UnicodeError', 'struct.error'}
    name = type(error).__name__
    return name if name in known else 'other'


def observe_early_packet(branch, kind, channel, size, opcode, length, phase):
    # Fixed branch names and numeric fields only: no payload or exception text.
    if branch not in ('initial-state', 'control-listener', 'control-sdp',
                      'incoming-accept', 'bridge-start'):
        raise ValueError('unknown early packet branch')
    fields = (kind, channel, size, opcode, length)
    if any(value is not None and (type(value) is not int or not 0 <= value <= 65535)
           for value in fields):
        raise ValueError('invalid early packet metadata')
    phase('early-' + branch + '-kind-' + str(kind) + '-channel-' + str(channel) +
          '-size-' + str(size) + '-opcode-' + ('unavailable' if opcode is None else str(opcode)) +
          '-declared-length-' + ('unavailable' if length is None else str(length)))


def flush_proxy_evidence(guard, diagnostics, timings):
    # Called only after socket/thread teardown; no diagnostic disk IO in the
    # incoming/open critical path. Even early launch/protocol errors get a flush.
    failed = False
    for name, lines in (('proxy-phases.log', diagnostics), ('proxy-timing.log', timings)):
        try:
            (guard / name).write_text('\n'.join(lines) + '\n', encoding='ascii')
        except OSError:
            failed = True
    if failed:
        raise OSError('proxy-evidence-write-failed')


def observe_handshake_packet(kind, channel, body, crc16, phase):
    # Only fixed field names, numeric transport metadata and validation states.
    phase('handshake-packet-kind-' + str(kind) + '-channel-' + str(channel) +
          '-size-' + str(len(body)))
    if kind == 1 and len(body) >= 3:
        opcode, length = struct.unpack('<HB', body[:3])
        phase('handshake-command-opcode-' + str(opcode) + '-length-' + str(length) +
              '-exact-length-' + str(len(body) == length + 3).lower())
    if kind == 7:
        metadata = inspect_nearby_frame(body, crc16)
        phase('handshake-frame-' + '-'.join(str(k) + '-' + str(v).lower()
                                             for k, v in metadata.items()))


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
        if case in LIVE_CASES:
            live_control(tcp, conn, h, guard, case, cid, phase)
            return
        check(tcp.recv(1) == b'', 'owned TCP boundary is closed at bounded slice completion')


def read_tcp_frame(tcp, h):
    """Bounded actual Nearby stream framing; never render received bytes."""
    raw = bytearray(h.exact(tcp, 1))
    h.check(raw == b'\x7f', 'live TCP frame header')
    def ea():
        value = 0
        for i in range(4):
            byte = h.exact(tcp, 1)[0]; raw.append(byte)
            value |= (byte & 0x7f) << (7*i)
            if byte & 0x80:
                return value
        raise AssertionError('live TCP EA bound')
    ea(); ea(); flag_size = ea()
    h.check(flag_size <= 64, 'live TCP frame bound')
    raw.extend(h.exact(tcp, flag_size))
    size = ea(); h.check(size <= 65536, 'live TCP frame bound')
    raw.extend(h.exact(tcp, size+2))
    return h.decode_frame(bytes(raw))


def live_control(tcp, daemon, h, guard, case, control_cid, phase, receiver_key=None):
    tlv = lambda tag, value=b'': h.ea(tag)+h.ea(len(value))+value
    first = read_tcp_frame(tcp, h)
    h.check(first[:2] == (0, 0) and first[2].startswith(tlv(15)[:1]), 'live TCP pinned connectId')
    device = b'CD1C73F369C5FE0B80808D3D0335EAF7D99B2AB9FE15403DC621C166FBADCB6F'
    h.check(read_tcp_frame(tcp, h) == (0, 0, tlv(1,b'\x02')+tlv(3,device)+tlv(5,b'\x01')),
            'live TCP pinned initiator')
    # Actual upstream framing/cipher, deliberately fragmented then coalesced.
    def send(outer, payload):
        tcp.sendall(h.encrypted_frame(outer, payload, bytes.fromhex('e1e2e3e4e5e6e7e8')))
    handshake = tlv(2,b'\x02')+tlv(4,b'SYNTHETIC_PHONE')+tlv(6,b'\x01')
    raw = h.encrypted_frame(0, handshake, bytes.fromhex('f1f2f3f4f5f6f7f8'))
    tcp.sendall(raw[:3]);tcp.sendall(raw[3:])
    tag = b'SYNTHETIC'
    requests = b''.join(h.encrypted_frame(2, tlv(3,h.ea(3)+h.ea(b)+h.ea(len(tag))+tag+h.ea(1)),
        bytes.fromhex('c1c2c3c4c5c6c7c8')) for b in (19,20))
    tcp.sendall(requests)
    for business in (19,20):
        expected=tlv(4,h.ea(1)+h.ea(0)+h.ea(3)+h.ea(business)+h.ea(len(tag))+tag+h.ea(0))
        h.check(read_tcp_frame(tcp,h)==(2,1,expected),'live TCP encrypted business rejection')
    phase('live-tcp-handshake-and-encrypted-rejection-validated')
    if case.startswith('wifi_live_dmsdp_'):
        dmsdp_control(tcp,h,guard,case,phase,key=receiver_key)
        h.check(tcp.recv(1)==b'','live TCP owned socket closed after terminal')
        phase('live-dmsdp-terminal-closed')
        return
    if case == 'wifi_live_remote_close':
        h.send_event(daemon,0x81,struct.pack('<H',control_cid))
    if case in ('wifi_live_stop','wifi_live_background','wifi_live_owner_eof'):
        (guard / 'stop').write_text('STOP\n',encoding='ascii')
    elif case == 'wifi_live_peer_eof':
        tcp.shutdown(socket.SHUT_WR)
    elif case == 'wifi_live_malformed':
        raw = bytearray(h.encrypted_frame(2,tlv(3),bytes(8)));raw[-1]^=1;tcp.sendall(raw)
    elif case != 'wifi_live_expiry':
        send(33,tlv(5))
        h.check(read_tcp_frame(tcp,h)==(33,1,tlv(6)),'live TCP encrypted disconnect ACK')
    h.check(tcp.recv(1)==b'','live TCP owned socket closed after terminal')
    phase('live-tcp-terminal-closed')


def dmsdp_control(tcp,h,guard,case,phase,key=None):
    tlv=lambda tag,value=b'':h.ea(tag)+h.ea(len(value))+value
    request=tlv(3,h.ea(3)+h.ea(20)+h.ea(5)+b'DMSDP'+h.ea(1))
    tcp.sendall(h.encrypted_frame(4,request,bytes.fromhex('a1a2a3a4a5a6a7a8')))
    outer,encrypted,response=read_tcp_frame(tcp,h)
    tag,at=h.read_ea(response,0);size,at=h.read_ea(response,at)
    status,at=h.read_ea(response,at);port,at=h.read_ea(response,at)
    expected=tlv(4,h.ea(0)+h.ea(port)+h.ea(3)+h.ea(20)+h.ea(5)+b'DMSDP'+h.ea(1))
    h.check((outer,encrypted,tag,status)==(4,1,4,0) and 0<port<=65535 and response==expected,'DMSDP resource response')
    # Closing Nearby must retain actual DMSDP listeners and the same original owner.
    tcp.shutdown(socket.SHUT_WR)
    with socket.create_connection(('127.0.0.1',port),timeout=4) as session:
        session.settimeout(4)
        body=b'\x7f\x81\x90'+bytes(16);crc=h.crc16_arc(body)
        frame=body+struct.pack('<H',crc)
        if case=='wifi_live_dmsdp_malformed':
            session.sendall(frame[:-1]+bytes([frame[-1]^1]))
            h.check(session.recv(1)==b'','DMSDP owned endpoints close');return
        session.sendall(frame[:5]);session.sendall(frame[5:])
        reply=h.exact(session,21)
        control_port=struct.unpack('!H',reply[4:6])[0]
        expected=b'\x7f\x81\x90\x00'+struct.pack('!H',control_port)+bytes(13)
        h.check(0<control_port<=65535 and reply==expected+struct.pack('<H',h.crc16_arc(expected)),'DMSDP session negotiation response')
        if case=='wifi_live_dmsdp_duplicate':
            with socket.create_connection(('127.0.0.1',port),timeout=4) as duplicate:
                h.check(duplicate.recv(1)==b'','DMSDP owned endpoints close')
            h.check(session.recv(1)==b'','DMSDP owned endpoints close');return
        session.shutdown(socket.SHUT_WR)
        def read_control(control):
            head=h.exact(control,3);size=struct.unpack('!H',head[1:])[0]
            h.check(0<size<=65535,'DMSDP frame bound')
            return head[0],h.exact(control,size)
        with socket.create_connection(('127.0.0.1',control_port),timeout=4) as control:
            control.settimeout(4)
            options=b'OPTIONS * DMSDP/1.0\r\nCryptoVer: 1\r\nCryptoAbility: 222\r\nCryptoAlg: aes128-ctr\r\nUdpKA: 0\r\nKaRetry: 160\r\nLowDelay: 1\r\nCSeq: 1\r\n\r\n'
            h.check(read_control(control)==(0,options),'DMSDP plaintext OPTIONS')
            if case=='wifi_live_dmsdp_stop':
                (guard/'stop').write_text('STOP\n',encoding='ascii')
            else:
                selection=b'SET_PARAMETER * DMSDP/1.0\r\nCSeq: 2\r\nCryptoVer: 1\r\nCryptoSwitch: 222\r\nCryptoAlg: aes128-ctr\r\nUdpKA: 0\r\n\r\n'
                control.sendall(b'\x00'+struct.pack('!H',len(selection))+selection)
                ack=b'DMSDP/1.0 200 OK\r\nCSeq: 2\r\nCryptoVer: 1\r\nCryptoSwitch: 222\r\nCryptoAlg: aes128-ctr\r\nPlatform: 0\r\n\r\n'
                h.check(read_control(control)==(0,ack),'DMSDP plaintext crypto ACK')
                if key is not None:
                    # Independent OpenSSL peer; synthetic JVM key only, no Native key export.
                    iv=bytes(range(16));text=b'GET_PARAMETER * DMSDP/1.0\r\nCSeq: 3\r\n\r\n'
                    def ctr(data,nonce):
                        result=subprocess.run(['openssl','enc','-aes-128-ctr','-K',key.hex(),'-iv',nonce.hex()],input=data,capture_output=True,check=True)
                        return result.stdout
                    sealed=iv+ctr(text,iv);control.sendall(b'\xab'+struct.pack('!H',len(sealed))+sealed)
                    flag,payload=read_control(control)
                    h.check(flag==0xab and ctr(payload[16:],payload[:16])==b'GET_PARAMETER * DMSDP/1.0\r\nCSeq: 2\r\n\r\n','DMSDP encrypted TCP keepalive')
                    def send_payload(data,number):
                        nonce=bytes([number])*16;sealed=nonce+ctr(data,nonce)
                        control.sendall(b'\xab'+struct.pack('!H',len(sealed))+sealed)
                    def record(module,data):
                        return b'$'+struct.pack('!IiH',module,-1,len(data))+data
                    # Existing authorized synthetic identity; no Native key export.
                    info=h.ea(101)+json.dumps({'deviceId':'SYNTHETIC_PHONE','deviceType':3},separators=(',',':')).encode()
                    send_payload(record(3,info)+record(3,h.ea(104)+struct.pack('!I',0xffffffff)),2)
                    flag,payload=read_control(control);plain=ctr(payload[16:],payload[:16])
                    command,at=h.read_ea(plain,11)
                    expected={'deviceId':'CD1C73F369C5FE0B80808D3D0335EAF7D99B2AB9FE15403DC621C166FBADCB6F',
                        'deviceName':'Synthetic','deviceType':4,'bluetoothMac':'A0:B1:C2:D3:E4:F5','btName':'Synthetic',
                        'localIp':'127.0.0.1','remoteIp':'127.0.0.1','port':-1,'businessId':1,'properties':{'2003':'A1B2C3D4'}}
                    h.check(flag==0xab and plain[:1]==b'$' and struct.unpack('!IiH',plain[1:11])==(3,-1,len(plain)-11)
                        and command==101 and json.loads(plain[at:])==expected,'DMSDP device info response')
                    sync=b'SET_PARAMETER * DMSDP/1.0\r\nTimeServerPort: 1234\r\nTimeUsHigh: 1\r\nTimeUsLow: -1\r\nCSeq: 8\r\n\r\n'
                    # Duplicate101/empty104 produce no echo; next output is sync ACK.
                    send_payload(record(3,info),3);send_payload(sync,4)
                    flag,payload=read_control(control)
                    h.check(flag==0xab and ctr(payload[16:],payload[:16])==b'DMSDP/1.0 200 OK\r\nCSeq: 8\r\n\r\n','DMSDP encrypted time sync ACK')
                    send_payload(record(5,h.ea(101)+h.ea(7236)),5)
                control.shutdown(socket.SHUT_WR)
            h.check(control.recv(1)==b'','DMSDP owned endpoints close')
        h.check(session.recv(1)==b'','DMSDP owned endpoints close')
    phase('dmsdp-listener-session-control-lifecycle-validated')


def consume_negative_auth_close(kind, channel, body, auth_cid):
    """Recognize exactly one production auth-CID close command.

    read_packet returns the complete command body: opcode (u16), parameter
    length (u8), then CID (u16) and status (u8). Malformed or unrelated
    commands stay in the pending queue for strict cleanup parsing.
    """
    expected = struct.pack('<HBHB', 0xf441, 3, auth_cid, 0)
    return kind == 1 and channel == 0 and body == expected


def require_cleanup_command(packet, ocf, params, check, phase):
    kind, channel, body = packet
    if kind == 1 and len(body) >= 3:
        opcode, length = struct.unpack('<HB', body[:3])
        phase('received-command-' + hex(opcode) + '-length-' + str(length))
    check((kind, channel, body) == (1, 0, struct.pack('<HB', 0xf400 | ocf, len(params)) + params),
          'CID cleanup command component=' + hex(ocf))


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


def _run_case(args, h, case, isolation):
    documents = Path(args.data_dir) / 'Documents'
    guard = documents / ('auth-cid-' + case)
    if guard.exists():
        raise UnsafeCaseFailure('preexisting-case-directory')
    guard.mkdir(parents=True)
    (guard / 'ready').write_text('READY\n', encoding='ascii')
    (guard / 'deadline').write_text(str(int(time.time()) + 120), encoding='ascii')
    (guard / 'heartbeat').write_text('POWER_DRIVER_OWNS_THIS\n', encoding='ascii')
    result = documents / 'fe35-cli-result'
    result.unlink(missing_ok=True)
    (documents / 'fe35-cli-status.log').unlink(missing_ok=True)
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
    timings = []
    diagnostic_overflow = [False]
    def phase(label):
        step[0] = label
        if diagnostics and diagnostics[-1] == label:
            return
        if len(diagnostics) >= 4095:
            if not diagnostic_overflow[0]:
                diagnostic_overflow[0] = True
                diagnostics.append('diagnostic-capacity-exceeded')
                timings.append(str(time.monotonic_ns()) + ' diagnostic-capacity-exceeded')
            return
        diagnostics.append(label)
        timings.append(str(time.monotonic_ns()) + ' ' + label)
    pending = []
    socket_lock = threading.Lock()
    sockets, closing = [daemon, phone], [False]

    def accept(listener):
        accepted = listener.accept()[0]
        with socket_lock:
            if closing[0]:
                accepted.close()
                raise UnsafeCaseFailure('accept-after-case-close')
            sockets.append(accepted)
        return accepted
    auth_cid, control_cid = 0x3456, 0x2345
    peer = bytes.fromhex('a1a2a3a4a5a6')

    def packet(conn):
        return pending.pop(0) if pending else h.read_packet(conn)

    def command(conn, ocf, params):
        phase('cleanup-command-' + hex(ocf))
        require_cleanup_command(packet(conn), ocf, params, h.check, phase)

    def reset_cleanup_peer(conn):
        conn.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack('ii', 1, 0))
        conn.close()

    def cleanup(conn, owned_auth=True, remote_auth_closed=False, auth_services=True):
        step[0] = 'typed_cleanup'
        if owned_auth and not remote_auth_closed:
            command(conn, 0x41, struct.pack('<HB', auth_cid, 0))
            if case == 'auth_cid_close_failure':
                reset_cleanup_peer(conn)
                return
            if case == 'pending_stop':
                (guard / 'stop').write_text('STOP\n', encoding='ascii')
                h.check(conn.recv(1) == b'', 'pending verified candidate revoked before unacknowledged close')
                return
            h.send_event(conn, 0x81, struct.pack('<H', auth_cid))
        if auth_services:
            command(conn, 0x31, struct.pack('<I', 0x10002))
            command(conn, 0x43, bytes([17, 0]))
            command(conn, 1, b'')
            if case == 'auth_listener_barrier_failure':
                reset_cleanup_peer(conn)
                return
            h.send_event(conn, 0x60, bytes([2]))
        if case != 'wifi_live_remote_close':
            command(conn, 0x41, struct.pack('<HB', control_cid, 0))
            if case == 'control_cid_close_failure':
                reset_cleanup_peer(conn)
                return
        if case == 'late_cleanup_data':
            # A real crypto candidate exists; this unexpected FE35 payload
            # before the close ACK must revoke it, never be silently skipped.
            h.send_packet(conn, 7, control_cid, b'{}')
        if case != 'wifi_live_remote_close':
            h.send_event(conn, 0x81, struct.pack('<H', control_cid))
        command(conn, 0x31, struct.pack('<I', 0x10001))
        command(conn, 0x43, bytes([16, 0]))
        command(conn, 1, b'')
        if case == 'final_cleanup_barrier_failure':
            reset_cleanup_peer(conn)
            return
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
        if case in ('auth_disconnect', 'auth_listener_barrier_failure',
                    'control_cid_close_failure', 'final_cleanup_barrier_failure'):
            h.send_event(conn, 0x81, struct.pack('<H', auth_cid))
            cleanup(conn, remote_auth_closed=True)
            return
        if case == 'auth_cid_close_failure':
            h.send_packet(conn, 7, auth_cid, bytes(38))
            cleanup(conn)
            return
        if case in ('stop', 'background', 'deadline'):
            phase('cancellation-request-' + case if case != 'deadline' else
                  'cancellation-await-original-deadline')
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
        with accept(phone) as peer_socket:
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
            h.check(case not in ('success',) + WIFI_CASES + LIVE_CASES or exchange == 3,
                    'complete handshake PAKE1 PAKE2 signed exchange')
        if case in ('wrong_pin', 'forged_signature'):
            h.check(terminal_auth_closed, 'negative auth terminal close acknowledged')
        if case in WIFI_CASES + LIVE_CASES:
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
            with accept(daemon) as conn:
                conn.settimeout(6)
                h.drive_peer(conn, 'success', phase, auth_flow=flow,
                             observe_packet=lambda k, c, b: observe_handshake_packet(
                                 k, c, b, h.crc16_arc, phase),
                             observe_early=lambda branch, k, c, s, o, n: observe_early_packet(
                                 branch, k, c, s, o, n, phase))
        except Exception as error:
            label = safe_label(str(error)) if isinstance(error, AssertionError) else 'none'
            errors.append((step[0], safe_exception_name(error), label))
            phase('exception-' + safe_exception_name(error) + '-assertion-' + label)
        finally:
            phase('daemon-finished')

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    pid = None
    try:
        launch = subprocess.run(['xcrun', 'simctl', 'launch', args.udid, args.bundle_id,
                             'tcp:' + str(daemon.getsockname()[1]), 'Documents/' + guard.name,
                             'auth_' + case], capture_output=True, text=True, timeout=30)
        h.check(launch.returncode == 0, 'CID fixture launch')
        pid = simulator_pid(launch, args.bundle_id)
        for _ in range(80):
            if simulator_process_exited(pid):
                break
            time.sleep(.25)
    finally:
        try:
            join_deadline = time.monotonic() + 8
            try:
                process_already_exited = pid is not None and simulator_process_exited(pid)
            except UnsafeCaseFailure:
                process_already_exited = False
                isolation['process_observation_failed'] = True
                isolation['failure_label'] = 'host-process-observation-failed'
            if process_already_exited:
                # Let a normal EOF/last ACK finish naturally before teardown.
                # The same original eight-second join budget bounds both paths.
                thread.join(max(0, join_deadline - time.monotonic()))
            with socket_lock:
                closing[0] = True
                for sock in sockets:
                    try:
                        sock.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass
                    sock.close()
            thread.join(max(0, join_deadline - time.monotonic()))
            isolation['thread_stopped'] = not thread.is_alive()
            try:
                isolation['process_exited'] = pid is not None and simulator_process_exited(pid)
            except UnsafeCaseFailure:
                isolation['process_exited'] = False
                isolation['process_observation_failed'] = True
                isolation['failure_label'] = 'host-process-observation-failed'
            isolation['safe'] = isolation['thread_stopped'] and isolation['process_exited']
        finally:
            try:
                flush_proxy_evidence(guard, list(diagnostics), list(timings))
            finally:
                h.preserve_case_evidence(documents, guard, 'fe36-cid-' + case)
                destination = h.ROOT / 'artifacts/scan-owner/simulator-cases' / ('fe36-cid-' + case)
                for name in ('proxy-phases.log', 'proxy-timing.log'):
                    if (guard / name).is_file():
                        shutil.copyfile(guard / name, destination / name)
    if not isolation.get('safe'):
        raise UnsafeCaseFailure(isolation.get('failure_label', 'process-or-daemon-still-live'))
    h.check(not diagnostic_overflow[0], 'diagnostic capacity retained')
    h.check(not thread.is_alive() and not errors, 'CID daemon completed: ' + repr(errors))
    h.check(result.exists() and result.read_text().strip() == '0', 'CID production-code assertions ' + case)
    trace = (guard / 'scan-events').read_text()
    h.check('CID_ASSERT_FAIL=' not in trace, 'all named CID assertions passed')
    expected_cleanup_facts = {
        'auth_disconnect': (1, 1, 0, 0, 1, 1, 1, 1, 1, 0),
        'auth_cid_close_failure': (0, 1, 0, 0, 1, 1, 0, 1, 0, 5),
        'auth_listener_barrier_failure': (0, 1, 0, 0, 1, 1, 0, 1, 1, 3),
        'control_cid_close_failure': (0, 1, 0, 0, 1, 1, 0, 1, 1, 7),
        'final_cleanup_barrier_failure': (0, 1, 0, 0, 1, 1, 1, 1, 1, 10),
    }
    if case in expected_cleanup_facts:
        status = guard.parent / 'fe35-cli-status.log'
        h.check(status.is_file(), 'auth disconnect native status retained')
        facts = re.findall(r'^BTSTACK_FE35_INBOUND_CLEANUP_FACTS=(\d+),(\d+),(\d+),(\d+),(\d+),(\d+),(\d+),(\d+),(\d+),(\d+)$',
                           status.read_text(errors='replace'), re.MULTILINE)
        h.check(len(facts) == 1, 'one final native cleanup predicate')
        h.check(tuple(map(int, facts[0])) == expected_cleanup_facts[case],
                'native cleanup evidence matches injected case')
        completion = re.findall(r'^CID_COMPLETION=(\d+),(\d+),(\d+),(\d+)$', trace, re.MULTILINE)
        h.check(len(completion) == 1, 'one typed auth disconnect completion')
        returned, confirmed, status_code, delegated = map(int, completion[0])
        h.check(returned == 1 and status_code == 1, 'auth disconnect remains a protocol failure')
        expected_cleanup = expected_cleanup_facts[case][0] == 1
        h.check(bool(confirmed) == expected_cleanup, 'typed cleanup matches independent native predicate')
        h.check(bool(delegated) == (not expected_cleanup), 'guard delegation follows native cleanup certainty')
    boundary = case in ('success', 'wifi_success', 'wifi_pending', 'wifi_duplicate', 'wifi_cleanup_failure')
    h.check(trace.count('TRUSTED_KEY_CALLBACK') == int(boundary), 'only bounded-auth or owned TCP boundary consumes key')
    h.check((guard / 'heartbeat').read_text() == 'POWER_DRIVER_OWNS_THIS\n', 'lease remains sole heartbeat owner')
    shutil.rmtree(guard)
    print('FE36_CID_TRANSPORT_AUTH_CASE_OK=' + case)


def run_case(args, h, case):
    isolation = {'safe': False, 'process_exited': False, 'thread_stopped': False}
    outcome = 'unsafe'
    label = 'case-interrupted'
    exception = 'none'
    try:
        _run_case(args, h, case, isolation)
        outcome, label = 'passed', 'none'
        return True
    except Exception as error:
        exception = safe_exception_name(error)
        if isinstance(error, UnsafeCaseFailure):
            label = error.label
        else:
            label = safe_label(str(error)) if isinstance(error, AssertionError) else 'case-exception'
        if isolation['safe'] and isinstance(error, AssertionError) and not isinstance(error, UnsafeCaseFailure):
            outcome = 'failed'
            raise IsolatedCaseFailure(label, exception) from error
        raise UnsafeCaseFailure(label) from error
    finally:
        destination = h.ROOT / 'artifacts/scan-owner/simulator-cases' / ('fe36-cid-' + case)
        destination.mkdir(parents=True, exist_ok=True)
        (destination / 'case-outcome.json').write_text(json.dumps({
            'case': case, 'outcome': outcome, 'label': label,
            'exception': exception, 'isolation': isolation}, sort_keys=True) + '\n', encoding='ascii')
        h.preserve_case_evidence(Path(args.data_dir) / 'Documents',
                                 Path(args.data_dir) / 'Documents' / ('auth-cid-' + case),
                                 'fe36-cid-' + case)


def run_all(args, harness, runner=None):
    runner = run_case if runner is None else runner
    matrix = [{'case': case, 'outcome': 'unrun', 'label': 'not-started'}
              for case in CASES + WIFI_CASES + LIVE_CASES]
    destination = harness.ROOT / 'artifacts/scan-owner/simulator-cases'
    destination.mkdir(parents=True, exist_ok=True)
    try:
        for entry in matrix:
            try:
                if runner(args, harness, entry['case']) is not True:
                    raise UnsafeCaseFailure('missing-isolation-certificate')
                entry.update(outcome='passed', label='none')
            except IsolatedCaseFailure as error:
                entry.update(outcome='failed', label=error.label, exception=error.exception)
            except Exception as error:
                entry.update(outcome='unsafe', label=error.label if isinstance(error, UnsafeCaseFailure)
                             else 'setup-or-unproven-isolation', exception=safe_exception_name(error))
                break
    finally:
        (destination / 'fe36-matrix.json').write_text(json.dumps(matrix, indent=2) + '\n', encoding='ascii')
        for entry in matrix:
            print('FE36_CASE_OUTCOME=' + entry['case'] + ':' + entry['outcome'] + ':' + entry['label'])
    if any(entry['outcome'] != 'passed' for entry in matrix):
        raise AssertionError('FE36 matrix incomplete or failed; see fe36-matrix.json')
    print('FE36_CID_TRANSPORT_AUTH_CASES_OK=' + str(len(CASES)))
    print('FE36_NEARBY_TCP_TRANSPORT_CASES_OK=' + str(len(WIFI_CASES)))
    print('FE36_LIVE_TCP_CONTROL_CASES_OK=' + str(len(LIVE_CASES)))
