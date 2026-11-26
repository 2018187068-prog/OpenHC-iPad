#include <sys/types.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <sys/stat.h>
#include <sys/file.h>
#include <poll.h>
#include <pwd.h>
#include <grp.h>
#include <unistd.h>
#include <fcntl.h>
#include <signal.h>
#include <errno.h>
#include <string.h>
#include <limits.h>
#include <stdint.h>
#include <time.h>

#if defined(OHC_SCAN_HELPER_TEST_BUILD)
#ifndef OHC_SCAN_HELPER_TEST_SOCKET_PATH
#error OHC_SCAN_HELPER_TEST_SOCKET_PATH is required for test builds
#endif
#define HELPER_SOCKET_PATH OHC_SCAN_HELPER_TEST_SOCKET_PATH
#define HELPER_LOCK_PATH OHC_SCAN_HELPER_TEST_SOCKET_PATH ".lock"
#define HELPER_EXPECTED_PEER_UID geteuid()
#define HELPER_EXPECTED_PEER_GID getegid()
#else
#include <rootless.h>
#define HELPER_SOCKET_PATH ROOT_PATH("/var/run/openhc/scan-ping.sock")
#define HELPER_LOCK_PATH ROOT_PATH("/var/run/openhc/scan-ping.lock")
#endif

#define SOCKET_MODE 0660
#define CLIENT_TIMEOUT_MS 1500

static volatile sig_atomic_t stopping;
static int listener = -1;
static int instanceLock = -1;
static const char *socketPath;
static uid_t expectedSocketUid;
static gid_t expectedSocketGid;
static int ownsSocketPath;

static void stopHandler(int sig) { (void)sig; stopping = 1; }

static int64_t monotonicMillis(void) {
    struct timespec now;
    if (clock_gettime(CLOCK_MONOTONIC, &now) != 0) return -1;
    return (int64_t)now.tv_sec * 1000 + now.tv_nsec / 1000000;
}

static int pollUntil(int fd, short events, int64_t deadlineMs) {
    for (;;) {
        if (stopping) return -1;
        int64_t nowMs = monotonicMillis();
        int64_t remaining = deadlineMs - nowMs;
        if (nowMs < 0 || remaining <= 0) return -1;
        struct pollfd pfd = { .fd = fd, .events = events };
        int ready = poll(&pfd, 1, remaining > INT_MAX ? INT_MAX : (int)remaining);
        if (ready < 0 && errno == EINTR) continue;
        if (ready <= 0 || !(pfd.revents & (events | POLLERR | POLLHUP))) return -1;
        return 0;
    }
}

static int readRequest(int fd, char *buffer, size_t capacity, int64_t deadlineMs) {
    size_t used = 0;
    while (used < capacity) {
        if (pollUntil(fd, POLLIN, deadlineMs) != 0) return -1;
        ssize_t n = read(fd, buffer + used, capacity - used);
        if (n == 0) return (int)used;
        if (n < 0 && (errno == EINTR || errno == EAGAIN || errno == EWOULDBLOCK)) continue;
        if (n < 0) return -1;
        used += (size_t)n;
    }
    return -1;
}

static int writeReply(int fd, int64_t deadlineMs) {
    const char reply[] = "PONG\n";
    size_t offset = 0;
    while (offset < sizeof(reply) - 1) {
        if (pollUntil(fd, POLLOUT, deadlineMs) != 0) return -1;
        ssize_t n = write(fd, reply + offset, sizeof(reply) - 1 - offset);
        if (n < 0 && (errno == EINTR || errno == EAGAIN || errno == EWOULDBLOCK)) continue;
        if (n <= 0) return -1;
        offset += (size_t)n;
    }
    return 0;
}

static void serveClient(int fd, uid_t allowedUid, gid_t allowedGid) {
    uid_t peerUid = (uid_t)-1;
    gid_t peerGid = (gid_t)-1;
    char request[8] = {0};
    // Kernel-derived credentials only; there is no caller-claimed identity field.
    if (getpeereid(fd, &peerUid, &peerGid) != 0 || peerUid != allowedUid || peerGid != allowedGid)
        return;
    int64_t startMs = monotonicMillis();
    if (startMs < 0) return;
    int64_t deadlineMs = startMs + CLIENT_TIMEOUT_MS;
    int n = readRequest(fd, request, sizeof(request), deadlineMs);
    if (n != 5 || memcmp(request, "PING\n", 5) != 0) return;
    (void)writeReply(fd, deadlineMs);
}

static int acquireInstanceLock(void) {
    instanceLock = open(HELPER_LOCK_PATH, O_CREAT | O_RDWR, 0600);
    if (instanceLock < 0) return -1;
    struct stat st;
    if (fstat(instanceLock, &st) != 0 || !S_ISREG(st.st_mode)) return -1;
#if defined(OHC_SCAN_HELPER_TEST_BUILD)
    if (st.st_uid != geteuid()) return -1;
#else
    if (st.st_uid != 0 || (st.st_mode & 0022) != 0) return -1;
#endif
    if (flock(instanceLock, LOCK_EX | LOCK_NB) != 0) return -1;
    return 0;
}

static int prepareSocketPath(void) {
    struct stat st;
    if (lstat(socketPath, &st) != 0) return errno == ENOENT ? 0 : -1;
    if (!S_ISSOCK(st.st_mode) || st.st_uid != expectedSocketUid) return -1;
    return unlink(socketPath);
}

static int createListener(void) {
    listener = socket(AF_UNIX, SOCK_STREAM, 0);
    if (listener < 0) return -1;
    int flags = fcntl(listener, F_GETFL, 0);
    if (flags < 0 || fcntl(listener, F_SETFL, flags | O_NONBLOCK) != 0) return -1;
    struct sockaddr_un address = { .sun_family = AF_UNIX };
    strlcpy(address.sun_path, socketPath, sizeof(address.sun_path));
    if (bind(listener, (struct sockaddr *)&address, sizeof(address)) != 0) return -1;
    ownsSocketPath = 1;
    if (chown(socketPath, expectedSocketUid, expectedSocketGid) != 0
        || chmod(socketPath, SOCKET_MODE) != 0
        || listen(listener, 4) != 0) return -1;
    return 0;
}

int main(void) {
    uid_t allowedUid;
    gid_t allowedGid;
#if defined(OHC_SCAN_HELPER_TEST_BUILD)
    allowedUid = HELPER_EXPECTED_PEER_UID;
    allowedGid = HELPER_EXPECTED_PEER_GID;
    expectedSocketUid = geteuid();
    expectedSocketGid = getegid();
    socketPath = HELPER_SOCKET_PATH;
#else
    struct passwd *mobile = getpwnam("mobile");
    struct group *mobileGroup = getgrnam("mobile");
    if (!mobile || !mobileGroup || geteuid() != 0) return 10;
    allowedUid = mobile->pw_uid;
    allowedGid = mobileGroup->gr_gid;
    expectedSocketUid = 0;
    expectedSocketGid = mobileGroup->gr_gid;
    socketPath = HELPER_SOCKET_PATH;
    struct stat parent;
    if (lstat(ROOT_PATH("/var/run/openhc"), &parent) != 0 || !S_ISDIR(parent.st_mode)
        || parent.st_uid != 0 || (parent.st_mode & 0022) != 0
        || (parent.st_mode & S_IXOTH) == 0) return 19;
#endif
    if (strlen(socketPath) >= sizeof(((struct sockaddr_un *)0)->sun_path)) return 11;
    if (acquireInstanceLock() != 0) goto cleanup_error;
    if (prepareSocketPath() != 0) goto cleanup_error;
    if (createListener() != 0) goto cleanup_error;
    struct sigaction action;
    memset(&action, 0, sizeof(action));
    action.sa_handler = stopHandler;
    sigemptyset(&action.sa_mask);
    if (sigaction(SIGTERM, &action, NULL) != 0 || sigaction(SIGINT, &action, NULL) != 0)
        goto cleanup_error;
    signal(SIGPIPE, SIG_IGN);

    while (!stopping) {
        struct pollfd pfd = { .fd = listener, .events = POLLIN };
        int ready = poll(&pfd, 1, 1000);
        if (ready < 0 && errno == EINTR) continue;
        if (stopping) break;
        if (ready < 0) goto cleanup_error;
        if (ready == 0) continue;
        int client = accept(listener, NULL, NULL);
        if (client < 0) {
            if ((errno == EINTR || errno == EAGAIN) && !stopping) continue;
            goto cleanup_error;
        }
        int clientFlags = fcntl(client, F_GETFL, 0);
        if (clientFlags < 0 || fcntl(client, F_SETFL, clientFlags | O_NONBLOCK) != 0) {
            close(client);
            continue;
        }
        serveClient(client, allowedUid, allowedGid);
        close(client);
    }

    if (listener >= 0) { close(listener); listener = -1; }
    if (ownsSocketPath) { (void)unlink(socketPath); ownsSocketPath = 0; }
    if (instanceLock >= 0) { close(instanceLock); instanceLock = -1; }
    return 0;

cleanup_error:
    if (listener >= 0) { close(listener); listener = -1; }
    if (ownsSocketPath) { (void)unlink(socketPath); ownsSocketPath = 0; }
    if (instanceLock >= 0) { close(instanceLock); instanceLock = -1; }
    return 20;
}
