"""Synthetic Mach-O fixtures only; no credentials, device, or Apple tools."""
import importlib.util
from pathlib import Path
import hashlib
import struct
import unittest

spec = importlib.util.spec_from_file_location('audit', Path(__file__).with_name('audit-role-binary.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def fixture(platform=2, minos=0xf0000, extra_slot=None):
    sigstart = 4096
    # Empty requirements blob with one hash slot in each CodeDirectory.
    requirements = struct.pack('>III', 0xfade0c01, 12, 0)
    def directory(payload, kind):
        digest = hashlib.sha1 if kind == 1 else hashlib.sha256
        width = digest().digest_size
        hash_offset = 96 + width * 2
        blob = bytearray(hash_offset + width)
        struct.pack_into('>9I4B', blob, 0, 0xfade0c02, len(blob), 0x20400, 0,
                         hash_offset, 88, 2, 1, sigstart, width, kind, 0, 12)
        struct.pack_into('>QQQ', blob, 64, 0, sigstart, 1)
        blob[88:93] = b'test\0'
        blob[96:96 + width] = digest(requirements).digest()
        blob[hash_offset:] = digest(payload).digest()
        return bytes(blob)
    # Lengths are independent of hashes, so calculate signature size first.
    placeholder = bytes(sigstart)
    items = [(0, directory(placeholder, 1)), (2, requirements),
             (0x1000, directory(placeholder, 2))]
    if extra_slot:
        items.append((extra_slot, struct.pack('>II', 0xfade7171, 8)))
    sigsize = 12 + len(items) * 8 + sum(len(blob) for _, blob in items)
    dylib_name = b'/usr/lib/libSystem.B.dylib\0'
    dylib_length = (24 + len(dylib_name) + 7) // 8 * 8
    commands = [struct.pack('<6I', 0x32, 24, platform, minos, 0x120500, 0),
                struct.pack('<IIQQ', 0x80000028, 24, 512, 0),
                struct.pack('<6I', 0xc, dylib_length, 24, 0, 0, 0) +
                dylib_name.ljust(dylib_length - 24, b'\0'),
                struct.pack('<4I', 0x1d, 16, sigstart, sigsize)]
    payload = (struct.pack('<8I', 0xfeedfacf, 0x100000c, 0, 2, len(commands),
                           sum(map(len, commands)), 0, 0) + b''.join(commands)).ljust(sigstart, b'\0')
    items[0] = (0, directory(payload, 1))
    items[2] = (0x1000, directory(payload, 2))
    offset = 12 + len(items) * 8
    indices, blobs = [], []
    for slot, blob in items:
        indices.append(struct.pack('>II', slot, offset))
        blobs.append(blob)
        offset += len(blob)
    return payload + struct.pack('>III', 0xfade0cc0, sigsize, len(items)) + b''.join(indices + blobs)


class AuditTests(unittest.TestCase):
    def test_valid_synthetic_signature(self):
        self.assertEqual(module.audit(fixture())['status'], 'STRUCTURAL_AUDIT_OK')

    def test_code_page_tampering(self):
        data = bytearray(fixture())
        data[512] ^= 1
        with self.assertRaisesRegex(ValueError, 'CODE_PAGE_HASH_MISMATCH'):
            module.audit(data)

    def test_requirements_tampering(self):
        data = bytearray(fixture())
        slot, offset = struct.unpack_from('>II', data, 4096 + 20)
        self.assertEqual(slot, 2)
        data[4096 + offset + 11] ^= 1
        with self.assertRaisesRegex(ValueError, 'SPECIAL_SLOT_HASH_MISMATCH'):
            module.audit(data)

    def test_wrong_platform_and_minimum_os(self):
        for data in (fixture(platform=7), fixture(minos=0x100000)):
            with self.assertRaisesRegex(ValueError, 'REQUIRES_IOS_MINIMUM'):
                module.audit(data)

    def test_entitlements_refused(self):
        with self.assertRaisesRegex(ValueError, 'ENTITLEMENTS'):
            module.audit(fixture(extra_slot=5))

    def test_truncation_and_bad_command_size(self):
        data = bytearray(fixture())
        struct.pack_into('<I', data, 36, 0)
        for broken in (fixture()[:20], fixture()[:-1], data):
            with self.assertRaises(ValueError):
                module.audit(broken)


if __name__ == '__main__':
    unittest.main(verbosity=2)
