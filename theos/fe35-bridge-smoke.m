#import <Foundation/Foundation.h>
#import <OpenHCBridge/OpenHCBridge.h>

static KotlinByteArray *zeroBytes(int32_t length) {
    return [[KotlinByteArray alloc] initWithSize:length init:^int8_t(int32_t index) {
        return 0;
    }];
}

int openhc_fe35_bridge_smoke(void) {
    @autoreleasepool {
        KotlinByteArray *key = zeroBytes(16);
        OHCBFe35ControlBridge *bridge = [[OHCBFe35ControlBridge alloc]
            initWithDeviceIdText:@"synthetic-device"
            rootKey:key constA:key constB:key];
        if (!bridge) return 1;
        NSArray<OHCBFe35ControlBridgeEvent *> *started = [bridge startNowMillis:0];
        if (started.count != 1 || ![started.firstObject.kind isEqualToString:@"SEND_FRAME"]) {
            [bridge close];
            return 2;
        }
        [bridge close];
        return 0;
    }
}
