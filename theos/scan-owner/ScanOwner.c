#include "ScanOwner.h"
#include <limits.h>
#include <string.h>

static void effect(ohc_owner *o, ohc_owner_effect e) {
    if (o->emit) o->emit(o->context, e, o->generation, o->deadline);
}
static bool same(const ohc_owner_peer *a, const ohc_owner_peer *b) {
    return a->kernel_verified && b->kernel_verified && a->endpoint_verified && b->endpoint_verified &&
        a->connection && a->connection == b->connection &&
        a->policy_epoch && a->policy_epoch == b->policy_epoch &&
        a->endpoint_device == b->endpoint_device && a->endpoint_inode == b->endpoint_inode &&
        !memcmp(a->token, b->token, sizeof(a->token));
}
static void revoke(ohc_owner *o) {
    if (!o->revoked) { o->revoked = true; effect(o, OHC_CLEAR); }
}
static void stop(ohc_owner *o, int64_t now) {
    if (o->state == OHC_IDLE) return;
    revoke(o);
    if (o->worker_started && !o->worker_returned && !o->cancelled) {
        o->cancelled = true; effect(o, OHC_CANCEL_WORKER);
    }
    if (o->state == OHC_ARMING || o->state == OHC_TAKING || o->state == OHC_RUNNING) {
        o->state = OHC_STOPPING; o->phase_deadline = now + 1000;
    }
}
static void heartbeat_stop(ohc_owner *o) {
    if (o->heartbeat) { o->heartbeat = false; effect(o, OHC_STOP_HEARTBEAT); }
}
static void delegate(ohc_owner *o) {
    revoke(o); heartbeat_stop(o); o->state = OHC_DELEGATED;
    if (!o->delegated) { o->delegated = true; effect(o, OHC_DELEGATE_GUARD); }
    /* Keep fence and worker until independently recovered AND returned. */
}
static void maybe_release(ohc_owner *o) {
    if (o->recovery_verified && (!o->worker_started || (o->worker_returned && o->execution_exited))) {
        o->state = OHC_IDLE; effect(o, OHC_RELEASED);
    }
}
void ohc_owner_init(ohc_owner *o, ohc_owner_emit emit, void *context) {
    memset(o, 0, sizeof(*o)); o->emit = emit; o->context = context;
}
bool ohc_owner_open(ohc_owner_connection *c, const ohc_owner_peer *p) {
    memset(c, 0, sizeof(*c));
    if (!same(p, p)) return false;
    c->peer = *p; c->connected = true; return true;
}
static bool admit(ohc_owner *o, const ohc_owner_peer *p) {
    (void)o; (void)p;
#ifdef OPENHC_SCAN_OWNER_TEST
    return o->test_admit && o->test_admit(p);
#else
    return false;
#endif
}
static bool start(ohc_owner *o, const ohc_owner_peer *p, int64_t now) {
    if (o->state != OHC_IDLE || !admit(o, p) || now < 0 ||
        now > INT64_MAX - 240000 || o->generation == UINT64_MAX) return false;
    uint64_t g = o->generation + 1;
    ohc_owner_emit emit = o->emit; void *context = o->context;
#ifdef OPENHC_SCAN_OWNER_TEST
    bool (*policy)(const ohc_owner_peer *) = o->test_admit;
#endif
    ohc_owner_init(o, emit, context);
#ifdef OPENHC_SCAN_OWNER_TEST
    o->test_admit = policy;
#endif
    o->generation = g; o->peer = *p; o->state = OHC_ARMING;
    o->deadline = now + 240000; o->last_now = now; o->phase_deadline = now + 3000;
    effect(o, OHC_ARM_GUARD); return true;
}
bool ohc_owner_feed(ohc_owner *o, ohc_owner_connection *c, const ohc_owner_peer *fresh,
                    const void *bytes, size_t size, int64_t now) {
    if (!c->connected) return false;
    if (!same(&c->peer, fresh) || size > 64 || (!bytes && size) || now < 0) {
        ohc_owner_disconnect(o, c, now); return false;
    }
    if (!c->clock_set) { c->clock_set = true; c->opened_at = now; }
    if (now < c->opened_at || (!c->started && now - c->opened_at >= 2000) ||
        (c->used && now - c->partial_at >= 1000)) goto reject;
    const char *p = bytes;
    for (size_t i = 0; i < size; ++i) {
        if (!c->used) c->partial_at = now;
        if (c->used == sizeof(c->frame) - 1 || p[i] == '\0' || p[i] == '\r') goto reject;
        c->frame[c->used++] = p[i];
        if (p[i] != '\n') continue;
        c->frame[c->used] = 0;
        if (!strcmp(c->frame, "START\n")) {
            if (c->started || !start(o, &c->peer, now)) goto reject;
            c->started = true;
        } else if (!strcmp(c->frame, "STOP\n") || !strcmp(c->frame, "BACKGROUND\n")) {
            if (o->state == OHC_IDLE || !same(&o->peer, &c->peer)) goto reject;
            stop(o, now);
        } else goto reject;
        c->used = 0;
    }
    ohc_owner_tick(o, now); return c->connected;
reject:
    ohc_owner_disconnect(o, c, now); return false;
}
void ohc_owner_disconnect(ohc_owner *o, ohc_owner_connection *c, int64_t now) {
    if (c->connected && o->state != OHC_IDLE && same(&c->peer, &o->peer)) stop(o, now);
    c->connected = false; c->used = 0;
}
void ohc_owner_tick(ohc_owner *o, int64_t now) {
    if (o->state == OHC_IDLE) return;
    if (now < o->last_now || now > INT64_MAX - 3000) { stop(o, o->last_now); delegate(o); return; }
    o->last_now = now;
    if (now >= o->deadline) stop(o, now);
    if ((o->state == OHC_ARMING || o->state == OHC_TAKING || o->state == OHC_STOPPING ||
         o->state == OHC_RESTORING) && now >= o->phase_deadline) delegate(o);
    if (o->heartbeat && now - o->last_heartbeat >= 2000 && now < o->deadline) {
        o->last_heartbeat = now; effect(o, OHC_HEARTBEAT);
    }
}
void ohc_owner_guard_ready(ohc_owner *o, uint64_t g, bool ready, int64_t now) {
    if (g != o->generation) return;
    ohc_owner_tick(o, now);
    if (g != o->generation || o->state != OHC_ARMING) return;
    if (!ready) { delegate(o); return; }
    o->heartbeat = true; o->last_heartbeat = now; effect(o, OHC_HEARTBEAT);
    o->state = OHC_TAKING; o->phase_deadline = now + 3000; effect(o, OHC_TAKEOVER);
}
void ohc_owner_working(ohc_owner *o, uint64_t g, bool working, int64_t now) {
    if (g != o->generation) return;
    ohc_owner_tick(o, now);
    if (g != o->generation || o->state != OHC_TAKING) return;
    if (!working) { delegate(o); return; }
    o->state = OHC_RUNNING; o->worker_started = true; effect(o, OHC_RUN_WORKER);
}
bool ohc_owner_transport_event(ohc_owner *o, uint64_t g, const char *kind, int64_t now) {
    if (g != o->generation) return false;
    ohc_owner_tick(o, now);
    if (g != o->generation || o->state != OHC_RUNNING || o->cancelled) return false;
    if (!strcmp(kind, "RFCOMM_READY")) o->rfcomm = true;
    else if (!strcmp(kind, "SDP_READY")) o->sdp = true;
    else if (!strcmp(kind, "ACCEPTED")) {
        if (!o->published) { stop(o, now); return false; }
        o->accepted = true; revoke(o); return true;
    } else if (!strcmp(kind, "STOP") || !strcmp(kind, "FAILED")) { stop(o, now); return false; }
    /* CLEANED/PONG never supply readiness or recovery evidence. */
    return true;
}
void ohc_owner_common_event(ohc_owner *o, uint64_t g, const char *kind, int64_t now) {
    if (g != o->generation || !kind || strcmp(kind, "CLOSE_CONTROL_TRANSPORT")) return;
    /* A shorter common scan budget can expire while the independent owner
     * lease is still valid. Revoke/cancel now, not on a later native FAILED. */
    (void)ohc_owner_transport_event(o, g, "STOP", now);
}
bool ohc_owner_pairing(ohc_owner *o, uint64_t g) {
    if (g != o->generation || o->state != OHC_RUNNING || o->revoked ||
        !o->rfcomm || !o->sdp || o->published) return false;
    o->published = true; return true;
}
bool ohc_owner_handoff(ohc_owner *o, uint64_t g) {
    if (g != o->generation || o->state != OHC_RUNNING || !o->accepted || o->handed || o->cancelled) return false;
    o->handed = true; return true;
}
void ohc_owner_completed(ohc_owner *o, uint64_t g, fe35_scan_completion c,
                          bool exited, int64_t now) {
    if (g != o->generation || !o->worker_started || o->worker_returned) return;
    ohc_owner_tick(o, now);
    revoke(o); o->completion = c; o->worker_returned = c.returned;
    o->execution_exited = c.returned && exited; heartbeat_stop(o);
    if (o->delegated) { maybe_release(o); return; }
    /* Only the native API's documented success/failure statuses are understood.
     * Cancellation/failure (1) may still have confirmed cleanup; unknown status
     * values cannot acquire recovery authority merely by setting two booleans. */
    if (!c.returned || !c.cleanup_confirmed || !exited ||
        (c.status != 0 && c.status != 1) || now >= o->deadline) { delegate(o); return; }
    o->state = OHC_RESTORING; o->phase_deadline = now + 3000;
    effect(o, OHC_REQUEST_RESTORE); /* guard owns OFF/restore, never here */
}
void ohc_owner_recovered(ohc_owner *o, uint64_t g, bool verified) {
    if (g != o->generation || (o->state != OHC_RESTORING && o->state != OHC_DELEGATED)) return;
    if (!verified) { delegate(o); return; }
    o->recovery_verified = true; maybe_release(o);
}
void ohc_owner_execution_exited(ohc_owner *o, uint64_t g, bool exited) {
    if (g != o->generation || o->state == OHC_IDLE) return;
    if (!exited) { delegate(o); return; }
    o->execution_exited = true; maybe_release(o);
}
