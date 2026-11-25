#include "openhc_crypto.h"
#include <openssl/evp.h>
#include <openssl/hmac.h>
#include <openssl/bn.h>
#include <openssl/crypto.h>
#include <openssl/err.h>

int oh_crypto(int op, const unsigned char *key, int nk,
    const unsigned char *a, int na, const unsigned char *b, int nb,
    const unsigned char *c, int nc, unsigned char *out, int capacity) {
    int ok = 0, n = 0, total = 0;
    unsigned int written = 0;
    size_t size = capacity < 0 ? 0 : (size_t)capacity;
    EVP_CIPHER_CTX *ctx = NULL;
    EVP_PKEY *pk = NULL, *peer = NULL;
    EVP_PKEY_CTX *pctx = NULL;
    EVP_MD_CTX *md = NULL;
    BN_CTX *bnctx = NULL;
    BIGNUM *base = NULL, *exp = NULL, *prime = NULL, *result = NULL;
    if(nk < 0 || na < 0 || nb < 0 || nc < 0 || capacity < 0) return 0;
    ERR_clear_error();
    switch(op) {
    case 1:
        if(capacity != 32) break;
        ok = EVP_Digest(a, na, out, &written, EVP_sha256(), NULL) == 1 && written == 32;
        break;
    case 2:
        if(capacity != 32) break;
        ok = HMAC(EVP_sha256(), key, nk, a, na, out, &written) != NULL && written == 32;
        break;
    case 3: case 4: {
        const EVP_CIPHER *cipher = nk == 16 ? EVP_aes_128_gcm() : nk == 24 ? EVP_aes_192_gcm() : nk == 32 ? EVP_aes_256_gcm() : NULL;
        if(!cipher || na == 0 || (op == 3 && capacity != nc + 16) || (op == 4 && (nc < 16 || capacity != nc - 16))) break;
        ctx = EVP_CIPHER_CTX_new();
        if(!ctx) break;
        if(op == 3) {
            if(EVP_EncryptInit_ex(ctx, cipher, NULL, NULL, NULL) != 1 ||
               EVP_CIPHER_CTX_ctrl(ctx, EVP_CTRL_GCM_SET_IVLEN, na, NULL) != 1 ||
               EVP_EncryptInit_ex(ctx, NULL, NULL, key, a) != 1) break;
            if(nb && EVP_EncryptUpdate(ctx, NULL, &n, b, nb) != 1) break;
            if(nc && EVP_EncryptUpdate(ctx, out, &n, c, nc) != 1) break;
            total = nc ? n : 0;
            if(EVP_EncryptFinal_ex(ctx, out + total, &n) != 1) break;
            total += n;
            if(total != nc || EVP_CIPHER_CTX_ctrl(ctx, EVP_CTRL_GCM_GET_TAG, 16, out + total) != 1) break;
            ok = 1;
        } else {
            if(EVP_DecryptInit_ex(ctx, cipher, NULL, NULL, NULL) != 1 ||
               EVP_CIPHER_CTX_ctrl(ctx, EVP_CTRL_GCM_SET_IVLEN, na, NULL) != 1 ||
               EVP_DecryptInit_ex(ctx, NULL, NULL, key, a) != 1) break;
            if(nb && EVP_DecryptUpdate(ctx, NULL, &n, b, nb) != 1) break;
            if(nc > 16 && EVP_DecryptUpdate(ctx, out, &n, c, nc - 16) != 1) break;
            total = nc > 16 ? n : 0;
            if(EVP_CIPHER_CTX_ctrl(ctx, EVP_CTRL_GCM_SET_TAG, 16, (void *)(c + nc - 16)) != 1) break;
            if(EVP_DecryptFinal_ex(ctx, out + total, &n) != 1) break;
            ok = total + n == capacity;
        }
        break;
    }
    case 5: case 6: case 7: case 8: case 9: {
        const char *algorithm = op <= 7 ? "ED25519" : "X25519";
        if(nk != 32) break;
        pk = op == 7 ? EVP_PKEY_new_raw_public_key_ex(NULL,algorithm,NULL,key,nk) :
                       EVP_PKEY_new_raw_private_key_ex(NULL,algorithm,NULL,key,nk);
        if(!pk) break;
        if(op == 5 || op == 8) {
            if(capacity != 32) break;
            ok = EVP_PKEY_get_raw_public_key(pk, out, &size) == 1 && size == 32;
        } else if(op == 6 || op == 7) {
            md = EVP_MD_CTX_new(); if(!md) break;
            if(op == 6) {
                if(capacity != 64 || EVP_DigestSignInit(md,NULL,NULL,NULL,pk) != 1) break;
                ok = EVP_DigestSign(md,out,&size,a,na) == 1 && size == 64;
            } else {
                if(nb != 64 || capacity != 1 || EVP_DigestVerifyInit(md,NULL,NULL,NULL,pk) != 1) break;
                ok = EVP_DigestVerify(md,b,nb,a,na) == 1;
                if(ok) out[0] = 1;
            }
        } else {
            if(na != 32 || capacity != 32) break;
            peer = EVP_PKEY_new_raw_public_key_ex(NULL,"X25519",NULL,a,na);
            pctx = EVP_PKEY_CTX_new(pk,NULL);
            if(!peer || !pctx || EVP_PKEY_derive_init(pctx) != 1 || EVP_PKEY_derive_set_peer(pctx,peer) != 1) break;
            ok = EVP_PKEY_derive(pctx,out,&size) == 1 && size == 32;
            if(ok) { unsigned int nonzero = 0; for(int i=0;i<32;i++) nonzero |= out[i]; ok = nonzero != 0; }
        }
        break;
    }
    case 10: case 11:
        if(nc != 384 && nc != 256) break;
        prime = BN_bin2bn(c,nc,NULL);
        base = nk ? BN_bin2bn(key,nk,NULL) : BN_new();
        if(!prime || !base) break;
        if(op == 11) {
            if(capacity != 1 || nk > nc || BN_cmp(base,BN_value_one()) <= 0 || !BN_sub_word(prime,1)) break;
            ok = BN_cmp(base,prime) < 0;
            if(ok) out[0] = 1;
        } else {
            if(capacity != nc) break;
            exp = na ? BN_bin2bn(a,na,NULL) : BN_new();
            result = BN_new(); bnctx = BN_CTX_new();
            if(!exp || !result || !bnctx) break;
            BN_set_flags(exp, BN_FLG_CONSTTIME);
            ok = BN_mod_exp_mont_consttime(result,base,exp,prime,bnctx,NULL) == 1 && BN_bn2binpad(result,out,capacity) == capacity;
        }
        break;
    }
    EVP_CIPHER_CTX_free(ctx); EVP_MD_CTX_free(md); EVP_PKEY_CTX_free(pctx);
    EVP_PKEY_free(peer); EVP_PKEY_free(pk);
    BN_clear_free(base); BN_clear_free(exp); BN_free(prime); BN_clear_free(result); BN_CTX_free(bnctx);
    if(!ok && capacity) OPENSSL_cleanse(out,capacity);
    ERR_clear_error(); /* Never expose backend diagnostics or key material. */
    return ok;
}
