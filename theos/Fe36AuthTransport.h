#import <Foundation/Foundation.h>
#import <OpenHCBridge/OpenHCBridge.h>
#include "fe35-control-bridge.h"
NS_ASSUME_NONNULL_BEGIN
@class OHCFe36AuthTransport;
/* Internal borrowed key, valid for callback duration only. No diagnostic/event
 * representation. This is not a radio/network grant or a transferred lease.
 * A future next stage must copy privately and own cancellation/lease transfer;
 * the current bounded scan worker still tears down and returns to its guard. */
typedef void (^OHCFe36KeySink)(int64_t generation, int64_t incarnation, const uint8_t key[16]);
@interface OHCFe36AuthTransport : NSObject
- (instancetype)init NS_UNAVAILABLE;
- (instancetype)initWithConfig:(OHCBFe36AuthConfig *)config trust:(id<OHCBTrustStore>)trust
    commit:(BOOL (^)(OHCFe36AuthTransport *, int64_t, int64_t))commit;
- (BOOL)handoff:(OHCBScanReceiverEvent *)event now:(int64_t)now deadline:(int64_t)deadline;
- (fe36_auth_transport)binding;
- (BOOL)commitIncarnation:(int64_t)incarnation now:(int64_t)now;
/* Called on trusted owner's serial executor, after its final active fence. */
- (BOOL)deliver:(int64_t)incarnation now:(int64_t)now sink:(OHCFe36KeySink)sink;
- (void)cancel;
@end
NS_ASSUME_NONNULL_END
