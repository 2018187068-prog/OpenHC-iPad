"""Exercise the C query client against a synthetic local Unix stream server.

No device, radio, credentials or real BTstack instance is used. macOS only.
"""
import os
from pathlib import Path
import socket
import struct
import subprocess
import tempfile
import threading
import time

root = Path(__file__).resolve().parents[1]


def exact(conn, size):
    data = b""
    while len(data) < size:
        part = conn.recv(size - len(data))
        if not part:
            raise AssertionError("client closed early")
        data += part
    return data


def frame(body):
    return struct.pack("<HHH", 4, 0, len(body)) + body


with tempfile.TemporaryDirectory(prefix="ohbt-", dir="/tmp") as directory:
    executable = str(Path(directory) / "query")
    subprocess.run(["clang", "-std=c11", "-Wall", "-Wextra", "-Werror",
                    "-DOPENHC_BTSTACK_TEST", str(root / "theos/btstack-probe.c"),
                    "-o", executable], check=True)
    cases = ["fragmented", "unrelated", "eof", "oversize", "bad_length",
             "wrong_channel", "timeout", "event_flood"]
    for case in cases:
        endpoint = str(Path(directory) / "s")
        errors = []
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
            server.bind(endpoint)
            server.listen(1)
            server.settimeout(8)

            def serve():
                try:
                    with server.accept()[0] as conn:
                        conn.settimeout(6)
                        assert exact(conn, 9) == bytes([1, 0, 0, 0, 3, 0, 4, 0xf4, 0])
                        if case == "eof":
                            return
                        if case == "timeout":
                            time.sleep(4.5)
                            return
                        if case == "oversize":
                            conn.sendall(struct.pack("<HHH", 4, 0, 1025))
                            return
                        if case == "bad_length":
                            conn.sendall(frame(bytes([0x63, 3, 1, 2, 0, 0])))
                            return
                        if case == "wrong_channel":
                            conn.sendall(struct.pack("<HHH", 4, 1, 6) + bytes([0x63, 4, 1, 2, 0, 0]))
                            return
                        if case == "event_flood":
                            conn.sendall(frame(bytes([0x60, 1, 0])) * 32)
                            return
                        if case == "unrelated":
                            conn.sendall(frame(bytes([0x60, 1, 0])))
                        version = frame(bytes([0x63, 4, 1, 2, 0xb9, 0x0c]))
                        for byte in version:
                            conn.sendall(bytes([byte]))
                            time.sleep(0.001)
                        assert exact(conn, 9) == bytes([1, 0, 0, 0, 3, 0, 1, 0xf4, 0])
                        conn.sendall(frame(bytes([0x60, 1, 0])))
                        assert conn.recv(1) == b"", "client must close its connection"
                except Exception as error:
                    errors.append(error)

            worker = threading.Thread(target=serve, daemon=True)
            worker.start()
            completed = subprocess.run([executable, endpoint], capture_output=True, text=True, timeout=8)
            worker.join(7)
            assert not worker.is_alive(), "mock server did not finish"
            assert not errors, errors
            success = case in ("fragmented", "unrelated")
            assert completed.returncode == (0 if success else 1), case
            assert ("BTSTACK_QUERY_OK" in completed.stdout) == success, case
            if success:
                assert "BTSTACK_VERSION=1.2" in completed.stdout
                assert "BTSTACK_REVISION=3257" in completed.stdout
                assert "BTSTACK_STATE=0" in completed.stdout
            else:
                assert "BTSTACK_QUERY_FAILED=VERSION" in completed.stdout
            print("BTSTACK_MOCK_CASE_OK=" + case)
        os.unlink(endpoint)
    missing = subprocess.run([executable, str(Path(directory) / "missing")],
                             capture_output=True, text=True, timeout=8)
    assert missing.returncode == 1 and "BTSTACK_QUERY_FAILED=CONNECT" in missing.stdout
    print("BTSTACK_MOCK_CASE_OK=missing_socket")
    print("BTSTACK_MOCK_TESTS_OK=9")
