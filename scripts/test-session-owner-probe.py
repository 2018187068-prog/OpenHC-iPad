"""Compile/run the kernel peer-PID query against a synthetic Unix socket.

Darwin uses LOCAL_PEERPID; Linux uses SO_PEERCRED. Neither sends application data.
"""
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SessionOwnerProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory(prefix='ohsession-owner-', dir='/tmp')
        cls.root = Path(cls.directory.name)
        cls.binary = cls.root / 'session-owner-test'
        subprocess.run(['clang', '-std=c11', '-Wall', '-Wextra', '-Werror',
                        '-DOPENHC_SESSION_OWNER_TEST',
                        str(ROOT / 'theos/session-owner-probe.c'), '-o', str(cls.binary)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def test_reports_peer_pid_and_sends_no_application_bytes(self):
        path = self.root / 'baa.sock'
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(path))
        listener.listen(1)
        listener.settimeout(3)
        received = []

        def accept_and_check():
            with listener.accept()[0] as peer:
                peer.settimeout(2)
                received.append(peer.recv(1))

        thread = threading.Thread(target=accept_and_check)
        thread.start()
        result = subprocess.run([str(self.binary), str(path)], capture_output=True,
                                text=True, timeout=4)
        thread.join(timeout=3)
        listener.close()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('SESSION_SOCKET_OWNER_PID=' + str(os.getpid()), result.stdout)
        self.assertIn('SESSION_SOCKET_APPLICATION_BYTES=0', result.stdout)
        self.assertEqual(received, [b''])

    def test_refuses_non_socket_and_stale_endpoint(self):
        path = self.root / 'not-socket'
        path.write_text('metadata only')
        result = subprocess.run([str(self.binary), str(path)], capture_output=True,
                                text=True, timeout=3)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('SESSION_SOCKET_OWNER_FAILED=10', result.stdout)

    def test_source_has_no_application_io_calls(self):
        source = (ROOT / 'theos/session-owner-probe.c').read_text()
        for name in ('send', 'sendto', 'sendmsg', 'recv', 'recvfrom', 'recvmsg', 'read', 'write'):
            self.assertNotIn(name + '(', source)


if __name__ == '__main__':
    unittest.main()
