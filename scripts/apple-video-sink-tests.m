#import "../theos/OHCAppleVideoSink.h"
#import <VideoToolbox/VideoToolbox.h>
#import <CommonCrypto/CommonCryptor.h>
#include <arpa/inet.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../theos/OHCAnnexB.h"

static unsigned checks;
static void videoCheck(BOOL condition) {checks++;if(!condition){fprintf(stderr,"HISIGHT_APPLE_VIDEO_FAILED=%u\n",checks);exit(2);}}
typedef struct { CMSampleBufferRef sample;OSStatus status; } Capture;
static void compressed(void *context,void *source,OSStatus status,VTEncodeInfoFlags flags,CMSampleBufferRef sample) {
    (void)source;(void)flags;Capture *c=context;c->status=status;
    if(status==noErr && sample && !c->sample)c->sample=(CMSampleBufferRef)CFRetain(sample);
}
/* Real system encoder fixture. No precomputed/fake decoder outputs. */
static NSData *encodedAnnexB(void) {
    Capture capture={0};VTCompressionSessionRef encoder=NULL;CVPixelBufferRef image=NULL;
    videoCheck(VTCompressionSessionCreate(kCFAllocatorDefault,32,32,kCMVideoCodecType_H264,NULL,NULL,NULL,compressed,&capture,&encoder)==noErr);
    videoCheck(VTSessionSetProperty(encoder,kVTCompressionPropertyKey_RealTime,kCFBooleanTrue)==noErr);
    videoCheck(VTSessionSetProperty(encoder,kVTCompressionPropertyKey_AllowFrameReordering,kCFBooleanFalse)==noErr);
    videoCheck(VTSessionSetProperty(encoder,kVTCompressionPropertyKey_ProfileLevel,kVTProfileLevel_H264_Baseline_AutoLevel)==noErr);
    NSDictionary *attributes=@{(id)kCVPixelBufferIOSurfacePropertiesKey:@{}};
    videoCheck(CVPixelBufferCreate(kCFAllocatorDefault,32,32,kCVPixelFormatType_32BGRA,(__bridge CFDictionaryRef)attributes,&image)==kCVReturnSuccess);
    videoCheck(CVPixelBufferLockBaseAddress(image,0)==kCVReturnSuccess);
    uint8_t *pixels=CVPixelBufferGetBaseAddress(image);size_t row=CVPixelBufferGetBytesPerRow(image);
    for(int y=0;y<32;y++)for(int x=0;x<32;x++){uint8_t *p=pixels+y*row+x*4;p[0]=24;p[1]=96;p[2]=192;p[3]=255;}
    videoCheck(CVPixelBufferUnlockBaseAddress(image,0)==kCVReturnSuccess);
    VTEncodeInfoFlags flags=0;
    NSDictionary *options=@{(id)kVTEncodeFrameOptionKey_ForceKeyFrame:@YES};
    videoCheck(VTCompressionSessionEncodeFrame(encoder,image,CMTimeMake(0,30),CMTimeMake(1,30),(__bridge CFDictionaryRef)options,NULL,&flags)==noErr);
    videoCheck(VTCompressionSessionCompleteFrames(encoder,kCMTimeInvalid)==noErr);
    videoCheck(capture.status==noErr && capture.sample!=NULL);
    NSMutableData *out=[NSMutableData data];const uint8_t prefix[4]={0,0,0,1};
    CMFormatDescriptionRef format=CMSampleBufferGetFormatDescription(capture.sample);
    for(size_t i=0;i<2;i++) {
        const uint8_t *set=NULL;size_t length=0,count=0;int header=0;
        videoCheck(CMVideoFormatDescriptionGetH264ParameterSetAtIndex(format,i,&set,&length,&count,&header)==noErr && count>=2 && header==4);
        [out appendBytes:prefix length:4];[out appendBytes:set length:length];
    }
    CMBlockBufferRef block=CMSampleBufferGetDataBuffer(capture.sample);size_t size=CMBlockBufferGetDataLength(block);
    NSMutableData *avcc=[NSMutableData dataWithLength:size];videoCheck(CMBlockBufferCopyDataBytes(block,0,size,avcc.mutableBytes)==noErr);
    const uint8_t *bytes=avcc.bytes;size_t at=0;
    while(at<size) {
        videoCheck(size-at>=4);uint32_t length=0;memcpy(&length,bytes+at,4);length=ntohl(length);at+=4;
        videoCheck(length>0 && length<=size-at);[out appendBytes:prefix length:4];[out appendBytes:bytes+at length:length];at+=length;
    }
    CFRelease(capture.sample);VTCompressionSessionInvalidate(encoder);CFRelease(encoder);CVPixelBufferRelease(image);
    return out;
}
static OHCBKotlinByteArray *kbytes(NSData *data) {
    OHCBKotlinByteArray *out=[[OHCBKotlinByteArray alloc] initWithSize:(int32_t)data.length];const uint8_t *p=data.bytes;
    for(int32_t i=0;i<out.size;i++)[out setIndex:i value:(int8_t)p[i]];return out;
}
static OHCBHiSightVideoStream *stream(OHCAppleVideoSink *sink) {
    OHCBKotlinByteArray *key=[[OHCBKotlinByteArray alloc] initWithSize:16];for(int32_t i=0;i<16;i++)[key setIndex:i value:(int8_t)i];
    OHCBHiSightVideoStream *out=[[OHCBHiSightVideoStream alloc] initWithSessionKey:key consumer:sink];
    for(int32_t i=0;i<16;i++)[key setIndex:i value:0];return out;
}
/* Independent system CTR peer encoder; production uses ECB + explicit BE128 carry. */
static NSData *packet(NSData *annex,uint16_t seq) {
    uint8_t key[16],iv[16];for(int i=0;i<16;i++){key[i]=(uint8_t)i;iv[i]=(uint8_t)(0x90+i);}
    CCCryptorRef cipher=NULL;videoCheck(CCCryptorCreateWithMode(kCCEncrypt,kCCModeCTR,kCCAlgorithmAES,ccNoPadding,iv,key,16,NULL,0,0,kCCModeOptionCTR_BE,&cipher)==kCCSuccess);
    NSMutableData *sealed=[NSMutableData dataWithLength:annex.length];size_t moved=0;
    videoCheck(CCCryptorUpdate(cipher,annex.bytes,annex.length,sealed.mutableBytes,sealed.length,&moved)==kCCSuccess && moved==annex.length);CCCryptorRelease(cipher);memset(key,0,16);
    const uint8_t pes[14]={0,0,1,0xe0,0,0,0x84,0x80,5,0x21,0,5,0xbf,0x21};
    uint8_t rtp[12]={0x80,0xe0,(uint8_t)(seq>>8),(uint8_t)seq,0,1,0x5f,0x90,1,2,3,4};
    uint32_t length=htonl((uint32_t)(sizeof(rtp)+sizeof(pes)+16+sealed.length));
    NSMutableData *out=[NSMutableData dataWithBytes:&length length:4];[out appendBytes:rtp length:sizeof(rtp)];
    [out appendBytes:pes length:sizeof(pes)];[out appendBytes:iv length:16];[out appendData:sealed];return out;
}
void OHCCheckAppleVideoSink(CALayer *parent) {
    videoCheck(NSThread.isMainThread);
    NSData *annex=encodedAnnexB();AVSampleBufferDisplayLayer *layer=[AVSampleBufferDisplayLayer new];layer.frame=CGRectMake(0,0,32,32);[parent addSublayer:layer];
    OHCAppleVideoSink *sink=[[OHCAppleVideoSink alloc] initWithLayer:layer maximumWidth:64 maximumHeight:64];videoCheck(sink!=nil);
    OHCBHiSightVideoStream *video=stream(sink);NSData *wire=packet(annex,64999);
    const uint8_t *bytes=wire.bytes;
    for(NSUInteger i=0;i<wire.length;i++)videoCheck([video feedData:kbytes([NSData dataWithBytes:bytes+i length:1])]);
    videoCheck(video.deliveredFrames==1 && sink.decodedFrames==1 && sink.enqueuedFrames==1 && !sink.failed);
    videoCheck(sink.lastWidth==32 && sink.lastHeight==32 && sink.lastPts90k==90000);
    /* Simulated packet loss requires a new IDR, not fake decoder success. */
    NSMutableData *nonIdr=[annex mutableCopy];ohc_h264_nal nals[OHC_VIDEO_MAX_NALS];size_t count=0;BOOL changed=NO;
    videoCheck(ohc_h264_nals(nonIdr.bytes,nonIdr.length,nals,&count));uint8_t *mutable=nonIdr.mutableBytes;
    for(size_t i=0;i<count;i++)if((mutable[nals[i].offset]&31)==5){mutable[nals[i].offset]=(mutable[nals[i].offset]&0xe0)|1;changed=YES;}
    videoCheck(changed);
    videoCheck([video feedData:kbytes(packet(nonIdr,3))] && sink.decodedFrames==1 && sink.droppedFrames==1);
    videoCheck([video feedData:kbytes(packet(annex,4))] && sink.decodedFrames==2 && !sink.failed && video.deliveredFrames==3);
    videoCheck([video finish] && video.isClosed);[sink close];[sink close];
    videoCheck(sink.closed && ![video feedData:kbytes(wire)] && sink.decodedFrames==2);[layer removeFromSuperlayer];
    /* Actual format dimensions must fit the explicit sink capability. */
    OHCAppleVideoSink *small=[[OHCAppleVideoSink alloc] initWithLayer:[AVSampleBufferDisplayLayer new] maximumWidth:16 maximumHeight:16];
    OHCBHiSightVideoStream *smallVideo=stream(small);videoCheck(![smallVideo feedData:kbytes(wire)] && small.failed && smallVideo.hasFailed && smallVideo.isClosed && small.enqueuedFrames==0);[small close];
    /* Malformed Annex-B reaches the actual native sink and fails permanently. */
    OHCAppleVideoSink *bad=[[OHCAppleVideoSink alloc] initWithLayer:[AVSampleBufferDisplayLayer new] maximumWidth:64 maximumHeight:64];
    OHCBHiSightVideoStream *badVideo=stream(bad);uint8_t invalid[3]={1,2,3};
    videoCheck(![badVideo feedData:kbytes(packet([NSData dataWithBytes:invalid length:3],1))] && bad.failed && badVideo.hasFailed && bad.decodedFrames==0);[bad close];
    /* Close before data cannot allocate/decode a frame. */
    OHCAppleVideoSink *cancelled=[[OHCAppleVideoSink alloc] initWithLayer:[AVSampleBufferDisplayLayer new] maximumWidth:64 maximumHeight:64];
    OHCBHiSightVideoStream *cancelVideo=stream(cancelled);[cancelVideo close];[cancelled close];
    videoCheck(![cancelVideo feedData:kbytes(wire)] && cancelled.decodedFrames==0);
    printf("HISIGHT_APPLE_VIDEO_ASSERTIONS_OK=%u\n",checks);
    puts("HISIGHT_APPLE_ACTUAL_DECODE_ENQUEUE_OK=1");fflush(stdout);
}
