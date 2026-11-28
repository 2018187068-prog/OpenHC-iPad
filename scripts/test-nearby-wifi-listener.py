"""Kernel-operation regressions available on Windows; actual C helper runs on CI.

No radio configuration. Real local sockets validate idempotent listen and rejection
of connected/datagram descriptors. This is not ObjC/Native or Darwin runtime proof.
"""
import socket
import unittest
import importlib.util
import os
from pathlib import Path
import shutil
from unittest.mock import patch


class ListenerOperations(unittest.TestCase):
    def test_actual_phone_cipher_matches_common_test_wire_inputs(self):
        path=Path(__file__).with_name('test-fe35-cli-inbound-simulator.py')
        spec=importlib.util.spec_from_file_location('listener_phone',path)
        h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
        executable=shutil.which('openssl')
        if not executable and os.name=='nt':
            candidate=Path('C:/Program Files/Git/usr/bin/openssl.exe')
            if candidate.is_file():executable=str(candidate)
        self.assertTrue(executable,'OpenSSL required for actual phone framing regression')
        vectors=[
            (4,bytes.fromhex('8183838380'),'7f84818a8188e1e2e3e4e5e6e7e885af2f5cb76c29fc'),
            (4,bytes.fromhex('87828381'),'7f84818a8188e1e2e3e4e5e6e7e884a92e5cb5d0a1'),
            (33,b'\x82\x9102:12:34:56:78:9a','7fa1818a8188e1e2e3e4e5e6e7e893ac3def06d63666a58177285e114d1ef603e52d3eac'),
        ]
        with patch.dict(os.environ,{'PATH':str(Path(executable).parent)+os.pathsep+os.environ.get('PATH','')}):
            for outer,payload,golden in vectors:
                actual=h.encrypted_frame(outer,payload,bytes(range(0xe1,0xe9)))
                self.assertTrue(actual==bytes.fromhex(golden),'actual driver agrees with independent common test frame')
                self.assertTrue(h.decode_frame(actual)==(outer,1,payload),'real frame CRC/header/cipher roundtrip')

    def listener(self):
        s=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        self.addCleanup(s.close)
        s.bind(('127.0.0.1',0));s.setblocking(False);s.listen(1)
        return s

    def test_reassert_listen_preserves_port_and_accepts_actual_tcp(self):
        s=self.listener();address=s.getsockname()
        self.assertEqual(s.getsockopt(socket.SOL_SOCKET,socket.SO_TYPE),socket.SOCK_STREAM)
        self.assertFalse(s.getblocking())
        s.listen(1);self.assertEqual(address,s.getsockname())
        with socket.create_connection(address,timeout=2) as client:
            peer,_=s.accept()
            with peer:
                client.sendall(b'X');self.assertEqual(peer.recv(1),b'X')

    def test_kernel_rejects_listen_on_connected_stream(self):
        s=self.listener()
        with socket.create_connection(s.getsockname(),timeout=2) as client:
            peer,_=s.accept()
            with peer:
                peer.setblocking(False)
                with self.assertRaises(OSError):peer.listen(1)
            with self.assertRaises(OSError):client.listen(1)

    def test_datagram_is_not_a_stream_and_cannot_listen(self):
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as s:
            s.bind(('127.0.0.1',0));s.setblocking(False)
            self.assertNotEqual(s.getsockopt(socket.SOL_SOCKET,socket.SO_TYPE),socket.SOCK_STREAM)
            with self.assertRaises(OSError):s.listen(1)

    def test_bound_stream_remains_provider_owned_when_listen_is_reasserted(self):
        with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as s:
            s.bind(('127.0.0.1',0));s.setblocking(False);address=s.getsockname();descriptor=s.fileno()
            s.listen(1)
            self.assertEqual(descriptor,s.fileno());self.assertEqual(address,s.getsockname())

    def test_unbound_or_blocking_descriptors_fail_original_preconditions(self):
        with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as s:
            try:address=s.getsockname()
            except OSError:address=None  # Winsock rejects getsockname before bind.
            self.assertTrue(address is None or address[1]==0);self.assertTrue(s.getblocking())
        s=self.listener();self.assertNotEqual(s.getsockname()[1],0)
        self.assertNotEqual(s.getsockname()[0],'192.0.2.99')


if __name__=='__main__':
    unittest.main()
