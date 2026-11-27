#include "ScanLeaseProtocol.h"
#include <limits.h>
#include <string.h>
static void put64(uint8_t *b,uint64_t n) {
    for(int i=7;i>=0;--i) { b[i]=(uint8_t)n; n>>=8; }
}
static uint64_t get64(const uint8_t *b) {
    uint64_t n=0;
    for(int i=0;i<8;++i) { n=(n<<8)|b[i]; }
    return n;
}
void ohc_lease_encode(uint8_t b[OHC_LEASE_FRAME_SIZE],const ohc_lease_frame *f) {
    memset(b,0,OHC_LEASE_FRAME_SIZE); memcpy(b,"OHCL",4); b[4]=1; b[5]=f->op;
    put64(b+8,f->generation); put64(b+16,f->sequence); put64(b+24,(uint64_t)f->deadline);
    for(int i=0;i<4;++i) { b[32+i]=(uint8_t)(f->flags>>(24-8*i)); b[36+i]=(uint8_t)((uint32_t)f->status>>(24-8*i)); }
}
bool ohc_lease_decode(ohc_lease_frame *f,const uint8_t b[OHC_LEASE_FRAME_SIZE]) {
    memset(f,0,sizeof(*f));
    if(memcmp(b,"OHCL",4)||b[4]!=1||b[6]||b[7]) { return false; }
    f->op=b[5]; f->generation=get64(b+8); f->sequence=get64(b+16);
    uint64_t deadline=get64(b+24);
    if(deadline>INT64_MAX) { return false; }
    f->deadline=(int64_t)deadline; uint32_t status=0;
    for(int i=0;i<4;++i) { f->flags=(f->flags<<8)|b[32+i]; status=(status<<8)|b[36+i]; }
    if(status>INT32_MAX) { return false; }
    f->status=(int32_t)status; return true;
}
bool ohc_lease_overdue(const ohc_lease_guard *s,int64_t now) {
    return s->armed && (now<0 || now>=s->deadline || now<s->heartbeat || now-s->heartbeat>=OHC_LEASE_HEARTBEAT_MS);
}
bool ohc_lease_step(ohc_lease_guard *s,const ohc_lease_frame *f,int64_t now) {
    if(!f->generation || now<0 || f->sequence!=s->sequence+1 || s->sequence==UINT64_MAX ||
       s->delegated || s->restored || (f->op!=OHC_L_COMPLETE && (f->flags||f->status))) { return false; }
    if(!s->armed) {
        if(f->op!=OHC_L_ARM || f->sequence!=1 || f->deadline<=now ||
           now>INT64_MAX-OHC_LEASE_MAX_MS || f->deadline-now>OHC_LEASE_MAX_MS) { return false; }
        s->armed=true; s->generation=f->generation; s->deadline=f->deadline; s->heartbeat=now;
    } else {
        if(f->generation!=s->generation || f->deadline!=s->deadline || ohc_lease_overdue(s,now)) { return false; }
        switch(f->op) {
        case OHC_L_TAKEOVER:
            if(s->working||s->completed) { return false; }
            s->working=true; break;
        case OHC_L_BEAT: s->heartbeat=now; break;
        case OHC_L_COMPLETE:
            if(!s->working||s->completed||f->flags>7||(f->status!=0&&f->status!=1)) { return false; }
            s->completed=true; s->safe=f->flags==7; break;
        case OHC_L_RESTORE:
            if(!s->completed||!s->safe) { return false; }
            /* This is permission to ASK the independent adapter, not proof. */
            break;
        case OHC_L_DELEGATE: s->delegated=true; break;
        default: return false;
        }
    }
    s->sequence=f->sequence; return true;
}
bool ohc_lease_production_available(void) { return false; }
