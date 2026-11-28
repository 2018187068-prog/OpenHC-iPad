"""Redaction and failure-label regression for FE36 Nearby Simulator diagnostics."""
import importlib.util
from pathlib import Path
import socket
import struct
import threading
import unittest

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
