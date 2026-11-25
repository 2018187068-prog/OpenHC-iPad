"""macOS metadata probe tests; synthetic local endpoints, never a real broker."""
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class EndpointOwnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory(prefix='ohrole-', dir='/tmp')
        cls.root = Path(cls.directory.name)
        cls.binary = cls.root / 'role-test'
        subprocess.run(['clang', '-std=c11', '-Wall', '-Wextra', '-Werror',
                        '-DOPENHC_ROLE_TEST', str(ROOT / 'scripts/showcase-role-probe.c'),
                        '-o', str(cls.binary)], check=True)
        cls.release = cls.root / 'role-release'
        subprocess.run(['clang', '-std=c11', '-Wall', '-Wextra', '-Werror',
                        str(ROOT / 'scripts/showcase-role-probe.c'),
                        '-o', str(cls.release)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def invoke(self, path):
        return subprocess.run([str(self.binary), str(path)], capture_output=True,
                              text=True, timeout=5)

    def test_owner_identity_and_zero_protocol_bytes(self):
        path = self.root / 'socket'
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
            server.bind(str(path))
            server.listen(1)
            server.settimeout(2)
            p = self.invoke(path)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            self.assertIn('BROKER_ENDPOINT_OWNER_PID=' + str(os.getpid()), p.stdout)
            self.assertIn('BROKER_APPLICATION_BYTES_SENT=0', p.stdout)
            with server.accept()[0] as peer:
                peer.settimeout(1)
                self.assertEqual(peer.recv(1), b'', 'probe sent broker application bytes')

    def test_missing_socket(self):
        p = self.invoke(self.root / 'missing')
        self.assertNotEqual(p.returncode, 0)
        self.assertIn('FAILED=10', p.stdout)

    def test_regular_file_and_symlink_refused(self):
        regular = self.root / 'regular'
        regular.write_text('synthetic')
        alias = self.root / 'alias'
        alias.symlink_to(regular)
        for path in (regular, alias):
            p = self.invoke(path)
            self.assertNotEqual(p.returncode, 0)
            self.assertIn('FAILED=11', p.stdout)

    def test_stale_socket_refused(self):
        path = self.root / 'stale'
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
            server.bind(str(path))
        p = self.invoke(path)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn('FAILED=16', p.stdout)

    def test_release_cannot_be_redirected(self):
        p = subprocess.run([str(self.release), '/tmp/other'], timeout=5)
        self.assertEqual(p.returncode, 2)

    def test_self_check_without_endpoint(self):
        # Synthetic fixture supplies no endpoint. Run as the CI user's UID;
        # self-check must precede root checks and all socket operations.
        p = subprocess.run([str(self.release), '--self-check'], capture_output=True,
                           text=True, timeout=5)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stdout.splitlines(), ['ROLE_PROBE_MAIN_ENTERED',
                                                'ROLE_PROBE_SELF_CHECK_OK'])

    def test_no_protocol_io_apis(self):
        source = (ROOT / 'scripts/showcase-role-probe.c').read_text()
        import re
        source = re.sub(r'/\*.*?\*/|//[^\n]*', '', source, flags=re.S)
        for api in ('send', 'sendto', 'sendmsg', 'recv', 'recvfrom', 'recvmsg',
                    'read', 'write', 'open', 'fopen', 'system', 'execve'):
            self.assertNotRegex(source, r'\b' + api + r'\s*\(')


if __name__ == '__main__':
    unittest.main(verbosity=2)
