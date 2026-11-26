#ifndef OHC_SCAN_QR_BITMAP_H
#define OHC_SCAN_QR_BITMAP_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define OHC_SCAN_QR_MAX_UTF8_BYTES 1024
typedef struct {
    uint8_t *pixels;  /* malloc-owned, 8-bit grayscale, top row first */
    size_t edge;
    int modules;
} OHCScanQRBitmap;

/* CPU-only UTF-8 byte-mode QR, ECI 26, ECC M, four white modules per side. */
bool OHCScanQRCreate(const uint8_t *utf8, size_t length, int scale, OHCScanQRBitmap *result);
#endif
