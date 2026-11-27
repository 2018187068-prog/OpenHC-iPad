#import <Foundation/Foundation.h>
#import <OpenHCBridge/OpenHCBridge.h>
#import <CoreFoundation/CoreFoundation.h>
#include "fe35-control-bridge.h"
#include "Fe35BridgeBounds.h"
#include <string.h>
#import "Fe36AuthTransport.h"

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
        if (!fe35_bridge_checked_length(uuid.size, sizeof(out->uuid), &out->uuid_size)) return -1;
        for (int32_t i = 0; i < uuid.size; ++i) out->uuid[i] = (uint8_t)[uuid getIndex:i];
    }
    OHCBKotlinByteArray *frame = source.frame;
    if (frame) {
        if (!fe35_bridge_checked_length(frame.size, sizeof(out->frame), &out->frame_size)) return -1;
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

@interface OHCFe36AuthTransport () {
    NSLock *_lock;
    OHCBFe36AuthSessionBridge *_auth;
    int64_t _generation;
    BOOL _handed, _cancelled, _candidate, _delivered;
    BOOL (^_commit)(OHCFe36AuthTransport *, int64_t, int64_t);
}
- (int)step:(enum fe36_io_event)event incarnation:(int64_t)incarnation
    bytes:(const uint8_t *)bytes size:(size_t)size now:(int64_t)now
    send:(fe36_io_send)send context:(void *)context;
@end
static int authStep(void *p, enum fe36_io_event event, int64_t incarnation,
                    const uint8_t *bytes, size_t size, int64_t now, fe36_io_send send, void *context) {
    return [(__bridge OHCFe36AuthTransport *)p step:event incarnation:incarnation
        bytes:bytes size:size now:now send:send context:context];
}
static int authCommit(void *p,int64_t incarnation,int64_t now) {
    OHCFe36AuthTransport *a=(__bridge OHCFe36AuthTransport *)p;
    return [a commitIncarnation:incarnation now:now] ? 0 : -1;
}
static void authCancel(void *p) { [(__bridge OHCFe36AuthTransport *)p cancel]; }
@implementation OHCFe36AuthTransport
- (instancetype)initWithConfig:(OHCBFe36AuthConfig *)config trust:(id<OHCBTrustStore>)trust
    commit:(BOOL (^)(OHCFe36AuthTransport *,int64_t,int64_t))commit {
    if(!config || !trust || !commit) return nil;
    if((self=[super init])) {
        _lock=[NSLock new]; _commit=[commit copy];
        _auth=[[OHCBFe36AuthSessionBridge alloc] initWithConfig:config trust:trust];
        if(!_auth) return nil;
    } return self;
}
- (BOOL)handoff:(OHCBScanReceiverEvent *)event now:(int64_t)now deadline:(int64_t)deadline {
    [_lock lock];
    @try {
        if(_handed || _cancelled) return NO;
        _handed=YES; _generation=event.generation;
        NSArray *actions=[_auth handoffEvent:event nowMillis:now deadlineMillis:deadline];
        return actions.count==1 && [((OHCBFe36AuthAction *)actions[0]).kind isEqualToString:@"OPEN_AUTH_CONNECTION"];
    } @catch(__unused NSException *e) { _cancelled=YES; return NO; }
    @finally { [_lock unlock]; }
}
- (fe36_auth_transport)binding { return (fe36_auth_transport){(__bridge void *)self,authStep,authCommit,authCancel}; }
- (BOOL)commitIncarnation:(int64_t)incarnation now:(int64_t)now { return _commit && _commit(self,incarnation,now); }
- (int)step:(enum fe36_io_event)event incarnation:(int64_t)incarnation
    bytes:(const uint8_t *)bytes size:(size_t)size now:(int64_t)now
    send:(fe36_io_send)send context:(void *)context {
    @autoreleasepool {
        NSArray<OHCBFe36AuthAction *> *actions=nil;
        [_lock lock];
        @try {
            if(!_handed || _cancelled || _candidate || !send) return -1;
            if(event==FE36_IO_CONNECTED) actions=[_auth connectedGeneration:_generation connection:incarnation nowMillis:now];
            else if(event==FE36_IO_TICK) actions=[_auth tickGeneration:_generation nowMillis:now];
            else if(event==FE36_IO_DATA && bytes && size && size<=4096) {
                OHCBKotlinByteArray *copy=kotlinBytes(bytes,size);
                @try { actions=[_auth receiveGeneration:_generation connection:incarnation bytes:copy nowMillis:now]; }
                @finally { wipeKotlinBytes(copy); }
            } else return -1;
        } @catch(__unused NSException *e) { return -1; }
        @finally { [_lock unlock]; }
        if(actions.count>32) { [self cancel]; return -1; }
        BOOL verified=NO;
        for(OHCBFe36AuthAction *action in actions) {
            if([action.kind isEqualToString:@"SEND"]) {
                OHCBKotlinByteArray *data=action.bytes;
                if(!data || data.size<=0 || data.size>65536) { wipeKotlinBytes(data); [self cancel]; return -1; }
                uint8_t copy[4096]; int failed=0;
                for(int32_t at=0;at<data.size && !failed;) {
                    size_t part=MIN(sizeof(copy),(size_t)(data.size-at));
                    for(size_t j=0;j<part;j++) copy[j]=(uint8_t)[data getIndex:at+(int32_t)j];
                    failed=send(context,copy,part); memset(copy,0,sizeof(copy)); at+=(int32_t)part;
                }
                wipeKotlinBytes(data);
                if(failed) { [self cancel]; return -1; }
            } else if([action.kind isEqualToString:@"AUTHENTICATED"]) verified=YES;
            else { [self cancel]; return -1; }
        }
        [_lock lock];
        int result=_cancelled ? -1 : (verified ? 1 : 0);
        if(result==1) _candidate=YES;
        [_lock unlock]; return result;
    }
}
- (BOOL)deliver:(int64_t)incarnation now:(int64_t)now sink:(OHCFe36KeySink)sink {
    uint8_t key[16]={0}; BOOL valid=NO;
    [_lock lock];
    @try {
        if(!_candidate || _cancelled || _delivered || !sink) return NO;
        OHCBKotlinByteArray *data=[_auth takeSessionKeyGeneration:_generation connection:incarnation nowMillis:now];
        if(data.size==16) { for(int32_t i=0;i<16;i++) key[i]=(uint8_t)[data getIndex:i]; valid=YES; _delivered=YES; }
        wipeKotlinBytes(data);
    } @catch(__unused NSException *e) { valid=NO; }
    @finally { [_lock unlock]; }
    @try { if(valid) sink(_generation,incarnation,key); }
    @finally { memset(key,0,sizeof(key)); }
    return valid;
}
- (void)cancel {
    [_lock lock];
    @try { if(!_cancelled) { _cancelled=YES; [_auth stopGeneration:_generation]; } }
    @finally { [_lock unlock]; }
}
@end
