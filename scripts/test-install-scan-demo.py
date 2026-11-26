#!/usr/bin/env python3
"""Synthetic SSH boundary checks. Never connects to a device."""
import importlib.util
import pathlib
import unittest

spec = importlib.util.spec_from_file_location('installer', pathlib.Path(__file__).with_name('install-scan-demo.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class FakeSSH:
    def __init__(self, app_current=False, helper_current=True, fail_upload=False):
        self.app_current = app_current
        self.helper_current = helper_current
        self.fail_upload = fail_upload
        self.commands = []
        self.uploads = []
        self.client = self

    def open_sftp(self): return self
    def close(self): pass
    def put(self, local, remote):
        self.uploads.append((local, remote))
        if self.fail_upload: raise OSError('synthetic upload failure')

    def run(self, command, **kwargs):
        self.commands.append(command)
        if 'dpkg-query' in command: return 0, '0.1.0', ''
        if 'sha256sum' in command:
            if m.APP_BINARY in command:
                value = m.APP_EXECUTABLE_SHA256 if self.app_current else 'old-app'
            elif m.HELPER_BINARY in command:
                value = m.HELPER_EXECUTABLE_SHA256 if self.helper_current else 'old-helper'
            elif 'app.deb' in command: value = m.APP_SHA256
            else: value = m.HELPER_SHA256
            return 0, value + '  fixed', ''
        if 'dpkg -i' in command: self.app_current = self.helper_current = True
        if 'stat -c %u:%g:%a' in command: return 0, '0:0:755', ''
        if 'stat -c %U:%G:%a' in command: return 0, 'root:mobile:660', ''
        return 0, '', ''

    def require(self, command, label, **kwargs):
        status, output, _ = self.run(command, **kwargs)
        if status: raise m.InstallError(label)
        return output


class InstallTests(unittest.TestCase):
    def test_app_only_preserves_healthy_helper(self):
        ssh = FakeSSH()
        self.assertTrue(m.device_install(ssh, app_only=True))
        self.assertEqual(len(ssh.uploads), 1)
        self.assertEqual(ssh.uploads[0][0], str(m.APP_PACKAGE))
        install = [c for c in ssh.commands if 'dpkg -i' in c]
        self.assertEqual(len(install), 1)
        self.assertNotIn('helper.deb', install[0])
        self.assertFalse(any(x in c for c in ssh.commands for x in ('bootstrap', 'bootout', 'kickstart')))

    def test_default_independently_skips_matching_helper(self):
        ssh = FakeSSH()
        m.device_install(ssh)
        self.assertEqual(len(ssh.uploads), 1)

    def test_both_matching_no_upload(self):
        ssh = FakeSSH(app_current=True)
        m.device_install(ssh, app_only=True)
        self.assertFalse(ssh.uploads)

    def test_app_only_rejects_helper_mismatch_before_mutation(self):
        ssh = FakeSSH(helper_current=False)
        with self.assertRaisesRegex(m.InstallError, 'PINNED_INSTALLED_HELPER'):
            m.device_install(ssh, app_only=True)
        self.assertFalse(ssh.uploads)
        self.assertFalse(any('mkdir' in c or 'dpkg -i' in c for c in ssh.commands))

    def test_app_only_cannot_start_helper(self):
        ssh = FakeSSH()
        with self.assertRaisesRegex(m.InstallError, 'MUST_NOT_START'):
            m.device_install(ssh, start_helper=True, app_only=True)
        self.assertFalse(ssh.commands)

    def test_upload_failure_cleans_only_private_paths(self):
        ssh = FakeSSH(fail_upload=True)
        with self.assertRaises(OSError): m.device_install(ssh, app_only=True)
        cleanup = ssh.commands[-1]
        self.assertTrue(cleanup.startswith('rm -f -- /var/tmp/openhc-scan-demo-'))
        self.assertNotIn('rm -rf', cleanup)
        self.assertNotIn(m.RUNTIME, cleanup)


if __name__ == '__main__': unittest.main(verbosity=2)
