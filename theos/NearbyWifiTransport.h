#import <Foundation/Foundation.h>
#import <OpenHCBridge/OpenHCBridge.h>
#include "fe35-control-bridge.h"
NS_ASSUME_NONNULL_BEGIN
/* Trusted injected network lifetime. No production implementation/loader is supplied.
 * poll is nonblocking and returns nil until ready. After phone confirmation only, openListener
 * supplies a bound/listening IPv4 TCP socket matching config.carIp; it keeps ownership.
 * close must be idempotent and report actual cleanup certainty, not merely that it was called. */
@protocol OHCNearbyNetwork <NSObject>
- (nullable OHCBWifiNetworkConfig *)poll;
- (int)openListener;
/* Explicit transport association supplied by the trusted network owner. No deviceId/PONG
 * inference. A proxy fixture's actual loopback source differs from the advertised synthetic
 * phone address; a real provider must establish the supported target association separately. */
- (NSString *)acceptedPeerIPv4;
- (BOOL)close;
@end
/* Borrowed TCP/key boundary on owner executor. No ownership/lease escapes. Return YES only if
 * the boundary was consumed synchronously. The C worker closes TCP at the end of this slice.
 * Encrypted ReceiverSession and durable live TCP handoff remain a subsequent dependency. */
typedef BOOL (^OHCWifiBoundary)(uint64_t, int64_t, int64_t, int, const uint8_t key[_Nonnull 16]);
@interface OHCNearbyWifiTransport : NSObject
- (instancetype)initWithNetwork:(id<OHCNearbyNetwork>)network
    accept:(BOOL (^)(OHCNearbyWifiTransport *,int,int64_t))accept;
- (BOOL)handoffGeneration:(int64_t)generation deadline:(int64_t)deadline;
- (BOOL)storeKey:(const uint8_t [_Nonnull 16])key;
- (BOOL)deliverTo:(OHCWifiBoundary)sink owner:(uint64_t)owner descriptor:(int)fd;
- (fe35_wifi_transport)binding;
- (void)revoke;
- (BOOL)cancel;
@end
NS_ASSUME_NONNULL_END
