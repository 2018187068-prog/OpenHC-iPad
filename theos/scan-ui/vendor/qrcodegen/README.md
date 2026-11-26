# Vendored CPU QR encoder

Project Nayuki QR-Code-generator v1.8.0, fixed commit
`720f62bddb7226106071d4728c292cb1df519ceb`.
Primary source: https://github.com/nayuki/QR-Code-generator/tree/720f62bddb7226106071d4728c292cb1df519ceb/c

`qrcodegen.c` and `qrcodegen.h` are unmodified upstream files with MIT license headers.
SHA-256:
- qrcodegen.c: `300eff07ee25baaa7578f20284411638154716379437391e7e689c0e6ce81403`
- qrcodegen.h: `e82df4bff37d18b5863b9e7486fe6bda1b6cda8c3b9ecebfec473907265cb589`

The same copyright and license text ships inside the application as
`QR-Code-generator-LICENSE.txt`. ScanQRBitmap.c bounds input at 1024 UTF-8
bytes, uses ECI 26 plus a byte segment and fixed ECC M, and rasterizes only
black/white pixels with a four-module border and integer scale 1..12.
Production QR encoding/rendering uses no Core Image, GL, GPU, dynamic loading,
network, identity files, or external process. System Core Image decoding remains
only in the Simulator acceptance test, independently of this CPU renderer.
