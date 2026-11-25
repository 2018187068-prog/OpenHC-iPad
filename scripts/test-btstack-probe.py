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

    def element(data, offset=0):
        """Independent minimal SDP DataElement decoder for emitted attributes."""
        tag = data[offset]
        kind, index = tag >> 3, tag & 7
        offset += 1
        if index < 5:
            length = 1 << index
        else:
            width = 1 << (index - 5)
            length = int.from_bytes(data[offset:offset + width], "big")
            offset += width
        end = offset + length
        assert end <= len(data)
        if kind == 6:
            values = []
            while offset < end:
                value, offset = element(data, offset)
                values.append(value)
            assert offset == end
            return (kind, values), end
        return (kind, int.from_bytes(data[offset:end], "big")), end

    service_cases = ["success", "busy_skip", "state_not_off", "no_channels",
                     "allocation_failed", "first_sdp_failed", "second_sdp_failed",
                     "wrong_registration_channel"]
    for case in service_cases:
        endpoint = str(Path(directory) / "s")
        errors, history = [], []
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
            server.bind(endpoint)
            server.listen(1)
            server.settimeout(8)

            def service_server():
                next_handle = 0x10001
                try:
                    connections = 2 if case in ("success", "busy_skip") else 1
                    for cycle in range(connections):
                        owned, handles = set(), {}
                        with server.accept()[0] as conn:
                            conn.settimeout(6)
                            while True:
                                first = conn.recv(1)
                                if not first:
                                    break
                                header = first + exact(conn, 5)
                                packet_type, channel, size = struct.unpack("<HHH", header)
                                assert packet_type == 1 and channel == 0 and 3 <= size <= 258
                                packet = exact(conn, size)
                                opcode, length = struct.unpack("<HB", packet[:3])
                                assert opcode >> 10 == 0x3d and length == size - 3
                                ocf, params = opcode & 0x3ff, packet[3:]
                                # There must never be power/discoverability/pairing commands.
                                assert ocf in (1, 0x42, 0x43, 0x30, 0x31), ocf
                                history.append((cycle, ocf, params))
                                if ocf == 1:
                                    assert not params
                                    state = 2 if case == "state_not_off" else 0
                                    conn.sendall(frame(bytes([0x60, 1, state])))
                                elif ocf == 0x42:
                                    number, mtu = struct.unpack("<BH", params)
                                    assert 16 <= number <= 23 and mtu == 512
                                    assert number not in owned
                                    busy = case == "no_channels" or (case == "busy_skip" and number == 16)
                                    status = 0x71 if busy else (0x56 if case == "allocation_failed" else 0)
                                    if not status:
                                        owned.add(number)
                                    returned = number + 1 if case == "wrong_registration_channel" else number
                                    conn.sendall(frame(bytes([0x85, 2, status, returned])))
                                elif ocf == 0x30:
                                    record, end = element(params)
                                    assert end == len(params) and record[0] == 6
                                    values = record[1]
                                    assert len(values) == 6
                                    attrs = {}
                                    for i in range(0, len(values), 2):
                                        assert values[i][0] == 1
                                        attrs[values[i][1]] = values[i + 1]
                                    assert list(attrs) == [1, 4, 5]
                                    uuid = attrs[1][1][0]
                                    assert uuid in ((3, 0xfe35), (3, 0xfe36))
                                    protocols = attrs[4][1]
                                    assert protocols[0] == (6, [(3, 0x100)])
                                    assert protocols[1][0] == 6 and protocols[1][1][0] == (3, 3)
                                    rfcomm_channel = protocols[1][1][1]
                                    assert rfcomm_channel[0] == 1 and rfcomm_channel[1] in owned
                                    assert attrs[5] == (6, [(3, 0x1002)])
                                    failed = ((case == "first_sdp_failed" and uuid[1] == 0xfe35) or
                                              (case == "second_sdp_failed" and uuid[1] == 0xfe36))
                                    handle = 0 if failed else next_handle
                                    if not failed:
                                        handles[handle] = (uuid[1], rfcomm_channel[1])
                                        next_handle += 1
                                    conn.sendall(frame(bytes([0x90, 5, 0x56 if failed else 0]) + struct.pack("<I", handle)))
                                elif ocf == 0x31:
                                    handle, = struct.unpack("<I", params)
                                    assert handle in handles, "must only remove owned SDP handles"
                                    del handles[handle]
                                elif ocf == 0x43:
                                    number, = struct.unpack("<H", params)
                                    assert number in owned, "must never remove a busy/unowned channel"
                                    owned.remove(number)
                        if case == "wrong_registration_channel":
                            # Client cannot attest ownership from a malformed response;
                            # it must close rather than unregister an untrusted channel.
                            assert not any(op == 0x43 for _, op, _ in history)
                        else:
                            assert not owned and not handles, "explicit cleanup missing"
                except Exception as error:
                    errors.append(error)

            worker = threading.Thread(target=service_server, daemon=True)
            worker.start()
            completed = subprocess.run([executable, endpoint, "--services"], capture_output=True,
                                       text=True, timeout=20)
            worker.join(7)
            assert not worker.is_alive(), "service mock did not finish"
            assert not errors, (case, errors, completed.stdout)
            success = case in ("success", "busy_skip")
            assert completed.returncode == (0 if success else 1), (case, completed.stdout)
            assert ("BTSTACK_LOCAL_SERVICES_OK" in completed.stdout) == success, case
            if success:
                assert "BTSTACK_LOCAL_SERVICE_CYCLE_OK=2" in completed.stdout
                first_channel = 17 if case == "busy_skip" else 16
                assert completed.stdout.count(f"BTSTACK_FE35_LOCAL_CHANNEL={first_channel}\n") == 2
                assert completed.stdout.count(f"BTSTACK_FE36_LOCAL_CHANNEL={first_channel + 1}\n") == 2
                # Exact same channels must be reusable across close/reconnect.
                regs = [(cycle, params[0]) for cycle, op, params in history if op == 0x42]
                assert regs[-2:] == [(1, first_channel), (1, first_channel + 1)]
            else:
                assert "BTSTACK_SERVICES_FAILED=" in completed.stdout
            print("BTSTACK_SERVICE_MOCK_CASE_OK=" + case)
        os.unlink(endpoint)
    print("BTSTACK_SERVICE_MOCK_TESTS_OK=8")
