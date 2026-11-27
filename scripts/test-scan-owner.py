"""Run the actual portable owner core; only OS evidence/lease effects are fake.
No device, socket, identity, Trial or controller operation is performed here.
"""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
compiler = [shutil.which("zig"), "cc"] if shutil.which("zig") else [shutil.which("cc") or "cc"]
with tempfile.TemporaryDirectory(prefix="openhc-owner-") as tmp:
    for test in (False, True):
        exe = Path(tmp) / ("owner-test" if test else "owner-deny")
        if os.name == "nt": exe = exe.with_suffix(".exe")
        cmd = compiler + ["-std=c11", "-Wall", "-Wextra", "-Werror"]
        if test: cmd += ["-DOPENHC_SCAN_OWNER_TEST"]
        cmd += [str(ROOT / p) for p in ("theos/scan-owner/ScanOwner.c",
            "theos/scan-owner/ScanOwnerPeer.c", "scripts/scan-owner-tests.c")]
        subprocess.run(cmd + ["-o", str(exe)], check=True, timeout=120)
        subprocess.run([str(exe)], check=True, timeout=10)
