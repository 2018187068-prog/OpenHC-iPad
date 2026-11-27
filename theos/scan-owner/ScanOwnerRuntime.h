#import <Foundation/Foundation.h>
#import <OpenHCBridge/OpenHCBridge.h>
#include "ScanOwner.h"
NS_ASSUME_NONNULL_BEGIN
/* Trusted internal asynchronous adapter for the EXISTING Trial/guard contract.
 * No native device implementation is supplied or enabled. An implementation
 * must own the exclusive lock, immutable absolute guard deadline, sole heartbeat
 * and independent recovery actor. It must not block the owner executor or accept
 * UI paths/truth. All result blocks may run on any queue; deadlines fence them.
 * The offline fixture implements only these effects synthetically. */
@protocol OHCScanLeaseAdapter <NSObject>
@property(nonatomic, readonly) NSString *privateRunDirectory;
- (void)arm:(uint64_t)generation deadline:(int64_t)deadline result:(void (^)(BOOL))result;
- (void)takeover:(uint64_t)generation result:(void (^)(BOOL))result;
- (void)heartbeat:(uint64_t)generation;
- (void)stopHeartbeat:(uint64_t)generation;
- (void)requestRestore:(uint64_t)generation result:(void (^)(BOOL))result;
- (void)delegateOnce:(uint64_t)generation;
@end

/* Not installed, launched or wired to the demo/PING helper. One instance per
 * root owner process, not per caller. Internal root actor supplies config/lease;
 * endpoint carries only START/STOP/BACKGROUND. Production always denies START. */
@interface OHCScanOwnerRuntime : NSObject
- (instancetype)init NS_UNAVAILABLE;
- (instancetype)initWithConfig:(OHCBScanReceiverConfig *)config
                    bridgeInput:(const fe35_bridge_input *)input
                          lease:(id<OHCScanLeaseAdapter>)lease NS_DESIGNATED_INITIALIZER;
/* Ownership of accepted fd transfers here. Nonblocking read, fresh kernel and
 * endpoint sampling each tick, fixed bounded grammar. No claimed identity. */
- (void)acceptConnectedDescriptor:(int)fd;
/* Trusted recovery actor only; never exposed through endpoint grammar. */
- (void)observeVerifiedRecovery:(BOOL)verified generation:(uint64_t)generation;
/* Trusted internal scan/auth sink, serial off-main. Common generation belongs
 * to its retained session; the endpoint separately maps to the captured owner
 * fence. Never log QR/PIN. AUTH_HANDOFF is NOT completed authentication. */
@property(nonatomic, copy, nullable) void (^events)(NSArray<OHCBScanReceiverEvent *> *);
@property(nonatomic, copy, nullable) void (^clearPairing)(uint64_t generation);
@property(nonatomic, copy, nullable) void (^finished)(fe35_scan_completion, BOOL delegated);
/* Foreground client must close its connection on teardown. No force shutdown of
 * a running worker; self/binding/session retained through synchronous return. */
#ifdef OPENHC_SCAN_OWNER_TEST
- (void)acceptTestDescriptor:(int)fd evidence:(ohc_owner_peer)evidence;
@property(nonatomic, readonly) int testHandoffCount;
@property(nonatomic, copy) void (^testNativeCallback)(NSString *kind);
#endif
@end
NS_ASSUME_NONNULL_END
