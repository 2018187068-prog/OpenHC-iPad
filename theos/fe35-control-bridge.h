#ifndef OPENHC_FE35_CONTROL_BRIDGE_H
#define OPENHC_FE35_CONTROL_BRIDGE_H

#include <stddef.h>
#include <stdint.h>
#include <stdbool.h>

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

/* A serialized, borrowed ScanReceiverSession binding. The owner starts the common
 * session first, supplies that generation, and keeps context alive until return.
 * notify delivers common events to the owner's in-memory sink; return 1 when a
 * CLOSE_CONTROL_TRANSPORT action occurs, -1 on bridge failure, otherwise 0.
 * A readable/hung-up stop_fd requests Stop; -1 disables external cancellation.
 * Never run this bounded blocking API on the UI thread. It consumes control_bridge. */
typedef struct {
    void *context;
    int64_t generation;
    int stop_fd;
    int (*notify)(void *context, int64_t generation, const char *kind,
                  int channel, int64_t now_ms);
} fe35_scan_transport;

/* ObjC binding: context is a borrowed OHCBScanReceiverSession. The sink receives
 * a borrowed NSArray<OHCBScanReceiverEvent *>; retain only for foreground delivery.
 * It must process CLEAR_PAIRING and generation changes and must never log QR/PIN. */
typedef void (*fe35_scan_event_sink)(void *sink_context, void *events);
typedef struct {
    void *session;
    void *sink_context;
    fe35_scan_event_sink sink;
} fe35_scan_binding;
int fe35_scan_notify(void *binding, int64_t generation, const char *kind,
                     int channel, int64_t now_ms);
/* Returned by value only after the synchronous worker returns. status retains
 * the original 0=protocol success/nonzero=failure convention independently of
 * cleanup. cleanup_confirmed means known resources were released using the
 * existing unregister processing barrier/CID-close acknowledgement, with no
 * unresolved registration; not a remote absence query, process-exit, power or
 * restoration proof. false includes rejected/not-attempted/uncertain cleanup.
 * CLEANED is only the final teardown callback, emitted even on cleanup failure
 * before this return; never infer cleanup_confirmed or lease authority from it.
 * A zero-initialized result is not a completed worker. No result exists if the
 * worker has not returned; an external owner must handle that independently. */
typedef struct {
    bool returned;
    bool cleanup_confirmed;
    int status;
} fe35_scan_completion;
fe35_scan_completion openhc_btstack_scan_inbound(
    const char *run_dir, fe35_bridge_handle control_bridge, fe35_scan_transport *scan);

/* Optional trusted, borrowed authentication binding, never populated from wire
 * input. step: 0=waiting, 1=verified candidate, -1=failed. SEND effects occur
 * outside bridge locks and must complete before step may return a candidate.
 * Bounded-auth commit runs after confirmed transport cleanup and a final owner poll.
 * Explicit WiFi continuation commits privately after auth-CID/listener cleanup while
 * retaining FE35, original owner/lease/deadline, and revocable continuing-session secret;
 * it must independently serialize owner/generation/deadline validation with
 * one-shot key delivery. An unconfigured binding must reject, never use defaults.
 * incarnation is assigned by this transport (not the daemon's reusable CID). */
enum fe36_io_event { FE36_IO_CONNECTED, FE36_IO_DATA, FE36_IO_TICK };
typedef int (*fe36_io_send)(void *, const uint8_t *, size_t);
typedef struct {
    void *context;
    int (*step)(void *, enum fe36_io_event, int64_t incarnation,
                const uint8_t *, size_t, int64_t now_ms, fe36_io_send, void *);
    int (*commit)(void *, int64_t incarnation, int64_t now_ms);
    void (*cancel)(void *);
} fe36_auth_transport;
fe35_scan_completion openhc_btstack_scan_auth_inbound(
    const char *run_dir, fe35_bridge_handle control_bridge,
    fe35_scan_transport *scan, fe36_auth_transport *auth);

/* Explicit opt-in continuation; no default network provider. Provider owns its listener through
 * cancel; C owns accepted TCP until final close. No detached session/key is returned. step returns
 * a retained common batch, including empty waiting batches. Peer IPv4 is in network byte order.
 * cancel must revoke secrets and release its resources; false delegates unknown cleanup. */
enum fe35_wifi_io { FE35_WIFI_BEGIN, FE35_WIFI_NETWORK, FE35_WIFI_LISTEN, FE35_WIFI_ACCEPT };
typedef struct {
    void *context;
    fe35_bridge_batch (*step)(void *, enum fe35_wifi_io, fe35_bridge_handle, int64_t now_ms,
                              int accepted_fd, int *listener_fd, uint32_t *peer_ipv4);
    bool (*cancel)(void *);
} fe35_wifi_transport;
fe35_scan_completion openhc_btstack_scan_wifi_inbound(
    const char *run_dir, fe35_bridge_handle control_bridge,
    fe35_scan_transport *scan, fe36_auth_transport *auth, fe35_wifi_transport *wifi);

#endif
