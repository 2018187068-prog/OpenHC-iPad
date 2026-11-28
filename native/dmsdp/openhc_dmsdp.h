#ifndef OPENHC_DMSDP_H
#define OPENHC_DMSDP_H
/* Per-frame AES128-CTR using system CommonCrypto; no retained key or context. */
int oh_dmsdp_ctr(const unsigned char *key, int key_size, const unsigned char *iv, int iv_size,
                 const unsigned char *input, int input_size, unsigned char *out, int capacity);
#endif
