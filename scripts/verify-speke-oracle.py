"""Independent synthetic oracle; outputs status only, never derived bytes."""
from pathlib import Path
import re, hashlib, hmac
root = Path(__file__).resolve().parent.parent
reference = (root / "bridge/src/jvmMain/kotlin/io/github/gcbond/openhc/core/auth/crypto/AuthCrypto.kt").read_text(encoding="utf-8")
probe = (root / "bridge/src/commonMain/kotlin/io/github/gcbond/openhc/bridge/auth/SpekeMathProbe.kt").read_text(encoding="utf-8")
prime_hex = "".join(re.findall(r'"([0-9A-F]+)"', reference.split("val P3072:")[1].split("val P2048:")[0]))
assert len(prime_hex) == 768 and prime_hex in probe, "PRIME_SOURCE_MISMATCH"
p = int(prime_hex, 16)
def hkdf(ikm, salt, info, length):
    prk = hmac.new(salt, ikm, hashlib.sha256).digest()
    output = b""
    previous = b""
    counter = 1
    while len(output) < length:
        previous = hmac.new(prk, previous + info + bytes([counter]), hashlib.sha256).digest()
        output += previous
        counter += 1
    return output[:length]
salt = bytes(range(16))
generator = pow(int.from_bytes(hkdf(b"314159", salt, b"hichain_speke_base_info", 32), "big"), 2, p)
a, b = int.from_bytes(bytes(range(1,33)), "big"), int.from_bytes(bytes(range(33,65)), "big")
ap, bp = pow(generator,a,p), pow(generator,b,p)
assert pow(bp,a,p) == pow(ap,b,p), "SHARED_MISMATCH"
shared = pow(bp,a,p).to_bytes(384,"big")
okm = hkdf(shared,salt,b"hichain_speke_sessionkey_info",32)
proof = hmac.new(okm[16:] + bytes(16), bytes(range(32)), hashlib.sha256).digest()
returned = hkdf(okm[:16],salt,b"hichain_return_key",16)
fingerprint = hashlib.sha256(ap.to_bytes(384,"big") + bp.to_bytes(384,"big") + proof + returned).hexdigest()
assert 'hex("' + fingerprint + '")' in probe, "ORACLE_FINGERPRINT_MISMATCH"
print("SPEKE3072_PYTHON_ORACLE_OK")
