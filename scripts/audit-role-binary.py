"""Offline audit of our public metadata executable, never device identity data.

Deliberately accepts only thin arm64 iOS executables with libSystem alone and
no entitlements. Verifies embedded CodeDirectory page and special-slot hashes.
This is structural evidence, not an AMFI or physical launch test.
"""
import hashlib
import json
from pathlib import Path
import struct
import sys


def require(condition, message):
    if not condition:
        raise ValueError(message)


def audit(data):
    def unpack(fmt, offset, end=None):
        size = struct.calcsize(fmt)
        require(0 <= offset <= (len(data) if end is None else end) - size,
                'TRUNCATED_STRUCTURE')
        return struct.unpack_from(fmt, data, offset)

    magic, cpu, subtype, kind, count, size, flags, reserved = unpack('<8I', 0)
    require((magic, cpu, subtype, kind) == (0xfeedfacf, 0x100000c, 0, 2),
            'REQUIRES_THIN_BASELINE_ARM64_EXECUTABLE')
    end = 32 + size
    require(count <= 256 and end <= len(data), 'LOAD_COMMAND_RANGE')
    offset = 32
    signature = None
    build = None
    dependencies = []
    chained = False
    entry = False
    for _ in range(count):
        command, length = unpack('<II', offset, end)
        require(length >= 8 and length % 8 == 0 and offset + length <= end,
                'LOAD_COMMAND_SIZE')
        if command == 0x32:
            require(build is None, 'DUPLICATE_BUILD_VERSION')
            build = unpack('<4I', offset + 8, offset + length)
            require(build[0] == 2 and build[1] <= 0x000f0000,
                    'REQUIRES_IOS_MINIMUM_AT_MOST_15_0')
        if command == 0x80000028:
            unpack('<QQ', offset + 8, offset + length)
            entry = True
        if command == 0x2c:
            require(unpack('<III', offset + 8, offset + length)[2] == 0,
                    'ENCRYPTED_BINARY')
        if command in (0xc, 0x18 | 0x80000000, 0x1f | 0x80000000, 0x20, 0x23 | 0x80000000):
            name_offset = unpack('<I', offset + 8, offset + length)[0]
            require(24 <= name_offset < length, 'DYLIB_NAME_RANGE')
            raw = data[offset + name_offset:offset + length]
            require(b'\0' in raw, 'DYLIB_NAME_TERMINATION')
            dependencies.append(raw.split(b'\0', 1)[0].decode('ascii'))
        require(command != 0x8000001c, 'UNEXPECTED_RPATH')
        if command == 0x80000034:
            chained = True
        if command == 0x1d:
            require(signature is None, 'DUPLICATE_SIGNATURE')
            signature = unpack('<II', offset + 8, offset + length)
        offset += length
    require(offset == end and build and entry and signature, 'MISSING_REQUIRED_COMMAND')
    require(dependencies == ['/usr/lib/libSystem.B.dylib'], 'UNEXPECTED_DEPENDENCY')
    start, sigsize = signature
    require(end <= start and start + sigsize == len(data), 'SIGNATURE_RANGE')
    smagic, total, blobs = unpack('>III', start)
    require(smagic == 0xfade0cc0 and 12 <= total <= sigsize and blobs <= 32,
            'SIGNATURE_SUPERBLOB')
    index_end = start + 12 + blobs * 8
    require(index_end <= start + total, 'SIGNATURE_INDEX')
    slots = {}
    ranges = []
    for i in range(blobs):
        slot, relative = unpack('>II', start + 12 + i * 8, start + total)
        pos = start + relative
        require(slot not in slots and pos >= index_end, 'SIGNATURE_SLOT_RANGE')
        blob_magic, length = unpack('>II', pos, start + total)
        require(length >= 8 and pos + length <= start + total, 'SIGNATURE_BLOB_RANGE')
        require(not any(pos < stop and pos + length > begin for begin, stop in ranges),
                'SIGNATURE_BLOB_OVERLAP')
        ranges.append((pos, pos + length))
        require(slot in (0, 2, 0x1000), 'UNEXPECTED_SIGNATURE_SLOT_OR_ENTITLEMENTS')
        slots[slot] = (pos, length, blob_magic)
    directories = []
    for slot, (pos, length, blob_magic) in slots.items():
        if slot not in (0, 0x1000):
            require(blob_magic == 0xfade0c01, 'REQUIREMENTS_MAGIC')
            continue
        require(blob_magic == 0xfade0c02 and length >= 88, 'CODEDIRECTORY_MAGIC_OR_SIZE')
        version, cdflags, hash_offset, identifier, special, pages, limit = unpack('>7I', pos + 8, pos + length)
        hashsize, hashtype, platform, page = unpack('4B', pos + 36, pos + length)
        require(version == 0x20400 and page in (12, 14), 'CODEDIRECTORY_VERSION_OR_PAGE')
        require((hashtype, hashsize) in ((1, 20), (2, 32)), 'CODEDIRECTORY_HASH_TYPE')
        require(limit == start and pages == (limit + (1 << page) - 1) >> page,
                'CODEDIRECTORY_COVERAGE')
        require(special <= 7 and 88 <= identifier < hash_offset - special * hashsize,
                'CODEDIRECTORY_IDENTIFIER_RANGE')
        require(b'\0' in data[pos + identifier:pos + hash_offset - special * hashsize],
                'CODEDIRECTORY_IDENTIFIER_TERMINATION')
        require(hash_offset + pages * hashsize <= length, 'CODEDIRECTORY_HASH_RANGE')
        digest = hashlib.sha256 if hashtype == 2 else hashlib.sha1
        for i in range(pages):
            actual = digest(data[i * (1 << page):min((i + 1) * (1 << page), limit)]).digest()
            require(actual == data[pos + hash_offset + i * hashsize:pos + hash_offset + (i + 1) * hashsize],
                    'CODE_PAGE_HASH_MISMATCH')
        for i in range(1, special + 1):
            expected = bytes(hashsize)
            if i in slots:
                sp, sl, _ = slots[i]
                expected = digest(data[sp:sp + sl]).digest()
            require(expected == data[pos + hash_offset - i * hashsize:pos + hash_offset - (i - 1) * hashsize],
                    'SPECIAL_SLOT_HASH_MISMATCH')
        directories.append({'hash': hashtype, 'page_bytes': 1 << page,
                            'flags': cdflags, 'cdhash': digest(data[pos:pos + length]).hexdigest()[:40]})
    require({d['hash'] for d in directories} == {1, 2}, 'REQUIRES_BOTH_CODEDIRECTORIES')
    return {'sha256': hashlib.sha256(data).hexdigest(), 'platform': build[0],
            'minos': build[1], 'sdk': build[2], 'chained_fixups': chained,
            'dependencies': dependencies, 'directories': directories,
            'entitlements': 'absent', 'status': 'STRUCTURAL_AUDIT_OK'}


if __name__ == '__main__':
    print(json.dumps(audit(Path(sys.argv[1]).read_bytes()), indent=2))
