/* Synthetic only. Compiled into the existing simulator CLI fixture, never the DEB. */
#import <Foundation/Foundation.h>
#import <OpenHCBridge/OpenHCBridge.h>
#include "../theos/fe35-control-bridge.h"
#include <pthread.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

typedef struct {
    fe35_scan_binding binding;
    FILE *trace;
    const char *scenario;
    int stop_pipe[2];
    pthread_t timer;
    int timer_started;
    char stop_marker[512];
    int rfcomm;
    int sdp;
    int ready;
    int clear;
    int close;
    int cleaned;
    int invalid;
    int64_t generation;
} fixture;

static int64_t monotonic_ms(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return (int64_t)t.tv_sec * 1000 + t.tv_nsec / 1000000;
}

static void *request_stop(void *context) {
    fixture *f = context;
    if (f->stop_marker[0]) {
        /* Stop only after the host fixture has observed the RFCOMM command.
         * This keeps simulator scheduling latency out of the cancellation race. */
        struct timespec delay = {0, 10000000};
        unsigned attempts = 0;
        while (access(f->stop_marker, F_OK) != 0 && attempts++ < 800)
            nanosleep(&delay, NULL);
        if (access(f->stop_marker, F_OK) != 0) return NULL;
    } else {
        struct timespec delay = {0, 60000000};
        nanosleep(&delay, NULL);
    }
    (void)write(f->stop_pipe[1], "S", 1);
    return NULL;
}

static void start_timer(fixture *f) {
    if (!f->timer_started) {
        f->timer_started = 1;
        if (pthread_create(&f->timer, NULL, request_stop, f)) f->invalid = 1;
    }
}

static void sink(void *context, void *value) {
    fixture *f = context;
    NSArray<OHCBScanReceiverEvent *> *events = (__bridge NSArray *)value;
    for (OHCBScanReceiverEvent *event in events) {
        if (event.generation != f->generation) f->invalid = 1;
        fprintf(f->trace, "EVENT=%s\n", event.kind.UTF8String);
        if ([event.kind isEqualToString:@"PAIRING_READY"]) {
            f->ready++;
            if (!f->rfcomm || !f->sdp || !event.qrCode || event.pinCode.length != 6) f->invalid = 1;
            if (!strcmp(f->scenario, "ready_stop")) start_timer(f);
        }
        if ([event.kind isEqualToString:@"CLEAR_PAIRING"]) f->clear++;
        if ([event.kind isEqualToString:@"CLOSE_CONTROL_TRANSPORT"]) {
            f->close++;
            if (f->clear != 1) f->invalid = 1;
        }
    }
    fflush(f->trace);
}

static int notify(void *context, int64_t generation, const char *kind, int channel, int64_t now) {
    fixture *f = context;
    if (strcmp(kind, "TICK")) fprintf(f->trace, "CALLBACK=%s\n", kind);
    if (generation != f->generation) f->invalid = 1;
    if (!strcmp(kind, "RFCOMM_READY")) {
        f->rfcomm++;
        if (!strcmp(f->scenario, "stop_sdp_wait")) start_timer(f);
    }
    if (!strcmp(kind, "SDP_READY")) f->sdp++;
    if (!strcmp(kind, "CLEANED")) {
        f->cleaned++;
        if (f->clear != 1 || f->close != 1) f->invalid = 1;
    }
    int result = fe35_scan_notify(&f->binding, generation, kind, channel, now);
    /* Duplicate/foreign callbacks travel through the actual ObjC/common bridge.
     * Neither may publish another pairing event or terminate the current session. */
    if (!strcmp(kind, "SDP_READY") && !result) {
        if (fe35_scan_notify(&f->binding, generation, kind, channel, now)) f->invalid = 1;
        if (fe35_scan_notify(&f->binding, generation - 1, "FAILED", 0, now) != 1) f->invalid = 1;
    }
    fflush(f->trace);
    return result;
}

int openhc_scan_transport_fixture(const char *run_dir, const char *scenario) {
    fixture f = {0};
    f.scenario = scenario;
    f.stop_pipe[0] = f.stop_pipe[1] = -1;
    NSString *trace = [NSString stringWithFormat:@"%s/scan-events", run_dir];
    f.trace = fopen(trace.fileSystemRepresentation, "w");
    if (!f.trace || pipe(f.stop_pipe)) return 91;
    OHCBHostIdentity *host = [[OHCBHostIdentity alloc] initWithModelId:@"A1B2C3"
        subModelId:@"D4" brand:@"Synthetic" deviceName:@"Synthetic"];
    int64_t lifetime = 2000;
    OHCBScanReceiverConfig *config = [[OHCBScanReceiverConfig alloc] initWithHost:host
        bluetoothAddress:@"A0:B1:C2:D3:E4:F5" supportsUsb:NO lifetimeMillis:lifetime];
    OHCBScanReceiverSession *session = [[OHCBScanReceiverSession alloc] initWithConfig:config];
    NSArray *start = [session startNowMillis:monotonic_ms()];
    f.generation = session.generation;
    f.binding = (fe35_scan_binding){(__bridge void *)session, &f, sink};
    sink(&f, (__bridge void *)start);
    fe35_bridge_input input = {0};
    strcpy(input.device_id, "synthetic-device");
    input.root_key_size = input.const_a_size = input.const_b_size = 16;
    fe35_bridge_handle bridge = fe35_bridge_create(&input);
    if (!bridge) return 92;
    if (!strcmp(scenario, "stop_rfcomm_wait")) {
        if (snprintf(f.stop_marker, sizeof(f.stop_marker), "%s/stop", run_dir) >=
            (int)sizeof(f.stop_marker)) return 94;
        start_timer(&f);
    }
    fe35_scan_transport transport = {&f, f.generation, f.stop_pipe[0], notify};
    int result = openhc_btstack_scan_inbound(run_dir, bridge, &transport);
    if (f.timer_started) pthread_join(f.timer, NULL);
    /* Terminal callbacks and a previous generation remain inert after cleanup. */
    for (int i = 0; i < 2; ++i) {
        (void)fe35_scan_notify(&f.binding, f.generation, "RFCOMM_READY", 16, monotonic_ms());
        (void)fe35_scan_notify(&f.binding, f.generation, "SDP_READY", 0, monotonic_ms());
        (void)fe35_scan_notify(&f.binding, f.generation, "STOP", 0, monotonic_ms());
        (void)fe35_scan_notify(&f.binding, f.generation, "CLEANED", 0, monotonic_ms());
    }
    int expect_ready = !strcmp(scenario, "ready_stop") || !strcmp(scenario, "ready_timeout") ||
        !strcmp(scenario, "cleanup_failure");
    fprintf(f.trace, "COUNTS=%d,%d,%d,%d\n", f.ready, f.clear, f.close, f.cleaned);
    if (f.ready != expect_ready || f.clear != 1 || f.close != 1 || f.cleaned != 1 || result != 1)
        f.invalid = 1;
    (void)[session startNowMillis:monotonic_ms()];
    (void)fe35_scan_notify(&f.binding, f.generation, "RFCOMM_READY", 16, monotonic_ms());
    (void)fe35_scan_notify(&f.binding, f.generation, "SDP_READY", 0, monotonic_ms());
    (void)fe35_scan_notify(&f.binding, f.generation, "FAILED", 0, monotonic_ms());
    if (![session.state isEqualToString:@"STARTING"] || f.ready != expect_ready || f.close != 1)
        f.invalid = 1;
    (void)[session stopGeneration:session.generation];
    fclose(f.trace);
    close(f.stop_pipe[0]);
    close(f.stop_pipe[1]);
    return f.invalid ? 93 : 0;
}
