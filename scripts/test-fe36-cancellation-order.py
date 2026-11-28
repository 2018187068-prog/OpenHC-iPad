"""Real harness parser on sockets; synthetic peer, no Native/runtime claim."""
import importlib.util
from pathlib import Path
import socket
import struct
import threading
import unittest
from unittest.mock import patch

root = Path(__file__).resolve().parent
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, root / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
wire = load('cancel_wire', 'test-fe35-cli-inbound-simulator.py')
cid = load('cancel_cid', 'test-fe36-cid-simulator.py')

def frame(payload):
    body = b'\x7f' + wire.ea(0) + wire.ea(0) + wire.ea(0) + wire.ea(len(payload)) + payload
    return body + struct.pack('<H', wire.crc16_arc(body))

class CancellationOrdering(unittest.TestCase):
    def drive_handshake(self, reply):
        phases, failures, auth_calls = [], [], []
        left, right = socket.socketpair()
        left.settimeout(2); right.settimeout(2)
        def drive():
            try:
                wire.drive_peer(left, 'success', phases.append,
                    auth_flow=lambda _: auth_calls.append(True),
                    observe_packet=lambda k,c,b: cid.observe_handshake_packet(k,c,b,wire.crc16_arc,phases.append))
            except Exception as error:
                failures.append(error)
        # Crypto request bytes do not matter to this synthetic daemon. Keep
        # actual socket packet/parser and production harness assertions intact.
        with patch.object(wire, 'encrypted_command_request', return_value=b'synthetic-request'):
            thread = threading.Thread(target=drive); thread.start()
            try:
                def command(ocf,params):
                    wire.send_packet(right,1,0,struct.pack('<HB',0xf400|ocf,len(params))+params)
                command(1,b''); wire.read_packet(right)
                command(0x42,bytes([16,0,2]));wire.read_packet(right)
                command(0x30,b'\x19\xfe\x35\x08\x10\x09\x00\x04\x35\x0c')
                wire.read_packet(right)
                wire.read_packet(right)  # incoming event
                command(0x44,struct.pack('<H',0x2345));wire.read_packet(right)
                wire.send_packet(right,7,0x2345,frame(b'start'))
                wire.read_packet(right);wire.read_packet(right)
                wire.send_packet(right,*reply)
                thread.join(2)
                self.assertFalse(thread.is_alive())
            finally:
                left.close(); right.close(); thread.join(2)
        return phases, failures, auth_calls

    def test_early_close_is_not_accepted_as_handshake_or_background(self):
        close=struct.pack('<HBHB',0xf441,3,0x2345,0)
        phases,errors,auth=self.drive_handshake((1,0,close))
        self.assertEqual(len(errors),1)
        self.assertEqual(str(errors[0]),'handshake reply transport header')
        self.assertFalse(auth)
        self.assertIn('handshake-command-opcode-62529-length-3-exact-length-true',phases)

    def test_wrong_frame_payload_is_distinct_and_never_cancels(self):
        phases,errors,auth=self.drive_handshake((7,0x2345,frame(b'wrong')))
        self.assertEqual(len(errors),1)
        self.assertEqual(str(errors[0]),'handshake reply frame bytes')
        self.assertFalse(auth)
        self.assertIn('encrypted_handshake_response',phases)

    def test_cleanup_parser_ack_order_and_strict_rejection(self):
        for ocf, params in ((0x41,struct.pack('<HB',0x3456,0)),
                            (0x31,struct.pack('<I',0x10002)),(0x43,bytes([17,0])),(1,b'')):
            left,right = socket.socketpair()
            try:
                body=struct.pack('<HB',0xf400|ocf,len(params))+params
                wire.send_packet(left,1,0,body)
                cid.require_cleanup_command(wire.read_packet(right),ocf,params,wire.check,lambda _:None)
                for malformed in (body+b'x',body[:-1],bytes([body[0]^1])+body[1:]):
                    wire.send_packet(left,1,0,malformed)
                    with self.assertRaises(AssertionError):
                        cid.require_cleanup_command(wire.read_packet(right),ocf,params,wire.check,lambda _:None)
            finally:
                left.close();right.close()

    def test_handshake_metadata_redaction_and_labels(self):
        phases=[]
        marker=b'NEVER_PERSIST_SECRET'
        for packet in ((1,0,struct.pack('<HBHB',0xf441,3,0x2345,0)),
                       (7,0x2345,frame(marker)),(7,0x2345,b'bad'+marker)):
            cid.observe_handshake_packet(*packet,wire.crc16_arc,phases.append)
        self.assertNotIn(marker.decode(),repr(phases))
        self.assertIn('handshake-command-opcode-62529-length-3-exact-length-true',phases)
        self.assertEqual(cid.safe_label('handshake reply transport header'),'handshake-transport-shape')
        self.assertEqual(cid.safe_label('handshake reply frame bytes'),'handshake-payload')
        self.assertEqual(cid.safe_label(marker.decode()),'unclassified')

if __name__ == '__main__':
    unittest.main()
