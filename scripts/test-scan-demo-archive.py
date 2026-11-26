#!/usr/bin/env python3
"""Synthetic DEB archive tests, including the exact rejected builder IDs."""
import importlib.util
import io
import pathlib
import plistlib
import tarfile
import unittest

spec = importlib.util.spec_from_file_location('archive_check', pathlib.Path(__file__).with_name('check-scan-demo-archive.py'))
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


def tar(entries):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w:gz') as out:
        for info, content in entries:
            out.addfile(info, io.BytesIO(content) if content is not None else None)
    return buffer.getvalue()


def fixture(package, mutate=None, mutate_control=None):
    entries = []
    for name, mode in checker.LAYOUTS[package].items():
        info = tarfile.TarInfo(name)
        info.mode = mode
        info.uid = info.gid = 0
        if name not in checker.FILES:
            info.type = tarfile.DIRTYPE
            content = None
        elif name == checker.JOB:
            content = plistlib.dumps({
                'Label': 'com.gcbond.openhc-scan-ping-helper', 'UserName': 'root',
                'ProgramArguments': ['/var/jb/usr/libexec/openhc-scan-ping-helper'],
                'RunAtLoad': True, 'KeepAlive': True, 'ThrottleInterval': 5,
                'ProcessType': 'Background',
            })
        elif name.endswith('Info.plist'):
            content = plistlib.dumps({'CFBundleIdentifier': package, 'CFBundleExecutable': 'OpenHCScanDemo'})
        else:
            content = b'synthetic binary or README'
        info.size = len(content) if content else 0
        entries.append((info, content))
    if mutate:
        mutate(entries)
    control = tarfile.TarInfo('./control')
    control.mode = 0o644
    content = (f'Package: {package}\nVersion: 0.1.0\nArchitecture: iphoneos-arm64\n'
               'Depends: firmware (>= 15.0)\n').encode()
    control.size = len(content)
    controls = [(control, content)]
    if mutate_control:
        mutate_control(controls)
    parts = [('debian-binary', b'2.0\n'), ('control.tar.gz', tar(controls)), ('data.tar.gz', tar(entries))]
    raw = b'!<arch>\n'
    for name, payload in parts:
        header = f'{name+"/":<16}{0:<12}{0:<6}{0:<6}{"100644":<8}{len(payload):<10}`\n'.encode()
        assert len(header) == 60
        raw += header+payload+(b'\n' if len(payload) % 2 else b'')
    return raw


class ArchiveTests(unittest.TestCase):
    def each_rejected(self, mutate, message):
        for package in checker.LAYOUTS:
            with self.subTest(package=package):
                with self.assertRaisesRegex(checker.InvalidArchive, message):
                    checker.check(fixture(package, mutate))

    def test_root_owned_packages_pass(self):
        for package in checker.LAYOUTS:
            self.assertEqual(checker.check(fixture(package)), package)

    def test_old_builder_uid_gid_rejected(self):
        def change(entries):
            for info, _ in entries:
                info.uid, info.gid = 501, 20
        self.each_rejected(change, 'TAR_OWNER_NOT_ROOT')

    def test_shared_ancestor_owner_rejected(self):
        def change(entries):
            next(info for info, _ in entries if info.name == 'var/jb').uid = 501
        self.each_rejected(change, 'TAR_OWNER_NOT_ROOT')

    def test_shared_ancestor_writable_rejected(self):
        self.each_rejected(lambda entries: setattr(entries[0][0], 'mode', 0o777), 'TAR_MODE')

    def test_setuid_rejected(self):
        self.each_rejected(lambda entries: setattr(entries[-1][0], 'mode', 0o4755), 'TAR_MODE')

    def test_symlink_ancestor_rejected(self):
        def change(entries):
            info = next(info for info, _ in entries if info.name == 'var/jb')
            info.type, info.linkname = tarfile.SYMTYPE, '/private/preboot/synthetic'
        self.each_rejected(change, 'TAR_LINK_OR_SPECIAL_FILE')

    def test_hardlink_rejected(self):
        def change(entries):
            info, _ = entries[-1]
            info.type, info.linkname = tarfile.LNKTYPE, '/etc/passwd'
        self.each_rejected(change, 'TAR_LINK_OR_SPECIAL_FILE')

    def test_traversal_rejected(self):
        self.each_rejected(lambda entries: setattr(entries[0][0], 'name', '../var'), 'TAR_TRAVERSAL')

    def test_duplicate_path_rejected(self):
        self.each_rejected(lambda entries: entries.append(entries[0]), 'TAR_DUPLICATE')

    def test_unexpected_payload_rejected(self):
        self.each_rejected(lambda entries: setattr(entries[-1][0], 'name', 'var/jb/unexpected'), 'PACKAGE_LAYOUT')

    def test_executable_mode_required(self):
        def change(entries):
            for info, _ in entries:
                if info.name in (checker.HELPER, checker.APP+'/OpenHCScanDemo'):
                    info.mode = 0o644
        self.each_rejected(change, 'PACKAGE_MODE')

    def test_control_builder_uid_rejected(self):
        for package in checker.LAYOUTS:
            with self.assertRaisesRegex(checker.InvalidArchive, 'TAR_OWNER_NOT_ROOT'):
                checker.check(fixture(package, mutate_control=lambda entries: setattr(entries[0][0], 'uid', 501)))

    def test_maintainer_script_rejected(self):
        def change(entries):
            info = tarfile.TarInfo('postinst')
            info.mode = 0o755
            entries.append((info, b''))
        for package in checker.LAYOUTS:
            with self.assertRaisesRegex(checker.InvalidArchive, 'CONTROL_SCRIPTS_OR_UNEXPECTED_FILES'):
                checker.check(fixture(package, mutate_control=change))


if __name__ == '__main__':
    unittest.main(verbosity=2)
