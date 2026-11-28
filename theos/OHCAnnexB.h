#ifndef OHC_ANNEX_B_H
#define OHC_ANNEX_B_H
#include <stddef.h>
#include <stdint.h>
enum { OHC_VIDEO_MAX_AU=10*1024*1024, OHC_VIDEO_MAX_NALS=256 };
typedef struct {size_t offset,length;} ohc_h264_nal;
static inline size_t ohc_h264_start(const uint8_t *b,size_t n,size_t p) {
    if(p<=n && n-p>=3 && !b[p] && !b[p+1]) {
        if(b[p+2]==1)return 3;
        if(n-p>=4 && !b[p+2] && b[p+3]==1)return 4;
    }
    return 0;
}
/* Strict bounded Annex-B only. Complete framing validation before any decoder
 * state is changed. Output count remains zero on every failure. */
static inline int ohc_h264_nals(const uint8_t *b,size_t n,ohc_h264_nal *out,size_t *count) {
    if(count)*count=0;
    if(!b || !out || !count || !n || n>OHC_VIDEO_MAX_AU)return 0;
    size_t at=0,total=0;
    while(at<n) {
        size_t code=ohc_h264_start(b,n,at);if(!code)return 0;
        size_t begin=at+code,end=begin;
        while(end<n && !ohc_h264_start(b,n,end))end++;
        size_t next=end;while(end>begin && !b[end-1])end--;
        if(end==begin || (b[begin]&0x80) || !(b[begin]&31) || (b[begin]&31)>23 || total>=OHC_VIDEO_MAX_NALS)return 0;
        out[total++]=(ohc_h264_nal){begin,end-begin};at=next;
    }
    *count=total;return total!=0;
}
#endif
