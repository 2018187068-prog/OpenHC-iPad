#import <Foundation/Foundation.h>
#import <OpenHCBridge/OpenHCBridge.h>
#include <string.h>

int main(int argc, const char *argv[]) {
    @autoreleasepool {
        OHCBBridgeSelfCheck *bridge = [[OHCBBridgeSelfCheck alloc] init];
        if (argc == 1) {
            puts([[bridge selfCheck] UTF8String]);
        } else if (argc == 2 && strcmp(argv[1], "--wifi") == 0) {
            NSString *result = [bridge wifiConnectionInfoSelfCheck];
            puts([result UTF8String]);
            return [result isEqualToString:@"WIFI_CONNECTION_INFO_OK"] ? 0 : 1;
        } else {
            fputs("usage: openhc-bridge-check [--wifi]\n", stderr);
            return 2;
        }
    }
    return 0;
}
