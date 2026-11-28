#!/usr/bin/env python3
"""Compile and execute the production FE35 cleanup-certainty predicate."""
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'scripts/fe35-cleanup-certainty-test.c'

with tempfile.TemporaryDirectory(prefix='fe35-cleanup-certainty-') as directory:
    executable = Path(directory) / 'fe35-cleanup-certainty-test'
    subprocess.run([
        'cc', '-std=c11', '-Wall', '-Wextra', '-Werror', str(SOURCE), '-o', str(executable),
    ], cwd=ROOT, check=True)
    subprocess.run([str(executable)], cwd=ROOT, check=True)
