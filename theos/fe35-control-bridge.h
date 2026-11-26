#ifndef OPENHC_FE35_CONTROL_BRIDGE_H
#define OPENHC_FE35_CONTROL_BRIDGE_H

#include <stddef.h>
#include <stdint.h>

#define FE35_BRIDGE_MAX_FRAME 65552
#define FE35_BRIDGE_MAX_EVENTS 32

typedef struct {
    char device_id[129];
    uint8_t root_key[64];
    uint8_t const_a[64];
    uint8_t const_b[64];
    size_t root_key_size;
    size_t const_a_size;
    size_t const_b_size;
} fe35_bridge_input;

typedef struct {
    char kind[48];
    int32_t channel;
    uint8_t uuid[16];
    size_t uuid_size;
    uint8_t frame[FE35_BRIDGE_MAX_FRAME];
    size_t frame_size;
} fe35_bridge_event;

typedef void *fe35_bridge_handle;
typedef void *fe35_bridge_batch;

fe35_bridge_handle fe35_bridge_create(const fe35_bridge_input *input);
fe35_bridge_batch fe35_bridge_start(fe35_bridge_handle bridge, int64_t now_ms);
fe35_bridge_batch fe35_bridge_feed(fe35_bridge_handle bridge, const uint8_t *data, size_t size);
fe35_bridge_batch fe35_bridge_listener_ready(fe35_bridge_handle bridge, int channel);
fe35_bridge_batch fe35_bridge_tick(fe35_bridge_handle bridge, int64_t now_ms);
size_t fe35_bridge_event_count(fe35_bridge_batch batch);
int fe35_bridge_copy_event(fe35_bridge_batch batch, size_t index, fe35_bridge_event *event);
void fe35_bridge_release_batch(fe35_bridge_batch batch);
void fe35_bridge_close(fe35_bridge_handle bridge);

#endif
