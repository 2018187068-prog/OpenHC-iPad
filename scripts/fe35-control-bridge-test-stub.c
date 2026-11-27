#include "../theos/fe35-control-bridge.h"
#include "../theos/Fe35BridgeBounds.h"
#include <stdio.h>
#include <assert.h>
#include <string.h>

typedef struct {
    fe35_bridge_event events[2];
    size_t count;
} test_batch;

static test_batch batch;
static int fail_feed;

static fe35_bridge_batch set_event(const char *kind, const uint8_t *frame, size_t frame_size,
                                   const uint8_t *uuid, size_t uuid_size, int channel) {
    memset(&batch, 0, sizeof(batch));
    batch.count = 1;
    fe35_bridge_event *event = &batch.events[0];
    strncpy(event->kind, kind, sizeof(event->kind) - 1);
    event->channel = channel;
    if (frame_size > sizeof(event->frame) || uuid_size > sizeof(event->uuid)) return NULL;
    if (frame_size) memcpy(event->frame, frame, frame_size);
    event->frame_size = frame_size;
    if (uuid_size) memcpy(event->uuid, uuid, uuid_size);
    event->uuid_size = uuid_size;
    return &batch;
}

fe35_bridge_handle fe35_bridge_create(const fe35_bridge_input *input) {
    size_t checked = 99;
    assert(!fe35_bridge_checked_length(-1, 16, &checked));
    assert(checked == 99);
    assert(fe35_bridge_checked_length(0, 16, &checked) && checked == 0);
    assert(fe35_bridge_checked_length(16, 16, &checked) && checked == 16);
    assert(!fe35_bridge_checked_length(17, 16, &checked));
    assert(!fe35_bridge_checked_length(0, 16, NULL));
    static const char expected[] = "synthetic-device";
    if (!input || (strcmp(input->device_id, expected) != 0 &&
        strcmp(input->device_id, "synthetic-exception") != 0) || input->root_key_size != 16 ||
        input->const_a_size != 16 || input->const_b_size != 16) return NULL;
    fail_feed = strcmp(input->device_id, "synthetic-exception") == 0;
    return &fail_feed;
}

fe35_bridge_batch fe35_bridge_start(fe35_bridge_handle bridge, int64_t now_ms) {
    static const uint8_t frame[] = {0x7f, 0x80, 0x80, 0x80};
    (void)bridge; (void)now_ms;
    return set_event("SEND_FRAME", frame, sizeof(frame), NULL, 0, 0);
}

fe35_bridge_batch fe35_bridge_feed(fe35_bridge_handle bridge, const uint8_t *data, size_t size) {
    static const uint8_t uuid[16] = {0, 0, 0xfe, 0x36, 0, 0, 0x10, 0, 0x80, 0, 0, 0x80, 0x5f, 0x9b, 0x34, 0xfb};
    (void)bridge;
    if (!data || !size) return NULL;
    if (fail_feed || data[0] != 0x7f) return set_event("ERROR_SESSION_CLOSED", NULL, 0, NULL, 0, 0);
    return set_event("OPEN_AUTH_LISTENER", NULL, 0, uuid, sizeof(uuid), 0);
}

fe35_bridge_batch fe35_bridge_listener_ready(fe35_bridge_handle bridge, int channel) {
    static const uint8_t frame[] = {0x7f, 0x80, 0x80, 0x81, 0x04};
    (void)bridge;
    return set_event("SEND_FRAME", frame, sizeof(frame), NULL, 0, channel);
}

fe35_bridge_batch fe35_bridge_tick(fe35_bridge_handle bridge, int64_t now_ms) {
    (void)bridge; (void)now_ms;
    memset(&batch, 0, sizeof(batch));
    return &batch;
}

size_t fe35_bridge_event_count(fe35_bridge_batch value) {
    return value ? ((test_batch *)value)->count : 0;
}

int fe35_bridge_copy_event(fe35_bridge_batch value, size_t index, fe35_bridge_event *out) {
    test_batch *source = value;
    if (!source || !out || index >= source->count) return -1;
    *out = source->events[index];
    return 0;
}

void fe35_bridge_release_batch(fe35_bridge_batch value) { (void)value; }
void fe35_bridge_close(fe35_bridge_handle bridge) {
    (void)bridge;
    puts("BTSTACK_TEST_BRIDGE_CLOSE_CALLED");
}
