#ifndef OPENHC_CRYPTO_H
#define OPENHC_CRYPTO_H
/* Synthetic-probe adapter. Sizes are signed int to match EVP update APIs. */
int oh_crypto(int op, const unsigned char *key, int nk,
    const unsigned char *a, int na, const unsigned char *b, int nb,
    const unsigned char *c, int nc, unsigned char *out, int capacity);
int oh_random_bytes(unsigned char *out, int capacity);
#endif
