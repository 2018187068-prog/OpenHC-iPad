#import <Foundation/Foundation.h>
NS_ASSUME_NONNULL_BEGIN
/* Foreground-only client to an already connected dedicated owner endpoint.
 * No root/guard/identity API. A fresh instance/connection per Start; no reconnect
 * or authority inference. Not connected by the installed synthetic demo. */
@interface OHCScanOwnerForeground : NSObject
- (instancetype)init NS_UNAVAILABLE;
- (instancetype)initWithConnectedDescriptor:(int)fd NS_DESIGNATED_INITIALIZER;
@property(nonatomic, copy, nullable) void (^publication)(NSString *kind, uint64_t generation,
                                                       NSString * _Nullable qr, NSString * _Nullable pin);
- (void)start;
- (void)stop;
- (void)background;
@end
NS_ASSUME_NONNULL_END
