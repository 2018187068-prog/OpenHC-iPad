"""Prepare a rootless executable layout from an audited metadata-only tool.

Local artifact work only. Never connects to a device, changes trustcaches,
executes the tool, or overwrites an existing different file.
"""
import json
import os
from pathlib import Path
import runpy
import sys


def write_same_or_new(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError('REFUSE_SYMLINK_OUTPUT')
    try:
        with path.open('xb') as stream:
            stream.write(data)
    except FileExistsError:
        if path.read_bytes() != data:
            raise ValueError('REFUSE_DIFFERENT_EXISTING_OUTPUT')


def package(binary, output):
    audit = runpy.run_path(str(Path(__file__).with_name('audit-role-binary.py')))['audit']
    data = binary.read_bytes()
    report = audit(data)
    name = 'openhc-role-probe-' + report['sha256'][:8]
    execution_path = '/var/jb/usr/bin/' + name
    destination = output / 'rootless' / execution_path.lstrip('/')
    write_same_or_new(destination, data)
    os.chmod(destination, 0o700)
    # Auditing the final copy also detects accidental changes during packaging.
    if audit(destination.read_bytes()) != report:
        raise ValueError('PACKAGED_BINARY_CHANGED')
    manifest = {'sha256': report['sha256'], 'execution_path': execution_path,
                'relative_file': destination.relative_to(output).as_posix(),
                'intended_device_mode': '0700', 'intended_device_owner': 'root:wheel',
                'startup_check_argument': '--self-check',
                'automatic_device_execution': False,
                'device_validation': 'not performed by packaging'}
    encoded = (json.dumps(manifest, indent=2) + '\n').encode()
    write_same_or_new(output / 'rootless-role-manifest.json', encoded)
    return manifest


if __name__ == '__main__':
    print(json.dumps(package(Path(sys.argv[1]), Path(sys.argv[2])), indent=2))
