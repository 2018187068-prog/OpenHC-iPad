#import <Foundation/Foundation.h>
#import <OpenHCBridge/OpenHCBridge.h>
#import <CoreFoundation/CoreFoundation.h>
#include "fe35-control-bridge.h"
#include <string.h>

static OHCBKotlinByteArray *kotlinBytes(const uint8_t *bytes, size_t size) {
    if (size > INT32_MAX) return nil;
    OHCBKotlinByteArray *result = [OHCBKotlinByteArray arrayWithSize:(int32_t)size];
    for (size_t i = 0; i < size; ++i) {
        [result setIndex:(int32_t)i value:(int8_t)bytes[i]];
    }
    return result;
}

static void wipeKotlinBytes(OHCBKotlinByteArray *bytes) {
    for (int32_t i = 0; i < bytes.size; ++i) [bytes setIndex:i value:0];
}

static fe35_bridge_batch retainEvents(NSArray<OHCBFe35ControlBridgeEvent *> *events) {
    if (events.count > FE35_BRIDGE_MAX_EVENTS) return NULL;
    return (fe35_bridge_batch)CFBridgingRetain(events);
}

fe35_bridge_handle fe35_bridge_create(const fe35_bridge_input *input) {
    if (!input || !memchr(input->device_id, 0, sizeof(input->device_id)) ||
        input->root_key_size == 0 || input->root_key_size > sizeof(input->root_key) ||
        input->const_a_size == 0 || input->const_a_size > sizeof(input->const_a) ||
        input->const_b_size == 0 || input->const_b_size > sizeof(input->const_b)) return NULL;
    @autoreleasepool {
        OHCBKotlinByteArray *root = nil;
        OHCBKotlinByteArray *a = nil;
        OHCBKotlinByteArray *b = nil;
        @try {
            NSString *device = [NSString stringWithUTF8String:input->device_id];
            if (!device) return NULL;
            root = kotlinBytes(input->root_key, input->root_key_size);
            a = kotlinBytes(input->const_a, input->const_a_size);
            b = kotlinBytes(input->const_b, input->const_b_size);
            if (!root || !a || !b) return NULL;
            OHCBFe35ControlBridge *bridge = [[OHCBFe35ControlBridge alloc]
                initWithDeviceIdText:device rootKey:root constA:a constB:b];
            return bridge ? (fe35_bridge_handle)CFBridgingRetain(bridge) : NULL;
        } @catch (__unused NSException *exception) {
            return NULL;
        } @finally {
            // Every copied key buffer is cleared before the autorelease pool drains.
            // The bridge has already copied them into its cipher.
            // Locals remain nil if allocation failed before initialization.
            wipeKotlinBytes(root);
            wipeKotlinBytes(a);
            wipeKotlinBytes(b);
        }
    }
}

fe35_bridge_batch fe35_bridge_start(fe35_bridge_handle handle, int64_t now_ms) {
    @autoreleasepool {
        @try { return retainEvents([(__bridge OHCBFe35ControlBridge *)handle startNowMillis:now_ms]); }
        @catch (__unused NSException *exception) { return NULL; }
    }
}

fe35_bridge_batch fe35_bridge_feed(fe35_bridge_handle handle, const uint8_t *data, size_t size) {
    if (!handle || (!data && size) || size > 65536) return NULL;
    @autoreleasepool {
        @try {
            OHCBKotlinByteArray *bytes = kotlinBytes(data, size);
            return bytes ? retainEvents([(__bridge OHCBFe35ControlBridge *)handle feedData:bytes]) : NULL;
        } @catch (__unused NSException *exception) { return NULL; }
    }
}

fe35_bridge_batch fe35_bridge_listener_ready(fe35_bridge_handle handle, int channel) {
    @autoreleasepool {
        @try { return retainEvents([(__bridge OHCBFe35ControlBridge *)handle listenerReadyChannel:channel]); }
        @catch (__unused NSException *exception) { return NULL; }
    }
}

fe35_bridge_batch fe35_bridge_tick(fe35_bridge_handle handle, int64_t now_ms) {
    @autoreleasepool {
        @try { return retainEvents([(__bridge OHCBFe35ControlBridge *)handle tickNowMillis:now_ms]); }
        @catch (__unused NSException *exception) { return NULL; }
    }
}

size_t fe35_bridge_event_count(fe35_bridge_batch batch) {
    return batch ? ((__bridge NSArray *)batch).count : 0;
}

int fe35_bridge_copy_event(fe35_bridge_batch batch, size_t index, fe35_bridge_event *out) {
    if (!batch || !out) return -1;
    NSArray<OHCBFe35ControlBridgeEvent *> *events = (__bridge NSArray *)batch;
    if (index >= events.count) return -1;
    OHCBFe35ControlBridgeEvent *source = events[index];
    memset(out, 0, sizeof(*out));
    const char *kind = source.kind.UTF8String;
    if (!kind || strlen(kind) >= sizeof(out->kind)) return -1;
    strcpy(out->kind, kind);
    out->channel = source.channel;
    OHCBKotlinByteArray *uuid = source.serviceUuid;
    if (uuid) {
        if (uuid.size > sizeof(out->uuid)) return -1;
        out->uuid_size = (size_t)uuid.size;
        for (int32_t i = 0; i < uuid.size; ++i) out->uuid[i] = (uint8_t)[uuid getIndex:i];
    }
    OHCBKotlinByteArray *frame = source.frame;
    if (frame) {
        if ((size_t)frame.size > sizeof(out->frame)) return -1;
        out->frame_size = (size_t)frame.size;
        for (int32_t i = 0; i < frame.size; ++i) out->frame[i] = (uint8_t)[frame getIndex:i];
    }
    return 0;
}

void fe35_bridge_release_batch(fe35_bridge_batch batch) {
    if (batch) CFBridgingRelease(batch);
}

void fe35_bridge_close(fe35_bridge_handle handle) {
    if (!handle) return;
    @autoreleasepool {
        OHCBFe35ControlBridge *bridge = CFBridgingRelease(handle);
        @try { [bridge close]; }
        @catch (__unused NSException *exception) { }
    }
}

int fe35_scan_notify(void *context, int64_t generation, const char *kind,
                     int channel, int64_t now_ms) {
    fe35_scan_binding *binding = context;
    if (!binding || !binding->session || !binding->sink || !kind) return -1;
    @autoreleasepool {
        @try {
            OHCBScanReceiverSession *session = (__bridge OHCBScanReceiverSession *)binding->session;
            if (session.generation != generation) return 1;
            NSArray<OHCBScanReceiverEvent *> *events = [session
                onTransportEventGeneration:generation kind:[NSString stringWithUTF8String:kind]
                channel:channel nowMillis:now_ms];
            int close = 0;
            for (OHCBScanReceiverEvent *event in events) {
                if ([event.kind isEqualToString:@"CLOSE_CONTROL_TRANSPORT"]) close = 1;
            }
            binding->sink(binding->sink_context, (__bridge void *)events);
            return close || [session.state isEqualToString:@"STOPPED"] ||
                [session.state isEqualToString:@"FAILED"];
        } @catch (__unused NSException *exception) { return -1; }
    }
}
