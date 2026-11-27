#import "ScanLeaseAdapter.h"
NS_ASSUME_NONNULL_BEGIN
/* No production constructor can consume a client-supplied fd/path. This factory
 * stays nil until root-controlled launcher + target Trial effects are verified.
 * Not linked into or enabled in the installed synthetic demo. */
@interface OHCScanProcessLeaseAdapter : NSObject <OHCScanLeaseAdapter>
+ (nullable instancetype)productionAdapter;
- (instancetype)init NS_UNAVAILABLE;
#ifdef OPENHC_SCAN_OWNER_PROCESS_TEST
/* Host test broker owns the other end and independent guard. Simulator's
 * loopback relay is explicitly synthetic trust, NOT a deployment capability. */
- (nullable instancetype)initWithTestDescriptor:(int)fd runDirectory:(NSString *)directory;
- (void)testFlush:(void (^)(void))completion;
#endif
@property(nonatomic, readonly) NSString *privateRunDirectory;
@property(nonatomic, copy, nullable) void (^unavailable)(uint64_t generation);
@end
NS_ASSUME_NONNULL_END
