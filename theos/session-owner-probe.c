/* Bounded kernel peer-PID metadata query. No socket application data I/O. */
/* Linux SO_PEERCRED's struct ucred is a GNU extension; this also exposes
 * POSIX lstat/S_ISSOCK under the strict C11 host-test build. */
#if defined(__linux__) && !defined(_GNU_SOURCE)
#define _GNU_SOURCE
#endif
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <poll.h>
#include <fcntl.h>
#include <errno.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

#if defined(__APPLE__) && !defined(LOCAL_PEERPID)
#define LOCAL_PEERPID 0x002
#endif

static int owner_pid(const char *path, pid_t *owner) {
    struct stat before, after;
#ifdef OPENHC_SESSION_OWNER_TEST
    uid_t expected_uid = geteuid();
#else
    uid_t expected_uid = 0;
#endif
    if (lstat(path, &before) != 0 || !S_ISSOCK(before.st_mode) || before.st_uid != expected_uid) return 10;
    int fd = socket(AF_UNIX, SOCK_STREAM, 0);
    if (fd < 0) return 11;
    int flags = fcntl(fd, F_GETFL, 0);
    if (flags < 0 || fcntl(fd, F_SETFL, flags | O_NONBLOCK) < 0) { close(fd); return 12; }
    struct sockaddr_un address;
    memset(&address, 0, sizeof(address));
    address.sun_family = AF_UNIX;
    if (strlen(path) >= sizeof(address.sun_path)) { close(fd); return 13; }
    memcpy(address.sun_path, path, strlen(path) + 1);
    int rc = connect(fd, (struct sockaddr *)&address,
                     (socklen_t)(offsetof(struct sockaddr_un, sun_path) + strlen(path) + 1));
    if (rc < 0 && errno != EINPROGRESS) { close(fd); return 14; }
    if (rc < 0) {
        struct pollfd poller = { fd, POLLOUT, 0 };
        if (poll(&poller, 1, 1500) <= 0 || !(poller.revents & POLLOUT)) { close(fd); return 15; }
        int error = 0; socklen_t error_size = sizeof(error);
        if (getsockopt(fd, SOL_SOCKET, SO_ERROR, &error, &error_size) || error) { close(fd); return 16; }
    }
#if defined(__linux__)
    struct ucred credentials;
    socklen_t length = sizeof(credentials);
    rc = getsockopt(fd, SOL_SOCKET, SO_PEERCRED, &credentials, &length);
    if (!rc && length == sizeof(credentials)) *owner = credentials.pid;
    else rc = -1;
#elif defined(__APPLE__)
    socklen_t length = sizeof(*owner);
    rc = getsockopt(fd, 0 /* SOL_LOCAL on Darwin */, LOCAL_PEERPID, owner, &length);
    if (!rc && length != sizeof(*owner)) rc = -1;
#else
#error Unsupported Unix peer PID platform
#endif
    close(fd);
    if (rc || *owner <= 0) return 17;
    if (lstat(path, &after) || !S_ISSOCK(after.st_mode) || before.st_dev != after.st_dev ||
        before.st_ino != after.st_ino || before.st_uid != expected_uid) return 18;
    return 0;
}

int openhc_session_owner_probe(void) {
    const char *path = "/tmp/showcase_baa.sock";
    pid_t owner = -1;
    alarm(2);
    int rc = owner_pid(path, &owner);
    alarm(0);
    if (rc) printf("SESSION_SOCKET_OWNER_FAILED=%d\n", rc);
    else {
        printf("SESSION_SOCKET_OWNER_PID=%d\n", owner);
        puts("SESSION_SOCKET_APPLICATION_BYTES=0");
        puts("SESSION_SOCKET_OWNER_QUERY_OK");
    }
    return rc ? 1 : 0;
}

#ifdef OPENHC_SESSION_OWNER_TEST
int main(int argc, char **argv) {
    if (argc != 2) return 2;
    pid_t owner = -1;
    int rc = owner_pid(argv[1], &owner);
    if (rc) printf("SESSION_SOCKET_OWNER_FAILED=%d\n", rc);
    else {
        printf("SESSION_SOCKET_OWNER_PID=%d\n", owner);
        puts("SESSION_SOCKET_APPLICATION_BYTES=0");
        puts("SESSION_SOCKET_OWNER_QUERY_OK");
    }
    return rc ? 1 : 0;
}
#endif
