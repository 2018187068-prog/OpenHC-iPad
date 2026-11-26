#import <Foundation/Foundation.h>

@interface OHCScanHelperClient : NSObject
+ (void)pingWithTimeout:(NSTimeInterval)timeout
             completion:(void (^)(NSString *reply))completion;
@end
