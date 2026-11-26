#import <Foundation/Foundation.h>
#import <OpenHCBridge/OpenHCBridge.h>
#include <stdlib.h>
#include <string.h>
int openhc_platform_probe(void);
int openhc_btstack_probe(void);
int openhc_btstack_services_probe(void);
int openhc_btstack_control_synthetic(const char *address, unsigned channel,
                                     const char *profile, const char *run_dir);
int openhc_btstack_control_inbound(const char *run_dir);
int openhc_btstack_ownership_probe(void);
int openhc_session_owner_probe(void);
int openhc_fe35_bridge_smoke(void);

int openhc_cli_main(int argc, const char *argv[]) {
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
        } else if (argc == 2 && strcmp(argv[1], "--session-owner") == 0) {
            return openhc_session_owner_probe();
        } else if (argc == 2 && strcmp(argv[1], "--fe35-bridge-smoke") == 0) {
            return openhc_fe35_bridge_smoke();
        } else if (argc == 6 && strcmp(argv[1], "--btstack-control-synthetic") == 0) {
            char *end = NULL;
            unsigned long channel = strtoul(argv[3], &end, 10);
            if (!end || *end || channel < 1 || channel > 30) return 2;
            return openhc_btstack_control_synthetic(argv[2], (unsigned)channel, argv[4], argv[5]);
        } else if (argc == 3 && strcmp(argv[1], "--btstack-control-inbound") == 0) {
            return openhc_btstack_control_inbound(argv[2]);
        } else if (argc == 2 && strcmp(argv[1], "--version") == 0) {
            puts("OPENHC_STAGE0_VERSION=0.3.5");
        } else {
            fputs("usage: openhc-bridge-check [--wifi|--auth|--platform|--btstack|--btstack-services|--btstack-ownership|--session-owner|--fe35-bridge-smoke|--btstack-control-synthetic ADDRESS CHANNEL auto|strict|reference RUN_DIR|--btstack-control-inbound RUN_DIR <binary bridge config on stdin>|--version]\n", stderr);
            return 2;
        }
    }
    return 0;
}

#ifndef OPENHC_CLI_NO_MAIN
int main(int argc, const char *argv[]) {
    return openhc_cli_main(argc, argv);
}
#endif
