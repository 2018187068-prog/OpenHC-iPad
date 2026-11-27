/* Kernel evidence only, not a signing/trust policy. Fail closed on unsupported
 * APIs. XNU xnu-8019.80.24 bsd/sys/un.h and bsd/kern/uipc_usrreq.c:
 * LOCAL_PEERTOKEN queries the connected socket's last_pid task. In particular
 * this is NOT an immutable per-message XPC audit credential. No claim of app
 * identity or race-free exec authorization is made; production remains deny-all.
 */
#include "ScanOwner.h"
#include <string.h>
#ifdef __APPLE__
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <mach/message.h>
#include <fcntl.h>
#include <unistd.h>
#include <stdlib.h>
#include <limits.h>

#if defined(LOCAL_PEERTOKEN)
static bool endpoint(struct stat *out) {
    char resolved[PATH_MAX];
    const char *fixed = "/var/jb/var/run/openhc-owner/control.sock";
    if (!realpath(fixed, resolved)) return false;
    int dir = open("/", O_RDONLY | O_DIRECTORY | O_CLOEXEC);
    if (dir < 0) return false;
    char *cursor = resolved + 1;
    bool ok = false;
    for (;;) {
        char *slash = strchr(cursor, '/');
        if (slash) *slash = 0;
        struct stat s;
        if (!*cursor || fstatat(dir, cursor, &s, AT_SYMLINK_NOFOLLOW) || s.st_uid != 0) break;
        if (!slash) {
            /* Fixed root-owned endpoint. Group membership permits connection,
             * never application authorization. No group/world writable parents. */
            if (S_ISSOCK(s.st_mode) && (s.st_mode & 07777) == 0660) { *out = s; ok = true; }
            break;
        }
        if (!S_ISDIR(s.st_mode) || (s.st_mode & 0022)) break;
        int next = openat(dir, cursor, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
        if (next < 0) break;
        close(dir); dir = next; cursor = slash + 1;
    }
    close(dir); return ok;
}
#endif
bool ohc_owner_collect_peer(int fd, uint64_t nonce, uint64_t epoch, ohc_owner_peer *out) {
    memset(out, 0, sizeof(*out));
#if defined(LOCAL_PEERTOKEN)
    struct stat before, after;
    struct sockaddr_un local = {0}, peer = {0};
    socklen_t n = sizeof(local);
    if (!nonce || !epoch || !endpoint(&before) || getsockname(fd, (struct sockaddr *)&local, &n) ||
        local.sun_family != AF_UNIX || strncmp(local.sun_path,
        "/var/jb/var/run/openhc-owner/control.sock", sizeof(local.sun_path))) return false;
    n = sizeof(peer);
    if (getpeername(fd, (struct sockaddr *)&peer, &n) || peer.sun_family != AF_UNIX) return false;
    audit_token_t token = {{0}}; n = sizeof(token);
    uid_t uid; gid_t gid;
    if (getpeereid(fd, &uid, &gid) || getsockopt(fd, SOL_LOCAL, LOCAL_PEERTOKEN, &token, &n) ||
        n != sizeof(token) || sizeof(token) != sizeof(out->token) ||
        token.val[1] != uid || token.val[2] != gid || !token.val[5] ||
        !endpoint(&after) || before.st_dev != after.st_dev || before.st_ino != after.st_ino) return false;
    memcpy(out->token, &token, sizeof(token));
    out->connection = nonce; out->policy_epoch = epoch;
    out->endpoint_device = (uint64_t)before.st_dev; out->endpoint_inode = (uint64_t)before.st_ino;
    out->kernel_verified = out->endpoint_verified = true; return true;
#else
    (void)fd; (void)nonce; (void)epoch; return false;
#endif
}
#else
bool ohc_owner_collect_peer(int fd, uint64_t nonce, uint64_t epoch, ohc_owner_peer *out) {
    (void)fd; (void)nonce; (void)epoch; memset(out, 0, sizeof(*out)); return false;
}
#endif
