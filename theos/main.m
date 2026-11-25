#import <Foundation/Foundation.h>
#import <OpenHCBridge/OpenHCBridge.h>

int main(void) {
    @autoreleasepool {
        OHCBBridgeSelfCheck *bridge = [[OHCBBridgeSelfCheck alloc] init];
        puts([[bridge selfCheck] UTF8String]);
    }
    return 0;
}
