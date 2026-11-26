#!/usr/bin/env python3
"""Exercise source/digest fencing and the framework-only restore boundary."""
import contextlib
import hashlib
import importlib.util
import io
import pathlib
import tempfile
import unittest
from unittest import mock
import zipfile

SPEC = importlib.util.spec_from_file_location('reuse', pathlib.Path(__file__).with_name('prepare-scan-app-reuse.py'))
reuse = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reuse)


class ReuseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        self.archive = self.root / 'fixture.zip'
        header = b' onTransportEventGeneration: onControlRfcommReadyGeneration: onControlSdpReadyGeneration: takeAuthHandoffGeneration:'
        with zipfile.ZipFile(self.archive, 'w') as z:
            z.writestr('BUILD.txt', 'source_commit='+reuse.SOURCE+'\n')
            for name in reuse.REQUIRED:
                z.writestr(name, header if name.endswith('.h') else b'synthetic-build-file')
            z.writestr('iosArm64/OpenHCBridge-ObjC-API.h', header)
            z.writestr('scan-ui/untrusted.deb', b'must-not-restore')
            z.writestr('scan-supervisor/untrusted.deb', b'must-not-restore')
        self.enterContext(mock.patch.object(reuse, 'ROOT', self.root))
        self.enterContext(mock.patch.object(reuse, 'DIGEST', hashlib.sha256(self.archive.read_bytes()).hexdigest()))
        self.git = self.enterContext(mock.patch.object(reuse.subprocess, 'check_output', return_value=''))
        self.enterContext(contextlib.redirect_stdout(io.StringIO()))

    def test_audit_never_writes(self):
        reuse.prepare(self.archive)
        self.assertFalse((self.root/'artifacts').exists())

    def test_restore_only_framework_and_crypto(self):
        reuse.prepare(self.archive, restore=True)
        files = {p.relative_to(self.root/'artifacts').as_posix() for p in (self.root/'artifacts').rglob('*') if p.is_file()}
        self.assertEqual(files, set(reuse.REQUIRED))

    def test_tampered_digest_rejected_before_git_or_write(self):
        self.archive.write_bytes(self.archive.read_bytes()+b'tampered')
        with self.assertRaisesRegex(ValueError, 'ZIP_DIGEST'):
            reuse.prepare(self.archive, restore=True)
        self.git.assert_not_called()
        self.assertFalse((self.root/'artifacts').exists())

    def test_modified_framework_source_rejected(self):
        self.git.return_value = 'bridge/src/commonMain/changed.kt\n'
        with self.assertRaisesRegex(ValueError, 'INPUTS_CHANGED'):
            reuse.prepare(self.archive, restore=True)
        self.assertFalse((self.root/'artifacts').exists())

    def test_untracked_framework_source_rejected(self):
        self.git.side_effect = ['', 'native/untracked.c\n']
        with self.assertRaisesRegex(ValueError, 'UNTRACKED_FRAMEWORK_INPUTS'):
            reuse.prepare(self.archive, restore=True)
        self.assertFalse((self.root/'artifacts').exists())


if __name__ == '__main__':
    unittest.main()
