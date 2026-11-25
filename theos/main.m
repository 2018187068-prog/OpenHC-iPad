#import <Foundation/Foundation.h>
#import <OpenHCBridge/OpenHCBridge.h>
#include <string.h>
int openhc_platform_probe(void);
int openhc_btstack_probe(void);
int openhc_btstack_services_probe(void);
int openhc_btstack_ownership_probe(void);

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
        } else if (argc == 2 && strcmp(argv[1], "--platform") == 0) {
            return openhc_platform_probe();
        } else if (argc == 2 && strcmp(argv[1], "--btstack") == 0) {
            return openhc_btstack_probe();
        } else if (argc == 2 && strcmp(argv[1], "--btstack-services") == 0) {
            return openhc_btstack_services_probe();
        } else if (argc == 2 && strcmp(argv[1], "--btstack-ownership") == 0) {
            return openhc_btstack_ownership_probe();
        } else if (argc == 2 && strcmp(argv[1], "--version") == 0) {
            puts("OPENHC_STAGE0_VERSION=0.3.2");
        } else {
            fputs("usage: openhc-bridge-check [--wifi|--auth|--platform|--btstack|--btstack-services|--btstack-ownership|--version]\n", stderr);
            return 2;
        }
    }
    return 0;
}
