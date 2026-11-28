#include "../theos/OHCAnnexB.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
int main(void) {
    ohc_h264_nal ranges[OHC_VIDEO_MAX_NALS];size_t count=99;
    const uint8_t mixed[]={0,0,0,1,0x67,0x42,0,0,1,0x68,0xce,0,0,0,1,0x65,0x80,0,0};
    assert(ohc_h264_nals(mixed,sizeof(mixed),ranges,&count) && count==3);
    assert(ranges[0].offset==4 && ranges[0].length==2 && ranges[1].offset==9 && ranges[1].length==2 && ranges[2].offset==15 && ranges[2].length==2);
    const uint8_t emulation[]={0,0,1,0x65,0,0,3,1,0x80};
    assert(ohc_h264_nals(emulation,sizeof(emulation),ranges,&count) && count==1 && ranges[0].length==6);
    const uint8_t bad[][6]={{0,0,1,0,0,0},{0,0,1,0x80,0,0},{0,0,1,0x78,0,0},{1,0,0,1,0x65,0x80}};
    for(size_t i=0;i<sizeof(bad)/sizeof(bad[0]);i++){count=99;assert(!ohc_h264_nals(bad[i],6,ranges,&count) && count==0);}
    for(size_t n=0;n<5;n++){count=99;assert(!ohc_h264_nals(mixed,n,ranges,&count) && count==0);}
    const uint8_t trailing[]={0,0,1,0x65,0x80,0,0,1};
    assert(!ohc_h264_nals(trailing,sizeof(trailing),ranges,&count) && count==0);
    uint8_t many[(OHC_VIDEO_MAX_NALS+1)*5];
    for(size_t i=0;i<sizeof(many);i+=5)memcpy(many+i,"\0\0\1\x65\x80",5);
    assert(ohc_h264_nals(many,sizeof(many)-5,ranges,&count) && count==OHC_VIDEO_MAX_NALS);
    assert(!ohc_h264_nals(many,sizeof(many),ranges,&count) && count==0);
    assert(!ohc_h264_nals(NULL,1,ranges,&count) && count==0);
    assert(!ohc_h264_nals(mixed,sizeof(mixed),NULL,&count) && count==0);
    assert(!ohc_h264_nals(mixed,sizeof(mixed),ranges,NULL));
    assert(!ohc_h264_nals(mixed,(size_t)OHC_VIDEO_MAX_AU+1,ranges,&count) && count==0);
    puts("HISIGHT_PRODUCTION_ANNEXB_CASES_OK=8");return 0;
}
