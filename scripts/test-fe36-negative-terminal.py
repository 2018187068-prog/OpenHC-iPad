"""Portable regression for the FE36 negative-auth close command boundary."""
import importlib.util
import struct
from pathlib import Path


source = Path(__file__).with_name("test-fe36-cid-simulator.py")
spec = importlib.util.spec_from_file_location("fe36_cid_simulator", source)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

cid = 0x3456
valid = struct.pack("<HBHB", 0xF441, 3, cid, 0)
assert module.consume_negative_auth_close(1, 0, valid, cid)

# The terminal command is consumed exactly once by the caller; malformed,
# wrong-CID, wrong-status, wrong-channel and extra-byte variants are not it
# and must remain available to strict cleanup parsing.
variants = (
    struct.pack("<HBHB", 0xF441, 3, cid ^ 1, 0),
    struct.pack("<HBHB", 0xF441, 3, cid, 1),
    valid + b"\x00",
    struct.pack("<HBHB", 0xF441, 2, cid, 0),
)
for body in variants:
    assert not module.consume_negative_auth_close(1, 0, body, cid)
assert not module.consume_negative_auth_close(1, 1, valid, cid)
assert not module.consume_negative_auth_close(7, 0, valid, cid)
print("FE36_NEGATIVE_TERMINAL_COMMAND_CHECKS=7")
