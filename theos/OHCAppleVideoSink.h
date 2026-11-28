#import <AVFoundation/AVFoundation.h>
#import <OpenHCBridge/OpenHCBridge.h>
NS_ASSUME_NONNULL_BEGIN
/* Real H.264 Annex-B -> VideoToolbox -> CVPixelBuffer -> display layer sink.
 * Caller supplies an actual attached layer and explicit decoder size limits.
 * No sockets, admission, identity, service advertisement, audio or media clock.
 * Receiver owner must serialize callbacks and close with its original lease.
 * A true accept means consumed (possibly dropped), NOT that pixels were shown. */
@interface OHCAppleVideoSink : NSObject <OHCBHiSightVideoConsumer>
- (nullable instancetype)initWithLayer:(AVSampleBufferDisplayLayer *)layer
    maximumWidth:(int)width maximumHeight:(int)height NS_DESIGNATED_INITIALIZER;
- (instancetype)init NS_UNAVAILABLE;
@property(nonatomic, strong, readonly) AVSampleBufferDisplayLayer *displayLayer;
@property(nonatomic, readonly) BOOL failed;
@property(nonatomic, readonly) BOOL closed;
@property(nonatomic, readonly) uint64_t decodedFrames;
@property(nonatomic, readonly) uint64_t enqueuedFrames;
@property(nonatomic, readonly) uint64_t droppedFrames;
@property(nonatomic, readonly) int lastWidth;
@property(nonatomic, readonly) int lastHeight;
@property(nonatomic, readonly) int64_t lastPts90k;
- (BOOL)acceptUnit:(OHCBAccessUnit *)unit;
- (void)close;
@end
NS_ASSUME_NONNULL_END
