#include "ScanQRBitmap.h"
#include "vendor/qrcodegen/qrcodegen.h"
#include <stdlib.h>
#include <string.h>

bool OHCScanQRCreate(const uint8_t *utf8, size_t length, int scale, OHCScanQRBitmap *result) {
    if (!result) return false;
    *result = (OHCScanQRBitmap){0};
    if (!utf8 || !length || length > OHC_SCAN_QR_MAX_UTF8_BYTES || scale < 1 || scale > 12)
        return false;
    uint8_t data[OHC_SCAN_QR_MAX_UTF8_BYTES], eci[3];
    uint8_t temporary[qrcodegen_BUFFER_LEN_MAX], qr[qrcodegen_BUFFER_LEN_MAX];
    struct qrcodegen_Segment segments[] = {
        qrcodegen_makeEci(26, eci),
        qrcodegen_makeBytes(utf8, length, data),
    };
    if (!qrcodegen_encodeSegmentsAdvanced(segments, 2, qrcodegen_Ecc_MEDIUM,
            qrcodegen_VERSION_MIN, qrcodegen_VERSION_MAX, qrcodegen_Mask_AUTO,
            false, temporary, qr)) return false;
    int modules = qrcodegen_getSize(qr);
    size_t edge = (size_t)(modules + 8) * (size_t)scale;
    uint8_t *pixels = malloc(edge * edge);
    if (!pixels) return false;
    memset(pixels, 255, edge * edge);
    for (int y = 0; y < modules; y++) for (int x = 0; x < modules; x++) {
        if (!qrcodegen_getModule(qr, x, y)) continue;
        for (int row = 0; row < scale; row++) {
            size_t offset = ((size_t)(y + 4) * (size_t)scale + (size_t)row) * edge
                + (size_t)(x + 4) * (size_t)scale;
            memset(pixels + offset, 0, (size_t)scale);
        }
    }
    *result = (OHCScanQRBitmap){ .pixels = pixels, .edge = edge, .modules = modules };
    return true;
}
