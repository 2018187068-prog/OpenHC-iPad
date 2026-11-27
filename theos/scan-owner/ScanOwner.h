#ifndef OHC_SCAN_OWNER_H
#define OHC_SCAN_OWNER_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "../fe35-control-bridge.h"

/* Internal API, never a wire structure. All calls/effects serialized on one
 * owner executor. Effect handlers must not re-enter. Lease effects adapt Trial
 * arm/takeover/restore: no second power controller or UI heartbeat writer.
 * Deployment lacks trusted app policy and native Trial actor: deny all. */
typedef struct {
    uint32_t token[8]; /* complete kernel audit token, including pidversion */
    uint64_t connection; /* server nonce, never recycled or client supplied */
    uint64_t endpoint_device, endpoint_inode, policy_epoch;
    bool kernel_verified, endpoint_verified;
} ohc_owner_peer;
typedef enum {
    OHC_ARM_GUARD, OHC_TAKEOVER, OHC_RUN_WORKER, OHC_CLEAR,
    OHC_CANCEL_WORKER, OHC_HEARTBEAT, OHC_STOP_HEARTBEAT,
    OHC_REQUEST_RESTORE, OHC_DELEGATE_GUARD, OHC_RELEASED
} ohc_owner_effect;
typedef void (*ohc_owner_emit)(void *, ohc_owner_effect, uint64_t, int64_t);
typedef enum { OHC_IDLE, OHC_ARMING, OHC_TAKING, OHC_RUNNING,
               OHC_STOPPING, OHC_RESTORING, OHC_DELEGATED } ohc_owner_state;
typedef struct {
    ohc_owner_state state;
    ohc_owner_peer peer;
    uint64_t generation;
    int64_t deadline, phase_deadline, last_now, last_heartbeat;
    bool worker_started, worker_returned, execution_exited, revoked, cancelled, heartbeat;
    bool delegated, recovery_verified, rfcomm, sdp, published, accepted, handed;
    fe35_scan_completion completion;
    ohc_owner_emit emit;
    void *context;
#ifdef OPENHC_SCAN_OWNER_TEST
    /* Absent in production. No environment/wire switch enables injection. */
    bool (*test_admit)(const ohc_owner_peer *);
#endif
} ohc_owner;
typedef struct {
    ohc_owner_peer peer;
    char frame[12]; size_t used;
    bool connected, clock_set, started;
    int64_t opened_at, partial_at;
} ohc_owner_connection;
void ohc_owner_init(ohc_owner *, ohc_owner_emit, void *);
bool ohc_owner_open(ohc_owner_connection *, const ohc_owner_peer *);
/* Acceptor samples fresh evidence from the same connected fd on each read/tick.
 * Evidence change fails closed before bytes are interpreted. */
bool ohc_owner_feed(ohc_owner *, ohc_owner_connection *, const ohc_owner_peer *,
                    const void *, size_t, int64_t);
void ohc_owner_disconnect(ohc_owner *, ohc_owner_connection *, int64_t);
void ohc_owner_tick(ohc_owner *, int64_t);
void ohc_owner_guard_ready(ohc_owner *, uint64_t, bool, int64_t);
void ohc_owner_working(ohc_owner *, uint64_t, bool, int64_t);
bool ohc_owner_transport_event(ohc_owner *, uint64_t, const char *, int64_t);
/* Trusted common sink preflight, outside effect handlers and before forwarding
 * its event batch. Only CLOSE_CONTROL_TRANSPORT is terminal; accepted CLEAR
 * alone must preserve the same-PIN handoff. Generation is the captured owner
 * fence, not a client field or common generation. No cleanup/recovery authority. */
void ohc_owner_common_event(ohc_owner *, uint64_t, const char *, int64_t);
bool ohc_owner_pairing(ohc_owner *, uint64_t);
bool ohc_owner_handoff(ohc_owner *, uint64_t);
void ohc_owner_completed(ohc_owner *, uint64_t, fe35_scan_completion, bool execution_exited, int64_t);
/* Independent guard observation, never a client frame or worker callback. */
void ohc_owner_recovered(ohc_owner *, uint64_t, bool restoration_verified);
void ohc_owner_execution_exited(ohc_owner *, uint64_t, bool independently_exited);
/* Darwin kernel evidence is NOT app authorization. Fixed internal endpoint. */
bool ohc_owner_collect_peer(int connected_fd, uint64_t nonce, uint64_t policy_epoch,
                            ohc_owner_peer *);
#endif
