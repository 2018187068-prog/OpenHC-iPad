#import <Foundation/Foundation.h>
#import <OpenHCBridge/OpenHCBridge.h>
#include "ScanOwner.h"
#import "ScanLeaseAdapter.h"
#import "../Fe36AuthTransport.h"
#import "../NearbyWifiTransport.h"
NS_ASSUME_NONNULL_BEGIN
typedef void (^OHCScanOwnerKeySink)(uint64_t ownerGeneration, int64_t commonGeneration,
                                    int64_t incarnation, const uint8_t key[_Nonnull 16]);
/* Trusted internal asynchronous adapter for the EXISTING Trial/guard contract.
 * No native device implementation is supplied or enabled. An implementation
 * must own the exclusive lock, immutable absolute guard deadline, sole heartbeat
 * and independent recovery actor. It must not block the owner executor or accept
 * UI paths/truth. All result blocks may run on any queue; deadlines fence them.
 * ScanProcessLeaseAdapter executes private-channel I/O; only its compile-time
 * fixture bootstrap is available. Deployment effects/launch remain disabled. */

/* Not installed, launched or wired to the demo/PING helper. One instance per
 * root owner process, not per caller. Internal root actor supplies config/lease;
 * endpoint carries only START/STOP/BACKGROUND. Production always denies START. */
@interface OHCScanOwnerRuntime : NSObject
- (instancetype)init NS_UNAVAILABLE;
- (instancetype)initWithConfig:(OHCBScanReceiverConfig *)config
                    bridgeInput:(const fe35_bridge_input *)input
                          lease:(id<OHCScanLeaseAdapter>)lease NS_DESIGNATED_INITIALIZER;
/* Trusted in-memory opt-in, before START, once per runtime. No endpoint/file/
 * environment loader. Nil/partial configuration rejects. Default initializer
 * retains explicit FE35-only behavior; no fabricated authentication success.
 * sink is synchronous on owner executor and must not reenter the runtime. */
- (BOOL)configureAuthentication:(OHCBFe36AuthConfig *)config trust:(id<OHCBTrustStore>)trust
    keySink:(OHCScanOwnerKeySink)sink;
/* Alternative opt-in, once before START. Retains original control/owner/lease until an owned
 * TCP boundary, then cleans up. No deployed provider and no encrypted TCP/media implementation.
 * boundary is borrowed synchronous inspection, NOT a transferred live-session lease. */
- (BOOL)configureContinuingAuthentication:(OHCBFe36AuthConfig *)config trust:(id<OHCBTrustStore>)trust
    network:(id<OHCNearbyNetwork>)network boundary:(OHCWifiBoundary)boundary;
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
