"""Portable regression for the FE36 negative-auth close command boundary."""
import importlib.util
import struct
import json
import socket
import tempfile
import threading
import contextlib
import io
from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path


source = Path(__file__).with_name("test-fe36-cid-simulator.py")
spec = importlib.util.spec_from_file_location("fe36_cid_simulator", source)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

cid = 0x3456
valid = struct.pack("<HBHB", 0xF441, 3, cid, 0)
assert module.consume_negative_auth_close(1, 0, valid, cid)

# The terminal command is consumed exactly once by the caller; malformed,
# wrong-CID, wrong-status, wrong-channel and extra-byte variants are not it
# and must remain available to strict cleanup parsing.
variants = (
    struct.pack("<HBHB", 0xF441, 3, cid ^ 1, 0),
    struct.pack("<HBHB", 0xF441, 3, cid, 1),
    valid + b"\x00",
    struct.pack("<HBHB", 0xF441, 2, cid, 0),
)
for body in variants:
    assert not module.consume_negative_auth_close(1, 0, body, cid)
assert not module.consume_negative_auth_close(1, 1, valid, cid)
assert not module.consume_negative_auth_close(7, 0, valid, cid)
print("FE36_NEGATIVE_TERMINAL_COMMAND_CHECKS=7")

def inform(code):
    return json.dumps({'oper_type': 3, 'data': json.dumps({
        'message': 0x8080, 'payload': {'errorCode': code}})}).encode()

for case, code in (('wrong_pin', 17), ('forged_signature', 29)):
    assert module.negative_inform(inform(code), case)
for body, case in ((inform(29), 'wrong_pin'), (inform(17), 'success'),
                   (inform(True), 'wrong_pin'), (b'[]', 'wrong_pin'),
                   (b'{', 'wrong_pin'), (b'{"oper_type":3,"data":"[]"}', 'wrong_pin')):
    try:
        module.negative_inform(body, case)
    except (AssertionError, ValueError, TypeError, KeyError):
        pass
    else:
        raise AssertionError('malformed/unexpected INFORM accepted')
acks = []
closed = module.acknowledge_negative_close((1, 0, valid), cid, lambda: acks.append(0x81))
assert closed and acks == [0x81]
for packet, duplicate in (((1, 0, valid), True), ((1, 0, valid + b'!'), False)):
    try:
        module.acknowledge_negative_close(packet, cid, lambda: acks.append(0x81), duplicate)
    except AssertionError:
        pass
    else:
        raise AssertionError('invalid/repeated ACK accepted')
assert acks == [0x81]
def failed_ack():
    raise OSError('synthetic ACK failure')
try:
    module.acknowledge_negative_close((1, 0, valid), cid, failed_ack)
except OSError:
    pass
else:
    raise AssertionError('ACK failure suppressed')

# Exercise the actual run_case proxy/cleanup code on Windows loopback sockets.
# Only Simulator launch, production daemon and phone crypto are substituted.
base_spec = importlib.util.spec_from_file_location('inbound', source.with_name('test-fe35-cli-inbound-simulator.py'))
base = importlib.util.module_from_spec(base_spec)
base_spec.loader.exec_module(base)
def loopback_negative(case, code, cleanup_failure=False):
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        errors, workers, observed = [], [], []
        def checked(condition, label):
            if not condition:
                raise AssertionError(label)
        def command(conn, ocf, params=b''):
            base.send_packet(conn, 1, 0, struct.pack('<HB', 0xf400 | ocf, len(params)) + params)
        def event(conn, code):
            kind, channel, body = base.read_packet(conn)
            checked(kind == 4 and channel == 0 and body[0] == code, 'expected typed event')
            return body[2:]
        def daemon_peer(port):
            with socket.create_connection(('127.0.0.1', port), timeout=3) as conn:
                event(conn, 0x82)
                command(conn, 0x44, struct.pack('<H', cid))
                event(conn, 0x80)
                exchanges = 3 if case == 'wrong_pin' else 4
                for index in range(exchanges):
                    request = bytearray()
                    while len(request) < 2:
                        kind, channel, body = base.read_packet(conn)
                        checked((kind, channel) == (7, cid), 'proxy request CID')
                        request.extend(body)
                    checked(request == b'{}', 'proxy request bytes')
                    response = inform(code) if index == exchanges - 1 else b'{"oper_type":1}'
                    for at in range(0, len(response), 17):
                        base.send_packet(conn, 7, cid, response[at:at + 17])
                command(conn, 0x41, struct.pack('<HB', cid, 0))
                checked(event(conn, 0x81) == struct.pack('<H', cid), 'exact close ACK')
                observed.append('ack-once')
                for ocf, params in ((0x31, struct.pack('<I', 0x10002)), (0x43, bytes([17, 0])), (1, b'')):
                    command(conn, ocf, params)
                if cleanup_failure:
                    observed.append('cleanup-failed')
                    return
                event(conn, 0x60)
                command(conn, 0x41, struct.pack('<HB', 0x2345, 0))
                event(conn, 0x81)
                for ocf, params in ((0x31, struct.pack('<I', 0x10001)), (0x43, bytes([16, 0])), (1, b'')):
                    command(conn, ocf, params)
                event(conn, 0x60)
                observed.append('cleanup-complete')
        def phone_peer(port):
            with socket.create_connection(('127.0.0.1', port), timeout=3) as conn:
                for index in range(3 if case == 'wrong_pin' else 4):
                    conn.sendall(struct.pack('!I', 2) + b'{}')
                    size, = struct.unpack('!I', base.exact(conn, 4))
                    reply = base.exact(conn, size)
                    if module.negative_inform(reply, case):
                        observed.append('phone-failed-no-key')
                        return
                raise AssertionError('missing INFORM')
        def start(fn, port):
            def run():
                try: fn(port)
                except Exception as error: errors.append(error)
            thread = threading.Thread(target=run)
            workers.append(thread);thread.start()
        def launch(argv, **_):
            guard = root / argv[-2]
            start(daemon_peer, int(argv[-3].split(':')[1]))
            start(phone_peer, int((guard / 'phone-port').read_text()))
            for thread in workers: thread.join(5)
            checked(not errors, 'loopback peer error: ' + repr(errors))
            checked(all(not thread.is_alive() for thread in workers), 'loopback bounded completion')
            (guard / 'scan-events').write_text('SYNTHETIC_PROXY_ONLY\n')
            (root / 'Documents/fe35-cli-result').write_text('0')
            return SimpleNamespace(returncode=0, stdout='synthetic: 12345\n')
        harness = SimpleNamespace(ROOT=root, check=checked, exact=base.exact, read_packet=base.read_packet,
            send_packet=base.send_packet, send_event=base.send_event, read_command=base.read_command,
            # This negative-auth-only substitute has no early inbound reads.
            drive_peer=lambda conn, case, phase, auth_flow, observe_packet=None, observe_early=None: auth_flow(conn))
        def preserve(documents, guard, label):
            (root / 'artifacts/scan-owner/simulator-cases' / label).mkdir(parents=True, exist_ok=True)
        harness.preserve_case_evidence = preserve
        with patch.object(module.subprocess, 'run', side_effect=launch), \
             patch.object(module, 'simulator_process_exited', return_value=True), \
             contextlib.redirect_stdout(io.StringIO()):
            try:
                module.run_case(SimpleNamespace(data_dir=folder, udid='synthetic', bundle_id='synthetic'), harness, case)
            except AssertionError as error:
                checked(cleanup_failure and isinstance(error, module.IsolatedCaseFailure) and
                        error.label == 'daemon-failure', 'unexpected proxy failure')
            else:
                checked(not cleanup_failure, 'cleanup failure hidden')
        assert observed.count('ack-once') == 1
        assert set(observed) == {'ack-once', 'cleanup-failed' if cleanup_failure else 'cleanup-complete', 'phone-failed-no-key'}

loopback_negative('wrong_pin', 17)
loopback_negative('forged_signature', 29)
loopback_negative('wrong_pin', 17, cleanup_failure=True)
print('FE36_NEGATIVE_INFORM_BOUNDARY_CHECKS=12')
print('FE36_NEGATIVE_INFORM_PROXY_CASES_OK=3;BOUNDARY=real-loopback-proxy-code-synthetic-peers-no-crypto')
