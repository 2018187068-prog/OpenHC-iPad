#!/usr/bin/env python3
"""Compile and execute the production C QR rasterizer, without UIKit/GPU."""
import hashlib
import pathlib
import shutil
import subprocess
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
TEXT = ('hicar://car/connect?devicename=合成演示车机&mac=A0:B1:C2:D3:E4:F5'
        '&moduleid=A1B2C3&submoduleid=D4&pin=000007&ability=4')
# Golden raster from the independent upstream Python encoder at the same pinned
# revision: ECI26 + UTF8 bytes, ECC M, automatic mask, boostecl=False.
# python/qrcodegen.py SHA256 b089855caf16185c61421ea4927c1b213cf9468940d71fa8ab11ef83662dcc84
GOLDEN = '0d7c5433102f2f27ae97a13ca236d9f5cc999de052ebb25604180ba487c5fd67'


def main():
    zig = shutil.which('zig')
    compiler = ([shutil.which('cc')] if shutil.which('cc') else [zig, 'cc'] if zig else None)
    if compiler is None:
        raise SystemExit('A host C compiler or zig cc is required')
    encoded = ','.join(str(b) for b in TEXT.encode('utf-8'))
    harness = r'''
#include "ScanQRBitmap.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define CHECK(x) do { if (!(x)) return 2; } while (0)
int main(int argc, char **argv) {
    const uint8_t input[] = {INPUT_BYTES};
    OHCScanQRBitmap out;
    CHECK(argc == 2);
    CHECK(!OHCScanQRCreate(NULL, 1, 3, &out) && out.pixels == NULL);
    CHECK(!OHCScanQRCreate(input, 0, 3, &out) && out.pixels == NULL);
    CHECK(!OHCScanQRCreate(input, sizeof(input), 0, &out));
    CHECK(!OHCScanQRCreate(input, sizeof(input), 13, &out));
    CHECK(!OHCScanQRCreate(input, sizeof(input), 3, NULL));
    uint8_t maximum[1025]; memset(maximum, 'a', sizeof(maximum));
    CHECK(!OHCScanQRCreate(maximum, 1025, 3, &out));
    CHECK(OHCScanQRCreate(maximum, 1024, 12, &out)); free(out.pixels);
    for (int repeat = 0; repeat < 20; repeat++) {
        CHECK(OHCScanQRCreate(input, sizeof(input), 3, &out)); free(out.pixels);
    }
    int scale = atoi(argv[1]);
    CHECK(OHCScanQRCreate(input, sizeof(input), scale, &out));
    CHECK(out.modules == 49 && out.edge == (size_t)(out.modules + 8) * (size_t)scale);
    CHECK(fwrite(out.pixels, 1, out.edge * out.edge, stdout) == out.edge * out.edge);
    free(out.pixels);
    return 0;
}
'''.replace('INPUT_BYTES', encoded)
    with tempfile.TemporaryDirectory(prefix='openhc-cpu-qr-') as directory:
        root = pathlib.Path(directory)
        driver = root / 'test.c'
        driver.write_text(harness, encoding='utf-8')
        binary = root / ('qr-test.exe' if __import__('os').name == 'nt' else 'qr-test')
        project = ROOT / 'theos/scan-ui'
        subprocess.run(compiler + ['-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                       '-I'+str(project), str(driver), str(project/'ScanQRBitmap.c'),
                       str(project/'vendor/qrcodegen/qrcodegen.c'), '-o', str(binary)],
                       check=True, timeout=120)
        reference = subprocess.check_output([str(binary), '1'], timeout=20)
        assert hashlib.sha256(reference).hexdigest() == GOLDEN, 'UTF8/ECI/leading-zero matrix mismatch'
        for scale in (2, 3, 4):
            pixels = subprocess.check_output([str(binary), str(scale)], timeout=20)
            edge = 57 * scale
            assert len(pixels) == edge * edge
            for y in range(edge):
                for x in range(edge):
                    assert pixels[y*edge+x] == reference[(y//scale)*57+x//scale]
                    if min(x, y, edge-1-x, edge-1-y) < 4*scale:
                        assert pixels[y*edge+x] == 255, 'four-module quiet zone corrupted'
            print('SCAN_CPU_QR_GOLDEN_UTF8_BORDER_INTEGER_SCALE_OK='+str(scale))
        print('SCAN_CPU_QR_BOUNDS_AND_REPEATED_RENDER_OK')


if __name__ == '__main__':
    main()
