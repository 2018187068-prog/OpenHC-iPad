#import "OHCAppleVideoSink.h"
#import <VideoToolbox/VideoToolbox.h>
#include <arpa/inet.h>
#include <string.h>
#include "OHCAnnexB.h"

@interface OHCAppleVideoSink () {
    NSRecursiveLock *_lock;
    int _maximumWidth,_maximumHeight;
    NSData *_sps,*_pps;
    CMVideoFormatDescriptionRef _format;
    VTDecompressionSessionRef _decoder;
    CVImageBufferRef _decodedImage;
    BOOL _awaitingIDR,_callbackSeen;
    OSStatus _callbackStatus;
    CMTime _callbackPts;
}
- (void)decoded:(CVImageBufferRef _Nullable)image status:(OSStatus)status pts:(CMTime)pts;
@end
static void decompressed(void *context,void *source,OSStatus status,VTDecodeInfoFlags flags,
                        CVImageBufferRef image,CMTime pts,CMTime duration) {
    (void)source;(void)flags;(void)duration;
    [(__bridge OHCAppleVideoSink *)context decoded:image status:status pts:pts];
}
@implementation OHCAppleVideoSink
/* Deployment minimum is iOS15. Legacy display-layer rendering methods remain
 * the compatible path there; isolate their deprecation warnings to wrappers. */
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wdeprecated-declarations"
- (id<AVQueuedSampleBufferRendering>)renderer {
    if(@available(iOS 17.0,*))return _displayLayer.sampleBufferRenderer;
    return _displayLayer;
}
- (BOOL)displayFailed {
    if(@available(iOS 17.0,*))return _displayLayer.sampleBufferRenderer.status==AVQueuedSampleBufferRenderingStatusFailed;
    return _displayLayer.status==AVQueuedSampleBufferRenderingStatusFailed;
}
- (void)flushDisplay {[_displayLayer flushAndRemoveImage];}
#pragma clang diagnostic pop
- (instancetype)initWithLayer:(AVSampleBufferDisplayLayer *)layer maximumWidth:(int)width maximumHeight:(int)height {
    if(!layer || width<=0 || height<=0 || width>4096 || height>4096)return nil;
    if((self=[super init])) {
        _displayLayer=layer;_maximumWidth=width;_maximumHeight=height;
        _lock=[NSRecursiveLock new];_awaitingIDR=YES;
    }
    return self;
}
- (void)resetDecoder {
    if(_decoder) {VTDecompressionSessionInvalidate(_decoder);CFRelease(_decoder);_decoder=NULL;}
    if(_format) {CFRelease(_format);_format=NULL;}
    if(_decodedImage) {CVPixelBufferRelease(_decodedImage);_decodedImage=NULL;}
    _awaitingIDR=YES;
}
- (BOOL)makeDecoder {
    if(!_sps || !_pps)return NO;
    const uint8_t *sets[2]={_sps.bytes,_pps.bytes};size_t sizes[2]={_sps.length,_pps.length};
    if(CMVideoFormatDescriptionCreateFromH264ParameterSets(kCFAllocatorDefault,2,sets,sizes,4,&_format)!=noErr)return NO;
    CMVideoDimensions dimensions=CMVideoFormatDescriptionGetDimensions(_format);
    if(dimensions.width<=0 || dimensions.height<=0 || dimensions.width>_maximumWidth || dimensions.height>_maximumHeight)return NO;
    NSDictionary *attributes=@{(id)kCVPixelBufferPixelFormatTypeKey:@(kCVPixelFormatType_32BGRA),
        (id)kCVPixelBufferIOSurfacePropertiesKey:@{}};
    VTDecompressionOutputCallbackRecord callback={decompressed,(__bridge void *)self};
    return VTDecompressionSessionCreate(kCFAllocatorDefault,_format,NULL,
        (__bridge CFDictionaryRef)attributes,&callback,&_decoder)==noErr;
}
/* No asynchronous-decompression flag is enabled. The callback only retains the
 * actual image; display enqueue happens after DecodeFrame returns. No callback
 * acquires the caller/owner lock or creates a detached source of authority. */
- (void)decoded:(CVImageBufferRef)image status:(OSStatus)status pts:(CMTime)pts {
    _callbackSeen=YES;_callbackStatus=status;_callbackPts=pts;
    if(image && status==noErr && !_decodedImage)_decodedImage=CVPixelBufferRetain(image);
}
- (BOOL)consume:(NSData *)data pts:(int64_t)pts discontinuity:(BOOL)gap {
    if(_closed || _failed || !data.length || data.length>OHC_VIDEO_MAX_AU || pts<0)return NO;
    ohc_h264_nal ranges[OHC_VIDEO_MAX_NALS];size_t count=0;
    if(!ohc_h264_nals(data.bytes,data.length,ranges,&count))return NO;
    const uint8_t *b=data.bytes;BOOL idr=NO,slice=NO,changed=NO;
    NSMutableData *avcc=[NSMutableData data];
    @try {
    for(size_t at=0;at<count;at++) {
        NSRange range=NSMakeRange(ranges[at].offset,ranges[at].length);int type=b[range.location]&31;
        if(type==7 || type==8) {
            if(range.length>65535)return NO;
            NSData *set=[data subdataWithRange:range];
            if(type==7 && ![_sps isEqualToData:set]) {_sps=set;changed=YES;}
            if(type==8 && ![_pps isEqualToData:set]) {_pps=set;changed=YES;}
        } else {
            uint32_t size=htonl((uint32_t)range.length);
            [avcc appendBytes:&size length:sizeof(size)];[avcc appendBytes:b+range.location length:range.length];
            if(type==5)idr=YES;if(type>=1 && type<=5)slice=YES;
        }
    }
    if(changed || gap) {[self resetDecoder];[self flushDisplay];}
    if(!slice || !_sps || !_pps || (_awaitingIDR && !idr)) {_droppedFrames++;return YES;}
    if(!_decoder && ![self makeDecoder])return NO;
    _awaitingIDR=NO;
    CMBlockBufferRef block=NULL;CMSampleBufferRef sample=NULL;BOOL ok=NO;
    @try {
    do {
        OSStatus status=CMBlockBufferCreateWithMemoryBlock(kCFAllocatorDefault,NULL,avcc.length,kCFAllocatorDefault,NULL,0,avcc.length,0,&block);
        if(status!=noErr || CMBlockBufferReplaceDataBytes(avcc.bytes,block,0,avcc.length)!=noErr)break;
        CMSampleTimingInfo timing={kCMTimeInvalid,CMTimeMake(pts,90000),kCMTimeInvalid};size_t size=avcc.length;
        if(CMSampleBufferCreateReady(kCFAllocatorDefault,block,_format,1,1,&timing,1,&size,&sample)!=noErr)break;
        CFArrayRef decodeAttachments=CMSampleBufferGetSampleAttachmentsArray(sample,true);
        if(!decodeAttachments || !CFArrayGetCount(decodeAttachments))break;
        CFMutableDictionaryRef decodeInfo=(CFMutableDictionaryRef)CFArrayGetValueAtIndex(decodeAttachments,0);
        CFDictionarySetValue(decodeInfo,kCMSampleAttachmentKey_NotSync,idr?kCFBooleanFalse:kCFBooleanTrue);
        CFDictionarySetValue(decodeInfo,kCMSampleAttachmentKey_DependsOnOthers,idr?kCFBooleanFalse:kCFBooleanTrue);
        _callbackSeen=NO;_callbackStatus=noErr;_callbackPts=kCMTimeInvalid;VTDecodeInfoFlags flags=0;
        status=VTDecompressionSessionDecodeFrame(_decoder,sample,0,NULL,&flags);
        if(status!=noErr || _callbackStatus!=noErr)break;
        if(!_decodedImage) {
            if(_callbackSeen || (flags&kVTDecodeInfo_FrameDropped)) {_droppedFrames++;ok=YES;}
            break;
        }
        if(!CMTIME_IS_NUMERIC(_callbackPts) || CMTimeCompare(_callbackPts,timing.presentationTimeStamp)!=0)break;
        _lastWidth=(int)CVPixelBufferGetWidth(_decodedImage);_lastHeight=(int)CVPixelBufferGetHeight(_decodedImage);
        if(_lastWidth<=0 || _lastHeight<=0 || _lastWidth>_maximumWidth || _lastHeight>_maximumHeight)break;
        _decodedFrames++;_lastPts90k=CMTimeConvertScale(_callbackPts,90000,kCMTimeRoundingMethod_Default).value;
        id<AVQueuedSampleBufferRendering> renderer=[self renderer];
        if([self displayFailed])break;
        if(!renderer.readyForMoreMediaData) {_droppedFrames++;ok=YES;break;}
        CMVideoFormatDescriptionRef imageFormat=NULL;CMSampleBufferRef imageSample=NULL;
        status=CMVideoFormatDescriptionCreateForImageBuffer(kCFAllocatorDefault,_decodedImage,&imageFormat);
        if(status==noErr)status=CMSampleBufferCreateReadyWithImageBuffer(kCFAllocatorDefault,_decodedImage,imageFormat,&timing,&imageSample);
        if(imageFormat)CFRelease(imageFormat);
        if(status!=noErr) {if(imageSample)CFRelease(imageSample);break;}
        CFArrayRef attachments=CMSampleBufferGetSampleAttachmentsArray(imageSample,true);
        if(!attachments || !CFArrayGetCount(attachments)) {CFRelease(imageSample);break;}
        CFDictionarySetValue((CFMutableDictionaryRef)CFArrayGetValueAtIndex(attachments,0),kCMSampleAttachmentKey_DisplayImmediately,kCFBooleanTrue);
        @try {[renderer enqueueSampleBuffer:imageSample];}
        @finally {CFRelease(imageSample);}
        if([self displayFailed])break;
        _enqueuedFrames++;ok=YES;
    } while(0);
    return ok;
    } @finally {
        if(sample)CFRelease(sample);
        if(block) {CMBlockBufferFillDataBytes(0,block,0,CMBlockBufferGetDataLength(block));CFRelease(block);}
        if(_decodedImage) {CVPixelBufferRelease(_decodedImage);_decodedImage=NULL;}
    }
    } @finally {if(avcc.length)memset(avcc.mutableBytes,0,avcc.length);}
}
- (BOOL)acceptUnit:(OHCBAccessUnit *)unit {
    [_lock lock];
    @try {
        if(_closed || _failed)return NO;
        if(!unit || unit.length<=0 || unit.length>OHC_VIDEO_MAX_AU || unit.offset<0 ||
            unit.offset>unit.data.size || unit.length>unit.data.size-unit.offset) {
            _failed=YES;[self resetDecoder];[self flushDisplay];return NO;
        }
        NSMutableData *data=[NSMutableData dataWithLength:(NSUInteger)unit.length];uint8_t *bytes=data.mutableBytes;
        for(int32_t i=0;i<unit.length;i++)bytes[i]=(uint8_t)[unit.data getIndex:unit.offset+i];
        BOOL ok=NO;
        @try {ok=[self consume:data pts:unit.pts90k discontinuity:unit.gapBefore!=nil];}
        @finally {memset(bytes,0,data.length);}
        if(!ok) {_failed=YES;[self resetDecoder];[self flushDisplay];}
        return ok;
    } @catch(__unused NSException *e) {_failed=YES;[self resetDecoder];return NO;}
    @finally {[_lock unlock];}
}
- (void)close {
    [_lock lock];
    @try {if(_closed)return;_closed=YES;[self resetDecoder];_sps=nil;_pps=nil;[self flushDisplay];}
    @finally {[_lock unlock];}
}
- (void)dealloc {if(_decoder){VTDecompressionSessionInvalidate(_decoder);CFRelease(_decoder);}if(_format)CFRelease(_format);if(_decodedImage)CVPixelBufferRelease(_decodedImage);}
@end
