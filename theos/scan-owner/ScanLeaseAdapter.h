#import <Foundation/Foundation.h>
#include "../fe35-control-bridge.h"
NS_ASSUME_NONNULL_BEGIN
/* Internal Trial arm/takeover/restore seam. No UI path or guard-truth input.
 * All methods are asynchronous, ordered by the caller's owner executor. */
@protocol OHCScanLeaseAdapter <NSObject>
@property(nonatomic, readonly) NSString *privateRunDirectory;
- (void)arm:(uint64_t)generation deadline:(int64_t)deadline result:(void (^)(BOOL))result;
- (void)takeover:(uint64_t)generation result:(void (^)(BOOL))result;
- (void)heartbeat:(uint64_t)generation;
- (void)stopHeartbeat:(uint64_t)generation;
- (void)requestRestore:(uint64_t)generation result:(void (^)(BOOL))result;
- (void)delegateOnce:(uint64_t)generation;
@optional
/* Trusted in-process API return, recorded before the core can request restore.
 * CLEANED never calls this. It is NOT independent recovery verification. */
- (void)workerCompletion:(fe35_scan_completion)completion generation:(uint64_t)generation executionExited:(BOOL)exited;
@property(nonatomic, copy, nullable) void (^unavailable)(uint64_t generation);
@end
NS_ASSUME_NONNULL_END
