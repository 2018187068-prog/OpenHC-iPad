#include "openhc_dmsdp.h"
#include <CommonCrypto/CommonCryptor.h>
#include <string.h>
static void wipe(unsigned char *p,size_t size) {
    volatile unsigned char *v=p;while(size--)*v++=0;
}
int oh_dmsdp_ctr(const unsigned char *key,int key_size,const unsigned char *iv,int iv_size,
                 const unsigned char *input,int input_size,unsigned char *out,int capacity) {
    if(!key || !iv || key_size!=16 || iv_size!=16 || input_size<0 || capacity!=input_size ||
       (input_size && (!input || !out))) return 0;
    if(!input_size)return 1;
    /* Pinned common/crypto/AesCtr increments the complete BE128 counter.
     * Use system AES-ECB and make carry explicit, independent of CTR provider. */
    unsigned char counter[16],stream[16];memcpy(counter,iv,sizeof(counter));
    CCCryptorRef cipher=NULL;
    CCCryptorStatus status=CCCryptorCreate(kCCEncrypt,kCCAlgorithmAES,kCCOptionECBMode,
        key,16,NULL,&cipher);
    for(int at=0;status==kCCSuccess && at<input_size;) {
        size_t moved=0;
        status=CCCryptorUpdate(cipher,counter,sizeof(counter),stream,sizeof(stream),&moved);
        if(status!=kCCSuccess || moved!=sizeof(stream)) {status=kCCUnspecifiedError;break;}
        int count=input_size-at;if(count>16)count=16;
        for(int i=0;i<count;i++)out[at+i]=input[at+i]^stream[i];
        at+=count;
        for(int i=15;i>=0;i--)if(++counter[i])break;
    }
    if(cipher)CCCryptorRelease(cipher);
    wipe(counter,sizeof(counter));wipe(stream,sizeof(stream));
    if(status!=kCCSuccess) {wipe(out,(size_t)capacity);return 0;}
    return 1;
}
