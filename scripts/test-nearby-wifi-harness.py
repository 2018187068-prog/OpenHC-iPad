"""Portable byte/socket regression of the exact Simulator negotiation driver.

Runs the production-fixture driver over real loopback sockets with injected Nearby framing
adapters. This validates the harness and packet order, NOT C/ObjC/Native or vendor interoperability;
those are separately executed by the combined Apple Simulator gate.
"""
import importlib.util
from pathlib import Path
import socket
import struct
import tempfile
import threading
from types import SimpleNamespace

root = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("cid", root / "test-fe36-cid-simulator.py")
cid = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cid)
spec2 = importlib.util.spec_from_file_location("wire", root / "test-fe35-cli-inbound-simulator.py")
wire = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(wire)
checks = 0

def check(value, label):
    global checks
    assert value, label
    checks += 1

def exact(conn, n):
    return wire.exact(conn, n)

# Keep this harness regression independent of an installed crypto binary. The real Simulator
# driver uses the real reference cipher functions; JVM covers encrypted common frame processing.
def frame(outer, payload, seed):
    return bytes([outer]) + struct.pack("!H", len(payload)) + payload
def decode(data):
    assert len(data) == 3 + struct.unpack("!H", data[1:3])[0]
    return data[0], 1, data[3:]

h = SimpleNamespace(ea=wire.ea, encrypted_frame=frame, decode_frame=decode,
                    read_packet=wire.read_packet, send_packet=wire.send_packet,
                    send_event=wire.send_event, crc16_arc=wire.crc16_arc, check=check)
def tlv(tag, value=b""):
    return wire.ea(tag) + wire.ea(len(value)) + value

for case in cid.WIFI_CASES:
    with tempfile.TemporaryDirectory(prefix="nearby-wifi-") as directory:
        guard = Path(directory) / 'guard'
        guard.mkdir()
        left, right = socket.socketpair()
        left.settimeout(4);right.settimeout(4)
        errors = []
        phases = []
        tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tcp.bind(("127.0.0.1", 0));tcp.listen(1);tcp.settimeout(4)
        port=tcp.getsockname()[1]
        (guard / "tcp-port").write_text(str(port))
        if case=="wifi_pending":
            # This is the injected state adapter; actual C emits it in Simulator.
            (guard.parent/"fe35-cli-status.log").write_text("BTSTACK_WIFI_NETWORK_PENDING\n")
            (guard/"tcp-port").unlink()
        def run():
            try: cid.wifi_negotiate(left,h,guard,case,phases.append)
            except BaseException as error: errors.append(error)
            finally: left.close()
        thread=threading.Thread(target=run);thread.start()
        def receive():
            raw=bytearray()
            while True:
                kind,channel,part=wire.read_packet(right)
                check((kind,channel)==(7,0x2345),"fragmented input uses FE35")
                check(0<len(part)<=17,"fixture deliberately fragments input")
                raw.extend(part)
                if len(raw)>=3 and len(raw)==3+struct.unpack("!H",raw[1:3])[0]:
                    return decode(raw)[::2]
        def send(outer,payload): wire.send_packet(right,7,0x2345,frame(outer,payload,b""))
        try:
            outer,request=receive()
            check(outer==4,"resource layer")
            if case=="wifi_malformed":
                check(request==tlv(1,b"\x83"),"actual truncated capability request")
            elif case=="wifi_unsupported":
                check(request==tlv(1,wire.ea(8)+tlv(3)),"unsupported WiFi channel request")
                send(4,tlv(2,wire.ea(8)+wire.ea(255)))
            else:
                check(request==tlv(1,wire.ea(3)+tlv(3)),"actual data-channel request golden")
                accepted=tlv(2,wire.ea(3)+wire.ea(1)+tlv(3,b"\x01"+wire.ea(2437)))
                send(4,accepted)
                if case=="wifi_duplicate":
                    check(receive()==(4,request),"duplicate resource request")
                    send(4,accepted)
                check(receive()==(4,tlv(7,wire.ea(3)+wire.ea(1))),"actual confirmation golden")
                (guard/"tcp-port").write_text(str(port))
                send(33,tlv(1))
                if case=="wifi_duplicate":
                    check(receive()==(4,tlv(7,wire.ea(3)+wire.ea(1))),"duplicate result stays ordered")
                check(receive()==(33,tlv(2,b"02:12:34:56:78:9a")),"MAC after listener request")
                info=("127.0.0.2##SYNTHETIC\n02:11:22:33:44:55\nsynthetic-pass\n2437"
                      "##version:3##"+str(port)+"##hicarApIp:127.0.0.1").encode()
                send(33,tlv(3,info))
                if case=="wifi_duplicate":
                    check(receive()==(33,tlv(2,b"02:12:34:56:78:9a")),"duplicate MAC stays ordered")
                if case=="wifi_disconnect":
                    check(wire.read_packet(right)==(4,0,b"\x81\x02\x45\x23"),"disconnect uses exact owned control CID")
                elif case not in ("wifi_stop","wifi_expiry"):
                    with tcp.accept()[0] as accepted_tcp:
                        address=accepted_tcp.getpeername()[0]
                        check(address=="127.0.0.1","real injected loopback proxy source")
            thread.join(4)
            check(not thread.is_alive() and not errors,"bounded driver completes "+case)
            if case == "wifi_success":
                check(any(p.startswith("wifi-response-packet-kind-actual-7-expected-7") for p in phases),
                      "response evidence records actual/expected packet type")
                check(any(p.startswith("wifi-response-decoded-outer-4-expected-4-encrypted-1-expected-1")
                          for p in phases), "response evidence records actual/expected Nearby framing")
            if case in ("wifi_stop","wifi_unsupported"):
                check((guard/"stop").read_text()=="STOP\n","explicit cancellation injection")
            if case=="wifi_pending":
                check((guard/"network-ready").read_text()=="SYNTHETIC_READY\n","explicit readiness injection")
        finally:
            right.close();tcp.close();thread.join(4)

print("NEARBY_WIFI_PORTABLE_HARNESS_CASES_OK="+str(len(cid.WIFI_CASES)))
print("NEARBY_WIFI_PORTABLE_HARNESS_ASSERTIONS_OK="+str(checks))
print("BOUNDARY=actual-loopback-fixture-driver;injected-framing-adapter;not-production-C-runtime")
