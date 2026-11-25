"""New transport metadata slice only; synthetic streams, no live endpoints."""
import importlib.util
from pathlib import Path
import struct
import time
import unittest

spec = importlib.util.spec_from_file_location('metadata', Path(__file__).with_name('btstack-transport-metadata.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class Stream:
    def __init__(self, data):
        self.data = data
        self.consumed = 0

    def settimeout(self, timeout):
        assert 0 < timeout <= 1

    def recv(self, size):
        # Force fragmentation even across the six-byte header.
        result = self.data[self.consumed:self.consumed + min(size, 1)]
        self.consumed += len(result)
        return result


def frame(body, kind=4, channel=0):
    return struct.pack('<HHH', kind, channel, len(body)) + body


def opened(server=23, cid=0x1234, status=0, incoming=1):
    # Independent construction from format 1B21221 and event accessors.
    payload = bytes([status]) + bytes.fromhex('010203040506') + struct.pack('<H', 0x5678)
    payload += bytes([server]) + struct.pack('<HH', cid, 512)
    if incoming is not None:
        payload += bytes([incoming])
    return bytes([0x80, len(payload)]) + payload


class MetadataTests(unittest.TestCase):
    def read(self, data):
        return module.MetadataReader(Stream(data)).receive(time.monotonic() + 1)

    def test_fragmented_open_and_dynamic_channels(self):
        for server in (3, 23, 30):
            result = self.read(frame(opened(server)))
            self.assertEqual(result, {'event': 0x80, 'status': 0, 'server_channel': server,
                                     'cid': 0x1234, 'mtu': 512, 'incoming': 1})
            self.assertNotIn('address', result)

    def test_short_failure_has_unknown_direction(self):
        result = self.read(frame(opened(status=0x56, incoming=None)))
        self.assertIsNone(result['incoming'])
        with self.assertRaisesRegex(ValueError, 'OPEN_RANGE'):
            self.read(frame(opened(incoming=None)))

    def test_reference_length_discrepancy_fails_closed(self):
        # rfcomm.c:265-277 allocates 18, advertises 16 parameter bytes,
        # but calls the handler with pos=17. Do not silently normalize it.
        body = bytearray(opened())
        body[1] = 16
        with self.assertRaisesRegex(ValueError, 'EVENT_SHAPE'):
            self.read(frame(body))

    def test_reference_daemon_cid_offset_discrepancy(self):
        body = opened(cid=0x1234)
        self.assertEqual(struct.unpack_from('<H', body, 12)[0], 0x1234)
        self.assertNotEqual(struct.unpack_from('<H', body, 13)[0], 0x1234)
        self.assertEqual(self.read(frame(body))['cid'], 0x1234)

    def test_close_reopen_uses_new_cid(self):
        stream = Stream(frame(opened(cid=0x1234)) + frame(bytes([0x81, 2, 0x34, 0x12])) +
                        frame(opened(cid=0x2468)))
        reader = module.MetadataReader(stream)
        results = [reader.receive(time.monotonic() + 1) for _ in range(3)]
        self.assertEqual([r['cid'] for r in results], [0x1234, 0x1234, 0x2468])

    def test_security_parameters_never_read(self):
        for code in (0x16, 0x17, 0x18, 0x31, 0x32, 0x33, 0x34, 0x35, 0x36):
            stream = Stream(frame(bytes([code, 6]) + b'mock!!'))
            with self.assertRaisesRegex(ValueError, 'PARAMETERS_NOT_READ'):
                module.MetadataReader(stream).receive(time.monotonic() + 1)
            self.assertEqual(stream.consumed, 8)

    def test_rfcomm_payload_never_read(self):
        stream = Stream(frame(b'synthetic', kind=7, channel=0x1234))
        with self.assertRaisesRegex(ValueError, 'DISALLOWED_METADATA_FRAME'):
            module.MetadataReader(stream).receive(time.monotonic() + 1)
        self.assertEqual(stream.consumed, 6)

    def test_malformed_size_eof_and_deadline(self):
        for data in (frame(b'\x81\x03\x01\x00'), b'\x04',
                     struct.pack('<HHH', 4, 0, 1025), frame(opened(server=0))):
            with self.assertRaises(ValueError):
                self.read(data)
        with self.assertRaises(TimeoutError):
            module.MetadataReader(Stream(b'')).receive(time.monotonic() - 1)

    def test_total_event_limit(self):
        reader = module.MetadataReader(Stream(frame(b'\x60\x01\x00') * 257))
        for _ in range(256):
            reader.receive(time.monotonic() + 1)
        with self.assertRaisesRegex(ValueError, 'EVENT_LIMIT'):
            reader.receive(time.monotonic() + 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
