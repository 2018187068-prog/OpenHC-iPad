#!/usr/bin/env python3
"""Verify one pinned synthetic CI archive; restore framework/crypto only.

No App, helper, identity, runtime configuration or device logs are restored.
Reject reuse if any framework/crypto source or build input changed.
"""
import argparse
import hashlib
import pathlib
import stat
import subprocess
import zipfile

SOURCE = '6d1731813d95e8e60f7628a7a06f95848668c6f2'
RUN = 45875853812
ARTIFACT = 15145905964
DIGEST = 'aef52fb49f3d3737e190703b195a9ce5b39ec0ca7dbb2a898d1077a4fb86a60c'
ROOT = pathlib.Path(__file__).resolve().parents[1]
INPUTS = ['bridge', 'native', 'build.gradle.kts', 'settings.gradle.kts',
          'gradle.properties', 'gradle', 'scripts/build-crypto-backend.sh',
          'scripts/source-slices.sha256', 'scripts/verify-apple-artifact.sh']
PREFIXES = ('iosArm64/OpenHCBridge.framework/', 'crypto/iosArm64/',
            'crypto/iosSimulatorArm64/')
REQUIRED = ['iosArm64/OpenHCBridge.framework/'+name for name in
            ('OpenHCBridge', 'Headers/OpenHCBridge.h', 'Info.plist', 'Modules/module.modulemap')]
REQUIRED += ['crypto/'+target+'/'+name for target in ('iosArm64', 'iosSimulatorArm64')
             for name in ('libcrypto.a', 'libopenhc_crypto.a')]


def prepare(path, restore=False):
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != DIGEST:
        raise ValueError('REUSE_ZIP_DIGEST_MISMATCH')
    changed = subprocess.check_output(['git', 'diff', '--name-only', SOURCE, '--', *INPUTS],
                                      cwd=ROOT, text=True)
    if changed.strip():
        raise ValueError('REUSE_FRAMEWORK_INPUTS_CHANGED')
    if subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard', '--',
                                *INPUTS], cwd=ROOT, text=True).strip():
        raise ValueError('REUSE_UNTRACKED_FRAMEWORK_INPUTS')
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError('REUSE_DUPLICATE_MEMBER')
        if archive.read('BUILD.txt').decode().splitlines()[0] != 'source_commit='+SOURCE:
            raise ValueError('REUSE_BUILD_SOURCE_MISMATCH')
        if not all(name in names for name in REQUIRED):
            raise ValueError('REUSE_REQUIRED_MEMBER_MISSING')
        header = archive.read('iosArm64/OpenHCBridge.framework/Headers/OpenHCBridge.h')
        if header != archive.read('iosArm64/OpenHCBridge-ObjC-API.h'):
            raise ValueError('REUSE_HEADER_COPY_MISMATCH')
        for selector in (b'onTransportEventGeneration:', b'onControlRfcommReadyGeneration:',
                         b'onControlSdpReadyGeneration:', b'takeAuthHandoffGeneration:'):
            if selector not in header:
                raise ValueError('REUSE_SCAN_INTERFACE_MISSING')
        selected = []
        for member in archive.infolist():
            if not member.filename.startswith(PREFIXES):
                continue
            relative = pathlib.PurePosixPath(member.filename)
            mode = member.external_attr >> 16
            if relative.is_absolute() or '..' in relative.parts or '\\' in member.filename:
                raise ValueError('REUSE_MEMBER_PATH')
            if stat.S_ISLNK(mode) or member.is_dir():
                raise ValueError('REUSE_MEMBER_TYPE')
            selected.append((member, relative))
        for member, relative in selected if restore else []:
            destination = ROOT / 'artifacts' / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(archive.read(member))
        for name in REQUIRED:
            print(f'REUSE_MEMBER_SHA256 {name} {hashlib.sha256(archive.read(name)).hexdigest()}')
    print(f'SCAN_APP_REUSE_OK source={SOURCE} run={RUN} artifact={ARTIFACT} zip_sha256={DIGEST}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=pathlib.Path)
    parser.add_argument('--restore', action='store_true', help='restore only verified framework/crypto into CI workspace')
    args = parser.parse_args()
    prepare(args.archive, args.restore)
