#include "../theos/scan-owner/ScanLeaseProtocol.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static unsigned checks;
#define CHECK(x) do { ++checks; if(!(x)) { fprintf(stderr,"LEASE_ASSERT=%s line=%d\n",#x,__LINE__); exit(1); } } while(0)
int main(void) {
    CHECK(!ohc_lease_production_available());
    ohc_lease_frame f={OHC_L_ARM,1,1,240100,0,0}, decoded;
    uint8_t wire[OHC_LEASE_FRAME_SIZE]; ohc_lease_encode(wire,&f);
    CHECK(ohc_lease_decode(&decoded,wire)); CHECK(decoded.op==f.op&&decoded.deadline==f.deadline);
    for(int i=0;i<8;++i) {
        if(i==5) { continue; }
        uint8_t bad[OHC_LEASE_FRAME_SIZE]; memcpy(bad,wire,sizeof(bad)); bad[i]^=0xff;
        CHECK(!ohc_lease_decode(&decoded,bad));
    }
    for(int op=0;op<256;++op) {
        ohc_lease_guard s={0}; f=(ohc_lease_frame){(uint8_t)op,1,1,240100,0,0};
        CHECK(ohc_lease_step(&s,&f,100)==(op==OHC_L_ARM));
    }
    f=(ohc_lease_frame){OHC_L_ARM,1,1,240100,0,0}; ohc_lease_guard s={0};
    CHECK(!ohc_lease_step(&s,&f,99)); CHECK(ohc_lease_step(&s,&f,100));
    CHECK(!ohc_lease_step(&s,&f,100)); /* one-shot, no replay */
    f.op=OHC_L_TAKEOVER; f.sequence=2;
    for(int i=0;i<3;++i) {
        ohc_lease_frame bad=f;
        if(i==0) { bad.generation++; }
        if(i==1) { bad.deadline++; }
        if(i==2) { bad.sequence++; }
        CHECK(!ohc_lease_step(&s,&bad,101));
    }
    CHECK(ohc_lease_step(&s,&f,101));
    for(int status=-1;status<=2;status+=3) {
        ohc_lease_guard invalid=s;
        ohc_lease_frame bad={OHC_L_COMPLETE,1,3,240100,7,status};
        CHECK(!ohc_lease_step(&invalid,&bad,102));
    }
    f.op=OHC_L_RESTORE; f.sequence=3; CHECK(!ohc_lease_step(&s,&f,102));
    for(unsigned flags=0;flags<=8;++flags) {
        ohc_lease_guard variant=s;
        f=(ohc_lease_frame){OHC_L_COMPLETE,1,3,240100,flags,1};
        CHECK(ohc_lease_step(&variant,&f,102)==(flags<=7));
        if(flags<=7) {
            CHECK(variant.safe==(flags==7));
            f.op=OHC_L_RESTORE; f.sequence++; f.flags=0; f.status=0;
            CHECK(ohc_lease_step(&variant,&f,103)==(flags==7));
        }
    }
    f=(ohc_lease_frame){OHC_L_BEAT,1,3,240100,0,0};
    CHECK(ohc_lease_step(&s,&f,2100)); CHECK(s.deadline==240100&&s.heartbeat==2100);
    CHECK(!ohc_lease_overdue(&s,8099)); CHECK(ohc_lease_overdue(&s,8100));
    f.sequence++; CHECK(!ohc_lease_step(&s,&f,8100));
    f=(ohc_lease_frame){OHC_L_DELEGATE,1,4,240100,0,0};
    CHECK(ohc_lease_step(&s,&f,2200)); f.sequence++; CHECK(!ohc_lease_step(&s,&f,2201));
    printf("SCAN_LEASE_PROTOCOL_ASSERTIONS=%u\n",checks);
    return 0;
}
