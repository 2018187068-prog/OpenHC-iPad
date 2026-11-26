#!/usr/bin/env python3
"""Read numeric archive metadata; never extract or follow package links."""
import argparse
import hashlib
import io
import pathlib
import plistlib
import tarfile


class InvalidArchive(ValueError):
    pass


APP = 'var/jb/Applications/OpenHCScanDemo.app'
HELPER = 'var/jb/usr/libexec/openhc-scan-ping-helper'
JOB = 'var/jb/Library/LaunchDaemons/com.gcbond.openhc-scan-ping-helper.plist'
RUNTIME = 'var/jb/var/run/openhc'
LAYOUTS = {
    'com.gcbond.openhc-scan-demo': {
        'var': 0o755, 'var/jb': 0o755, 'var/jb/Applications': 0o755,
        APP: 0o755, APP+'/Info.plist': 0o644, APP+'/OpenHCScanDemo': 0o755,
    },
    'com.gcbond.openhc-scan-ping-helper': {
        'var': 0o755, 'var/jb': 0o755, 'var/jb/usr': 0o755,
        'var/jb/usr/libexec': 0o755, HELPER: 0o755,
        'var/jb/Library': 0o755, 'var/jb/Library/LaunchDaemons': 0o755, JOB: 0o644,
        'var/jb/var': 0o755, 'var/jb/var/run': 0o755, RUNTIME: 0o755,
        RUNTIME+'/README.txt': 0o644,
    },
}
FILES = {APP+'/Info.plist', APP+'/OpenHCScanDemo', HELPER, JOB, RUNTIME+'/README.txt'}


def require(condition, message):
    if not condition:
        raise InvalidArchive(message)


def read_deb(raw):
    require(raw.startswith(b'!<arch>\n'), 'DEB_AR_MAGIC')
    members = {}
    offset = 8
    while offset < len(raw):
        header = raw[offset:offset+60]
        require(len(header) == 60 and header[58:60] == b'`\n', 'DEB_AR_HEADER')
        name = header[:16].decode('ascii').strip().rstrip('/')
        try:
            size = int(header[48:58])
        except ValueError as error:
            raise InvalidArchive('DEB_AR_SIZE') from error
        require(size >= 0 and offset+60+size <= len(raw), 'DEB_AR_BOUNDS')
        require(name not in members, 'DEB_AR_DUPLICATE')
        members[name] = raw[offset+60:offset+60+size]
        offset += 60+size+(size % 2)
    require(members.get('debian-binary') == b'2.0\n', 'DEB_VERSION')
    control = [key for key in members if key.startswith('control.tar')]
    data = [key for key in members if key.startswith('data.tar')]
    require(len(control) == len(data) == 1 and len(members) == 3, 'DEB_MEMBERS')
    return members[control[0]], members[data[0]]


def read_tar(raw):
    entries = {}
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:*') as archive:
        for member in archive.getmembers():
            name = member.name
            require(not name.startswith('/') and '\\' not in name, 'TAR_ABSOLUTE_PATH')
            while name.startswith('./'):
                name = name[2:]
            if name == '.':
                name = ''
            require(all(part not in ('', '.', '..') for part in name.split('/')) or not name,
                    'TAR_TRAVERSAL_OR_EMPTY_COMPONENT')
            require(name not in entries, 'TAR_DUPLICATE_PATH')
            require(member.isdir() or member.isreg(), 'TAR_LINK_OR_SPECIAL_FILE')
            require(member.uid == 0 and member.gid == 0, 'TAR_OWNER_NOT_ROOT:'+name)
            require(member.mode in (0o644, 0o755), 'TAR_MODE:'+name)
            entries[name] = (member, archive.extractfile(member).read() if member.isreg() else None)
    if '' in entries:
        require(entries[''][0].isdir() and entries[''][0].mode == 0o755, 'TAR_ROOT_MODE')
        del entries['']
    return entries


def check(raw, require_xz=False):
    control_raw, data_raw = read_deb(raw)
    if require_xz:
        require(data_raw.startswith(b'\xfd7zXZ\x00'), 'DATA_COMPRESSION_NOT_XZ')
    control = read_tar(control_raw)
    require(set(control) == {'control'}, 'CONTROL_SCRIPTS_OR_UNEXPECTED_FILES')
    require(control['control'][0].isreg() and control['control'][0].mode == 0o644, 'CONTROL_MODE')
    fields = dict(line.split(': ', 1) for line in control['control'][1].decode().splitlines() if ': ' in line)
    package = fields.get('Package')
    require(package in LAYOUTS, 'PACKAGE_NAME')
    require(fields.get('Architecture') == 'iphoneos-arm64', 'PACKAGE_ARCH')
    require(fields.get('Version') == '0.1.0', 'PACKAGE_VERSION')
    require(fields.get('Depends') == 'firmware (>= 15.0)', 'PACKAGE_DEPENDENCIES')
    data = read_tar(data_raw)
    layout = LAYOUTS[package]
    require(set(data) == set(layout), 'PACKAGE_LAYOUT')
    for name, (member, _) in data.items():
        require(member.mode == layout[name], 'PACKAGE_MODE:'+name)
        require(member.isreg() if name in FILES else member.isdir(), 'PACKAGE_TYPE:'+name)
    if package.endswith('helper'):
        job = plistlib.loads(data[JOB][1])
        require(job == {
            'Label': 'com.gcbond.openhc-scan-ping-helper', 'UserName': 'root',
            'ProgramArguments': ['/var/jb/usr/libexec/openhc-scan-ping-helper'],
            'RunAtLoad': True, 'KeepAlive': True, 'ThrottleInterval': 5,
            'ProcessType': 'Background',
        }, 'HELPER_JOB_SCOPE')
    else:
        info = plistlib.loads(data[APP+'/Info.plist'][1])
        require(info.get('CFBundleIdentifier') == package and
                info.get('CFBundleExecutable') == 'OpenHCScanDemo', 'APP_IDENTITY')
    return package


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--require-xz', action='store_true')
    parser.add_argument('packages', nargs='+', type=pathlib.Path)
    args = parser.parse_args()
    for package in args.packages:
        raw = package.read_bytes()
        name = check(raw, require_xz=args.require_xz)
        print(f'SCAN_DEMO_ARCHIVE_OK package={name} version=0.1.0 sha256={hashlib.sha256(raw).hexdigest()}')


if __name__ == '__main__':
    main()
