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
        } else if (argc == 2 && strcmp(argv[1], "--auth") == 0) {
            NSString *result = [bridge authSelfCheck];
            puts([result UTF8String]);
            return [result isEqualToString:@"AUTH_VECTORS_OK"] ? 0 : 1;
        } else if (argc == 2 && strcmp(argv[1], "--version") == 0) {
            puts("OPENHC_STAGE0_VERSION=0.3.0");
        } else {
            fputs("usage: openhc-bridge-check [--wifi|--auth|--version]\n", stderr);
            return 2;
        }
    }
    return 0;
}
