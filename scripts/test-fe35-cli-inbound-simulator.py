"""Drive the real FE35 CLI/Kotlin Native bridge with a local synthetic BTstack peer."""
import argparse
import hashlib
import hmac
import importlib.util
from pathlib import Path
import shutil
import socket
import struct
import subprocess
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "btstack_socket_fixture", ROOT / "scripts/test-btstack-transport-socket.py")
_fixture = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_fixture)

DEVICE_ID = b"CD1C73F369C5FE0B80808D3D0335EAF7D99B2AB9FE15403DC621C166FBADCB6F"
ROOT_KEY = bytes(16)
CONST_A = bytes(range(0x10, 0x20))
CONST_B = bytes(range(0x20, 0x30))
PHONE_FIRST = bytes.fromhex(_fixture.UPSTREAM_PHONE_FIRST)
EXPECTED_HANDSHAKE_REPLY = bytes.fromhex(
    "82810284c043443143373346333639433546453042383038303844334430333335"
    "454146374439394232414239464531353430334443363231433136364642414443"
    "423646868101")
EXPECTED_COMMAND4 = bytes.fromhex(
    "84a0809182938968696361724175746880900000fe3600001000800000805f9b34fb")
ASSERTIONS = 0
ASSERTION_LOCK = threading.Lock()


def check(condition, label):
    global ASSERTIONS
    with ASSERTION_LOCK:
        ASSERTIONS += 1
    if not condition:
        raise AssertionError(label)


def exact(conn, count):
    result = bytearray()
    while len(result) < count:
        part = conn.recv(count - len(result))
        if not part:
            raise EOFError("peer closed before frame was complete")
        result.extend(part)
    return bytes(result)


def read_packet(conn):
    kind, channel, size = struct.unpack("<HHH", exact(conn, 6))
    return kind, channel, exact(conn, size)


def send_packet(conn, kind, channel, body):
    conn.sendall(struct.pack("<HHH", kind, channel, len(body)) + body)


def send_event(conn, code, params):
    send_packet(conn, 4, 0, bytes([code, len(params)]) + params)


def read_command(conn, ocf, params):
    kind, channel, size = struct.unpack("<HHH", exact(conn, 6))
    check((kind, channel, size) == (1, 0, len(params) + 3),
          "command header expected_ocf=" + hex(0xF400 | ocf) +
          " actual=(kind=" + str(kind) + ",channel=" + str(channel) + ",size=" + str(size) + ")")
    packet = exact(conn, size)
    opcode, length = struct.unpack("<HB", packet[:3])
    body = packet[3:]
    check(opcode == (0xF400 | ocf), "command opcode")
    check(length == len(params), "command parameter length")
    check(body == params, "command parameters")


def ea(value):
    result = bytearray()
    while True:
        group = value & 0x7f
        value >>= 7
        result.append(group | (0x80 if value == 0 else 0))
        if value == 0:
            return bytes(result)


def read_ea(data, offset):
    value = 0
    for index in range(4):
        byte = data[offset + index]
        value |= (byte & 0x7f) << (7 * index)
        if byte & 0x80:
            return value, offset + index + 1
    raise AssertionError("unterminated EA")


def crc16_arc(data):
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ (0xA001 if crc & 1 else 0)
    return crc


def cipher_material(seed):
    h1 = bytes(CONST_A[(i + 3) % 16] ^ CONST_B[i] for i in range(16))
    derived = bytes(h1[(i - 5 + 16) % 16] ^ ROOT_KEY[i] for i in range(16))
    material = hmac.new(derived, seed, hashlib.sha256).digest()
    return material[:16], material[16:32]


def aes_cfb(data, seed, decrypt=False):
    key, iv = cipher_material(seed)
    operation = "-d" if decrypt else "-e"
    result = subprocess.run(
        ["openssl", "enc", operation, "-aes-128-cfb", "-K", key.hex(), "-iv", iv.hex(), "-nopad"],
        input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode:
        raise RuntimeError("synthetic AES-CFB operation failed")
    return result.stdout


def encrypted_frame(outer_type, plaintext, seed):
    encrypted = aes_cfb(plaintext, seed)
    flags = ea(1) + ea(10) + ea(1) + ea(8) + seed
    body = b"\x7f" + ea(outer_type) + flags + ea(len(encrypted)) + encrypted
    return body + struct.pack("<H", crc16_arc(body))


def decode_frame(frame):
    check(len(frame) >= 8 and frame[0] == 0x7f, "Nearby frame header")
    check(struct.unpack("<H", frame[-2:])[0] == crc16_arc(frame[:-2]), "Nearby frame CRC")
    outer, pos = read_ea(frame, 1)
    flag, pos = read_ea(frame, pos)
    flag_size, pos = read_ea(frame, pos)
    flag_bytes = frame[pos:pos + flag_size]
    pos += flag_size
    size, pos = read_ea(frame, pos)
    payload = frame[pos:pos + size]
    check(pos + size + 2 == len(frame), "Nearby frame exact length")
    seed = None
    if flag & 1:
        tag, at = read_ea(flag_bytes, 0)
        seed_size, at = read_ea(flag_bytes, at)
        check(tag == 1 and seed_size == 8 and at + seed_size == len(flag_bytes), "Nearby seed TLV")
        seed = flag_bytes[at:]
        payload = aes_cfb(payload, seed, decrypt=True)
    return outer, flag, payload


def encrypted_command_request():
    request = ea(2) + ea(19) + ea(9) + b"hicarAuth" + ea(0)
    payload = ea(3) + ea(len(request)) + request
    return encrypted_frame(2, payload, bytes(range(0xd1, 0xd9)))


def assert_service_record(params, uuid, channel):
    check(uuid in params, "SDP UUID bytes")
    check(bytes([0x08, channel]) in params, "SDP RFCOMM channel bytes")
    check(b"\x09\x00\x04\x35\x0c" in params, "SDP protocol descriptor")


def register_channel(conn, channel, status):
    read_command(conn, 0x42, bytes([channel, 0, 2]))
    send_event(conn, 0x85, bytes([status, channel]))


def expect_cleanup(conn, expected_auth_channel=None, expected_auth_handle=None, include_disconnect=True):
    if expected_auth_handle is not None or expected_auth_channel is not None:
        if expected_auth_handle is not None:
            read_command(conn, 0x31, struct.pack("<I", expected_auth_handle))
        if expected_auth_channel is not None:
            read_command(conn, 0x43, bytes([expected_auth_channel, 0]))
        read_command(conn, 1, b"")
        send_event(conn, 0x60, bytes([2]))
    if include_disconnect:
        read_command(conn, 0x41, struct.pack("<HB", 0x2345, 0))
        send_event(conn, 0x81, struct.pack("<H", 0x2345))
    read_command(conn, 0x31, struct.pack("<I", 0x10001))
    read_command(conn, 0x43, bytes([16, 0]))
    read_command(conn, 1, b"")
    send_event(conn, 0x60, bytes([2]))


def drive_peer(conn, case, set_step):
    set_step("initial_state")
    conn.settimeout(4)
    read_command(conn, 1, b"")
    send_event(conn, 0x60, bytes([2]))
    set_step("register_control_channel")
    register_channel(conn, 16, 0)

    set_step("register_fe35_sdp")
    kind, channel, sdp = read_packet(conn)
    check((kind, channel, sdp[:3]) == (1, 0, bytes([0x30, 0xf4, len(sdp) - 3])), "control SDP command")
    check(b"\x19\xfe\x35" in sdp[3:], "FE35 service registration")
    assert_service_record(sdp[3:], b"\x19\xfe\x35", 16)
    send_event(conn, 0x90, bytes([0]) + struct.pack("<I", 0x10001))

    if case == "incoming_timeout":
        expect_cleanup(conn, include_disconnect=False)
        return

    cid = 0x2345
    set_step("incoming_and_open")
    send_event(conn, 0x82, bytes.fromhex("a1a2a3a4a5a6") + bytes([16]) + struct.pack("<H", cid))
    read_command(conn, 0x44, struct.pack("<H", cid))
    send_event(conn, 0x80, bytes([0]) + bytes.fromhex("010203040506") +
               struct.pack("<H", 0x5678) + bytes([16]) + struct.pack("<HHB", cid, 512, 1))

    kind, channel, start = read_packet(conn)
    set_step("bridge_start")
    check((kind, channel) == (7, cid), "bridge start transport header")
    start_outer, start_flag, _ = decode_frame(start)
    check((start_outer, start_flag) == (0, 0), "bridge start frame bytes")

    request = encrypted_command_request()
    split = len(PHONE_FIRST) // 3
    set_step("fragmented_phone_first_and_encrypted_request")
    send_packet(conn, 7, cid, PHONE_FIRST[:split])
    send_packet(conn, 7, cid, PHONE_FIRST[split:] + request)
    kind, channel, handshake_reply = read_packet(conn)
    set_step("encrypted_handshake_response")
    check((kind, channel) == (7, cid), "handshake reply transport header")
    outer, flag, payload = decode_frame(handshake_reply)
    check((outer, flag, payload) == (0, 1, EXPECTED_HANDSHAKE_REPLY), "handshake reply frame bytes")

    set_step("register_auth_listener_channel")
    register_channel(conn, 16, 0x71)
    register_channel(conn, 17, 0)
    set_step("register_auth_sdp")
    kind, channel, sdp = read_packet(conn)
    check((kind, channel, sdp[:3]) == (1, 0, bytes([0x30, 0xf4, len(sdp) - 3])), "auth SDP command")
    uuid128 = bytes.fromhex("1c0000fe3600001000800000805f9b34fb")
    check(uuid128 in sdp[3:], "auth SDP UUID128 callback")
    assert_service_record(sdp[3:], uuid128, 17)

    if case == "listener_registration_failure":
        send_event(conn, 0x90, bytes([1]) + struct.pack("<I", 0))
        expect_cleanup(conn, expected_auth_channel=17)
        return

    set_step("auth_listener_ready")
    send_event(conn, 0x90, bytes([0]) + struct.pack("<I", 0x10002))
    set_step("encrypted_command4_response")
    kind, channel, response_frame = read_packet(conn)
    check((kind, channel) == (7, cid), "listener response transport header")
    outer, flag, payload = decode_frame(response_frame)
    check((outer, flag) == (2, 1), "encrypted command4 frame marker")
    check(payload == EXPECTED_COMMAND4, "encrypted command4 plaintext bytes")
    check(payload.startswith(b"\x84"), "command4 TLV tag")
    check(b"\x91\x82\x93" in payload, "command4 channel and business id")
    check(b"\xfe\x36\x00\x00\x10\x00\x80\x00\x00\x80\x5f\x9b\x34\xfb" in payload,
          "command4 UUID bytes")
    set_step("disconnect_and_cleanup")
    send_event(conn, 0x81, struct.pack("<H", cid))
    expect_cleanup(conn, expected_auth_channel=17, expected_auth_handle=0x10002)


def run_case(args, case):
    global ASSERTIONS
    started_assertions = ASSERTIONS
    data_dir = Path(args.data_dir)
    documents = data_dir / "Documents"
    guard = documents / ("fe35-guard-" + case)
    guard.mkdir(parents=True, exist_ok=True)
    (guard / "ready").write_text("READY\n", encoding="ascii")
    (guard / "deadline").write_text(str(int(time.time()) + 120) + "\n", encoding="ascii")
    (guard / "heartbeat").write_text("POWER_DRIVER_OWNS_THIS\n", encoding="ascii")
    result_file = documents / "fe35-cli-result"
    result_file.unlink(missing_ok=True)
    errors = []
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", 0))
    endpoint = "tcp:" + str(server.getsockname()[1])
    server.listen(1)
    server.settimeout(8)

    def serve():
        peer_step = ["accept"]
        try:
            with server.accept()[0] as conn:
                drive_peer(conn, case, lambda value: peer_step.__setitem__(0, value))
        except Exception as exc:
            errors.append((peer_step[0], repr(exc)))

    worker = threading.Thread(target=serve, daemon=True)
    worker.start()
    guard_rel = "Documents/" + guard.name
    started = time.monotonic()
    launch = subprocess.run([
        "xcrun", "simctl", "launch", args.udid, args.bundle_id,
        endpoint, guard_rel,
    ], capture_output=True, text=True, timeout=12)
    check(launch.returncode == 0, "simulator CLI process launched")
    expected_status = 0 if case == "success" else 1
    for _ in range(60):
        if result_file.exists():
            break
        time.sleep(0.25)
    check(result_file.exists(), "CLI bounded completion result")
    actual_status = result_file.read_text(encoding="ascii").strip()
    worker.join(8)
    server.close()
    check(not worker.is_alive(), "synthetic peer completed")
    cli_log = documents / "fe35-cli-status.log"
    cli_status = cli_log.read_text(encoding="ascii", errors="replace") if cli_log.exists() else "missing"
    check(not errors, "synthetic peer assertions: " + repr(errors) + "; CLI status log: " + cli_status)
    check(actual_status == str(expected_status),
          "CLI result status expected=" + str(expected_status) + " actual=" + actual_status +
          "; CLI status log: " + cli_status)
    check((guard / "heartbeat").read_text(encoding="ascii") == "POWER_DRIVER_OWNS_THIS\n",
          "Trial remains heartbeat owner")
    shutil.rmtree(guard)
    elapsed = time.monotonic() - started
    check(elapsed < 10, "bounded CLI scenario completion")
    print("FE35_KN_INBOUND_CASE_OK=" + case)
    print("FE35_KN_INBOUND_CASE_ASSERTIONS=" + str(ASSERTIONS - started_assertions))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--udid", required=True)
    parser.add_argument("--bundle-id", required=True)
    parser.add_argument("--data-dir", required=True)
    args = parser.parse_args()
    for case in ("success", "listener_registration_failure", "incoming_timeout"):
        run_case(args, case)
    print("FE35_KN_INBOUND_ASSERTIONS=" + str(ASSERTIONS))


if __name__ == "__main__":
    main()
