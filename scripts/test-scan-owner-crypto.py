"""Crypto-only reuse failure tests: no source artifacts/config/identity restored."""
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
spec = importlib.util.spec_from_file_location('reuse', Path(__file__).with_name('prepare-scan-owner-crypto.py'))
reuse = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reuse)

class ReuseTests(unittest.TestCase):
    def check_archive(self, mutate=None, fail=None):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'source.zip'
            members = {'BUILD.txt':('source_commit='+reuse.SOURCE+'\n').encode()}
            for target in ('iosArm64','iosSimulatorArm64'):
                for name in ('libcrypto.a','libopenhc_crypto.a'):
                    members['crypto/'+target+'/'+name] = b'!<arch>\nSYNTHETIC'
            # Deliberately present forbidden unrelated member; never read/restore.
            members['iosArm64/OpenHCBridge.framework/OpenHCBridge'] = b'OLD_FRAMEWORK'
            if mutate: mutate(members)
            with zipfile.ZipFile(path,'w') as z:
                for name,value in members.items(): z.writestr(name,value)
            digest=hashlib.sha256(path.read_bytes()).hexdigest()
            dest=Path(directory)/'dest'
            with patch.object(reuse,'DIGEST',digest), patch.object(reuse.subprocess,'check_output',return_value=b''):
                if fail:
                    with self.assertRaisesRegex((ValueError,KeyError),fail):reuse.prepare(path,dest)
                    self.assertFalse(dest.exists(), 'validate all selected members before any write')
                else:
                    reuse.prepare(path,dest)
                    self.assertEqual(len(list(dest.rglob('*.a'))),4)
                    self.assertFalse((dest/'iosArm64').exists())
    def test_crypto_only(self):self.check_archive()
    def test_source_mismatch(self):self.check_archive(lambda m:m.update({'BUILD.txt':b'wrong'}),'CRYPTO_BUILD_SOURCE')
    def test_late_missing_member_no_partial_write(self):
        self.check_archive(lambda m:m.pop('crypto/iosSimulatorArm64/libopenhc_crypto.a'),'crypto/')
    def test_not_ar(self):self.check_archive(lambda m:m.update({'crypto/iosArm64/libcrypto.a':b'wrong'}),'CRYPTO_NOT_AR')
    def test_unpinned_zip(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'wrong.zip';path.write_bytes(b'wrong')
            with self.assertRaisesRegex(ValueError,'CRYPTO_ZIP_DIGEST_MISMATCH'):reuse.prepare(path)
    def test_crypto_input_change(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'source.zip';path.write_bytes(b'dummy')
            with patch.object(reuse,'DIGEST',hashlib.sha256(b'dummy').hexdigest()),patch.object(reuse.subprocess,'check_output',return_value=b'native/crypto/openhc_crypto.c'):
                with self.assertRaisesRegex(ValueError,'CRYPTO_INPUT_CHANGED'):reuse.prepare(path)

if __name__=='__main__':unittest.main()
