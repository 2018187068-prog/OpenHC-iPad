"""Reuse ONLY pinned crypto archives; rebuild frameworks against current sources.
Local ZIP argument; no CI/API/device access or restoration of an old framework.
"""
import hashlib
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = '6d1731813d95e8e60f7628a7a06f95848668c6f2'
DIGEST = 'aef52fb49f3d3737e190703b195a9ce5b39ec0ca7dbb2a898d1077a4fb86a60c'
INPUTS = ['native/crypto', 'scripts/build-crypto-backend.sh']

def prepare(path, destination=None):
    if hashlib.sha256(Path(path).read_bytes()).hexdigest() != DIGEST:
        raise ValueError('CRYPTO_ZIP_DIGEST_MISMATCH')
    if subprocess.check_output(['git', 'diff', '--name-only', SOURCE, '--', *INPUTS], cwd=ROOT).strip():
        raise ValueError('CRYPTO_INPUT_CHANGED_REBUILD_REQUIRED')
    if subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard', '--', *INPUTS], cwd=ROOT).strip():
        raise ValueError('CRYPTO_INPUT_UNTRACKED_REBUILD_REQUIRED')
    names = ['crypto/'+target+'/'+lib for target in ('iosArm64', 'iosSimulatorArm64')
             for lib in ('libcrypto.a', 'libopenhc_crypto.a')]
    with zipfile.ZipFile(path) as z:
        if len(z.namelist()) != len(set(z.namelist())):
            raise ValueError('DUPLICATE_ZIP_MEMBER')
        if z.read('BUILD.txt').decode().splitlines()[0] != 'source_commit='+SOURCE:
            raise ValueError('CRYPTO_BUILD_SOURCE')
        selected = []
        for name in names:
            info = z.getinfo(name)
            if ((info.external_attr >> 16) & 0o170000) not in (0, 0o100000) or info.file_size > 64*1024*1024:
                raise ValueError('CRYPTO_NOT_REGULAR')
            raw = z.read(name)
            if not raw.startswith(b'!<arch>\n'): raise ValueError('CRYPTO_NOT_AR')
            selected.append((name, raw))
        for name, raw in selected:
            dest = (Path(destination) if destination else ROOT / 'artifacts') / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(raw)
            print('CRYPTO_REUSE_SHA256', name, hashlib.sha256(raw).hexdigest())
    print('CRYPTO_ONLY_REUSE_OK source='+SOURCE+' zip_sha256='+DIGEST)

if __name__ == '__main__':
    prepare(sys.argv[1])
