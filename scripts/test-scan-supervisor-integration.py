#!/usr/bin/env python3
"""Exercise the real helper executable and independent client processes on macOS."""
import os
import pathlib
import socket
import subprocess
import tempfile
import time


def wait_for_path(path, process, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            return
        if process.poll() is not None:
            raise AssertionError(f"helper exited before bind: {process.returncode}")
        time.sleep(0.02)
    raise AssertionError("helper socket bind deadline exceeded")


def connect(path, timeout=3):
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(timeout)
    client.connect(str(path))
    return client


def stop(process, path):
    process.terminate()
    assert process.wait(timeout=3) == 0
    assert not path.exists(), "graceful shutdown left its socket behind"


def main():
    source = pathlib.Path(__file__).resolve().parents[1] / "theos/scan-supervisor/main.c"
    with tempfile.TemporaryDirectory(prefix="openhc-helper-it-") as directory:
        root = pathlib.Path(directory)
        path = root / "ping.sock"
        binary = root / "helper"
        define = f'-DOHC_SCAN_HELPER_TEST_SOCKET_PATH="{path}"'
        subprocess.run(["clang", "-std=c11", "-Wall", "-Wextra", "-Werror",
                        "-DOHC_SCAN_HELPER_TEST_BUILD", define, str(source), "-o", str(binary)],
                       check=True)
        command = [str(binary)]

        # Model an overlong runtime relocation: production must fail closed
        # before opening a lock or truncating the AF_UNIX path.
        long_binary = root / "helper-long-path"
        long_path = str(root / ("r" * 120))
        assert len(long_path.encode("utf-8")) >= 104
        long_define = f'-DOHC_SCAN_HELPER_TEST_SOCKET_PATH="{long_path}"'
        subprocess.run(["clang", "-std=c11", "-Wall", "-Wextra", "-Werror",
                        "-DOHC_SCAN_HELPER_TEST_BUILD", long_define,
                        str(source), "-o", str(long_binary)], check=True)
        long_result = subprocess.run([str(long_binary)], timeout=3)
        assert long_result.returncode == 11, "overlong socket path did not fail closed at the path guard"
        assert not pathlib.Path(long_path + ".lock").exists(), "overlong path guard ran after lock creation"
        print("PASS overlong relocated socket path rejected before filesystem changes")

        helper = subprocess.Popen(command)
        wait_for_path(path, helper)
        with connect(path) as client:
            client.sendall(b"PING\n")
            client.shutdown(socket.SHUT_WR)
            assert client.recv(16) == b"PONG\n"
            assert client.recv(1) == b""
        print("PASS independent process fixed PING/PONG")

        with connect(path) as client:
            client.sendall(b"NOPE\n")
            client.shutdown(socket.SHUT_WR)
            assert client.recv(16) == b""
        with connect(path) as client:
            client.sendall(b"12345678")
            assert client.recv(1) == b""
        print("PASS malformed and oversized frames rejected")

        second = subprocess.run(command, timeout=3)
        assert second.returncode != 0 and path.exists(), "second instance disturbed active socket"
        print("PASS concurrent second instance rejected without unlink")

        slow = connect(path)
        slow.sendall(b"P")
        time.sleep(1.8)
        assert slow.recv(1) == b"", "slow request survived helper deadline"
        slow.close()
        print("PASS slow request closed at bounded deadline")

        stop(helper, path)
        print("PASS SIGTERM cleanup")

        restarted = subprocess.Popen(command)
        wait_for_path(path, restarted)
        with connect(path) as client:
            client.sendall(b"PING\n")
            client.shutdown(socket.SHUT_WR)
            assert client.recv(16) == b"PONG\n"
        stop(restarted, path)
        print("PASS restart after graceful cleanup")

    print("SCAN_SUPERVISOR_CROSS_PROCESS_INTEGRATION_OK")


if __name__ == "__main__":
    main()
