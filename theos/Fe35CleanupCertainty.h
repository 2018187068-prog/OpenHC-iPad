#ifndef OPENHC_FE35_CLEANUP_CERTAINTY_H
#define OPENHC_FE35_CLEANUP_CERTAINTY_H

static inline int openhc_fe35_cleanup_confirmed(int cleanup_ok, int close_ok,
        int registration_pending, int cleanup_uncertain, int cid_owned,
        int cid_opened, int cid_disconnected, int auth_cid_owned,
        int auth_disconnected) {
    return cleanup_ok && close_ok && !registration_pending &&
            !cleanup_uncertain && (!cid_owned || cid_opened || cid_disconnected) &&
            (!auth_cid_owned || auth_disconnected);
}

#endif
