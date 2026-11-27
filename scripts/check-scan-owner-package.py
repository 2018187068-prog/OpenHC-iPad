"""Read inert rootless package metadata without extraction or installation."""
import argparse
import hashlib
import importlib.util
from pathlib import Path
import struct

_spec = importlib.util.spec_from_file_location('scan_archive', Path(__file__).with_name('check-scan-demo-archive.py'))
_archive = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_archive)


def check(raw):
    control_raw, data_raw = _archive.read_deb(raw)
    assert data_raw.startswith(bytes([0xfd,55,122,88,90,0])), 'inert package must use xz'
    control, data = _archive.read_tar(control_raw), _archive.read_tar(data_raw)
    assert set(control) == {'control'}, 'no maintainer scripts'
    assert control['control'][0].isreg() and control['control'][0].mode == 0o644, 'control mode/type'
    fields = dict(line.split(': ', 1) for line in control['control'][1].decode().splitlines() if ': ' in line)
    assert fields['Package'] == 'com.gcbond.openhc-scan-owner-inert'
    assert fields['Architecture'] == 'iphoneos-arm64' and fields['Version'] == '0.1.0'
    assert fields['Depends'] == 'firmware (>= 15.0)'
    parent = 'var/jb/usr/libexec/openhc-owner-inert'
    directories = {'var', 'var/jb', 'var/jb/usr', 'var/jb/usr/libexec', parent}
    binaries = {parent + '/openhc-scan-broker', parent + '/openhc-scan-guard'}
    assert set(data) == directories | binaries, 'no launch job/config/links/extra payload'
    for name, (member, body) in data.items():
        assert member.mode == 0o755
        if name in directories:
            assert member.isdir()
        else:
            assert member.isreg() and len(body) > 32
            magic, cpu = struct.unpack_from('<II', body)
            assert magic == 0xfeedfacf and cpu == 0x100000c, 'arm64 Mach-O required'
    return True


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('package', type=Path)
    args = parser.parse_args()
    check(args.package.read_bytes())
    print('SCAN_OWNER_INERT_PACKAGE_OK_NO_DEPLOYMENT sha256=' + hashlib.sha256(args.package.read_bytes()).hexdigest())
