/* Metadata-only endpoint owner probe. No broker messages, recv, send or keys.
 * LOCAL_PEERPID query follows read-only Showcase.m reusable_baa_broker(),
 * but never invokes that routine's subsequent certificate/signing operations.
 * The release executable accepts no user-supplied endpoint.
 */
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

#ifndef LOCAL_PEERPID
#define LOCAL_PEERPID 0x002
#endif

static int owner_pid(const char *path, pid_t *owner) {
    struct stat st;
    if (lstat(path, &st) != 0) return 10;
    if (!S_ISSOCK(st.st_mode) || st.st_uid != geteuid()) return 11;
    struct sockaddr_un address;
    memset(&address, 0, sizeof(address));
    address.sun_family = AF_UNIX;
    if (strlen(path) >= sizeof(address.sun_path)) return 12;
    memcpy(address.sun_path, path, strlen(path) + 1);
    address.sun_len = (unsigned char)(offsetof(struct sockaddr_un, sun_path) + strlen(path) + 1);
    int fd = socket(AF_UNIX, SOCK_STREAM, 0);
    if (fd < 0) return 13;
    int flags = fcntl(fd, F_GETFL);
    if (flags < 0 || fcntl(fd, F_SETFL, flags | O_NONBLOCK) < 0) {
        close(fd); return 14;
    }
    int rc = connect(fd, (struct sockaddr *)&address, address.sun_len);
    if (rc < 0 && errno == EINPROGRESS) {
        struct pollfd event = { .fd = fd, .events = POLLOUT };
        int error = 0;
        socklen_t length = sizeof(error);
        rc = poll(&event, 1, 1500);
        if (rc <= 0 || getsockopt(fd, SOL_SOCKET, SO_ERROR, &error, &length) != 0 || error) {
            close(fd); return 15;
        }
    } else if (rc < 0) {
        close(fd); return 16;
    }
    socklen_t length = sizeof(*owner);
    *owner = 0;
    rc = getsockopt(fd, 0 /* SOL_LOCAL */, LOCAL_PEERPID, owner, &length);
    close(fd); /* zero application bytes were read or written */
    if (rc != 0 || length != sizeof(*owner) || *owner <= 0) return 17;
    struct stat after;
    if (lstat(path, &after) != 0 || after.st_dev != st.st_dev ||
        after.st_ino != st.st_ino || !S_ISSOCK(after.st_mode) || after.st_uid != st.st_uid)
        return 18;
    return 0;
}

int main(int argc, char **argv) {
    const char *path = "/tmp/showcase_baa.sock";
#ifdef OPENHC_ROLE_TEST
    if (argc != 2) return 2;
    path = argv[1];
#else
    (void)argv;
    if (argc != 1) return 2;
    if (geteuid() != 0) { puts("BROKER_OWNER_FAILED=ROOT_REQUIRED"); return 3; }
#endif
    alarm(4);
    pid_t owner;
    int rc = owner_pid(path, &owner);
    alarm(0);
    if (rc) { printf("BROKER_OWNER_FAILED=%d\n", rc); return 1; }
    printf("BROKER_ENDPOINT_OWNER_PID=%d\n", owner);
    puts("BROKER_APPLICATION_BYTES_SENT=0");
    puts("BROKER_APPLICATION_BYTES_READ=0");
    puts("BROKER_ENDPOINT_OWNER_QUERY_OK");
    return 0;
}
