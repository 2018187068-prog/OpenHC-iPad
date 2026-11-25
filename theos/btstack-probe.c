/* Bounded BTstack daemon query probe. Wire format checked against Showcase
 * ce9d1d50758f67307deb3f00c901a8e82894930c:
 * platform/daemon/src/{socket_connection.c,daemon.c}, src/btstack_defines.h.
 * No BTstack implementation code is copied. No radio-setting commands sent.
 */
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <time.h>
#include <unistd.h>

static int64_t now_ms(void) {
    struct timespec t;
    if (clock_gettime(CLOCK_MONOTONIC, &t) != 0) return -1;
    return (int64_t)t.tv_sec * 1000 + t.tv_nsec / 1000000;
}

static int ready(int fd, short events, int64_t deadline) {
    for (;;) {
        int64_t now = now_ms();
        if (now < 0 || now >= deadline) return -1;
        struct pollfd p = {fd, events, 0};
        int r = poll(&p, 1, (int)(deadline - now));
        if (r < 0 && errno == EINTR) continue;
        return r > 0 && (p.revents & events) ? 0 : -1;
    }
}

static int transfer(int fd, uint8_t *buf, size_t size, int sending, int64_t deadline) {
    while (size) {
        if (ready(fd, sending ? POLLOUT : POLLIN, deadline) != 0) return -1;
        ssize_t n = sending ? send(fd, buf, size, 0) : recv(fd, buf, size, 0);
        if (n < 0 && (errno == EINTR || errno == EAGAIN || errno == EWOULDBLOCK)) continue;
        if (n <= 0) return -1;
        buf += n;
        size -= (size_t)n;
    }
    return 0;
}

static unsigned le16(const uint8_t *p) { return p[0] | ((unsigned)p[1] << 8); }

static int query(int fd, uint8_t ocf, uint8_t expected, uint8_t *reply, unsigned expected_size) {
    /* Six-byte LE type/channel/length header, then opcode LE + parameter length.
     * OGF 0x3d -> opcode 0xf400 | OCF. Only GET_VERSION=4 / GET_STATE=1.
     */
    uint8_t request[] = {1, 0, 0, 0, 3, 0, ocf, 0xf4, 0};
    int64_t start = now_ms();
    if (start < 0) return -1;
    int64_t deadline = start + 4000;
    if (transfer(fd, request, sizeof(request), 1, deadline)) return -1;
    for (unsigned i = 0; i < 32; ++i) {
        uint8_t header[6], body[1024];
        if (transfer(fd, header, sizeof(header), 0, deadline)) return -1;
        unsigned size = le16(header + 4);
        if (size > sizeof(body)) return -1;
        if (transfer(fd, body, size, 0, deadline)) return -1;
        if (le16(header) != 4) continue;
        if (size < 2 || body[1] != size - 2) return -1;
        if (body[0] != expected) continue;
        if (le16(header + 2) != 0 || size != expected_size) return -1;
        memcpy(reply, body, size);
        return 0;
    }
    return -1;
}

/* Path injection exists only in the separately compiled CI test executable. */
#ifdef OPENHC_BTSTACK_TEST
static int probe(const char *path) {
#else
int openhc_btstack_probe(void) {
    const char *path = "/tmp/BTstack";
#endif
    int fd = -1, result = 1;
    const char *stage = "CONNECT";
    uint8_t version[6], state[3];
    struct sockaddr_un addr;
    memset(&addr, 0, sizeof(addr));
    addr.sun_family = AF_UNIX;
    if (strlen(path) >= sizeof(addr.sun_path)) goto done;
    memcpy(addr.sun_path, path, strlen(path) + 1);
    fd = socket(AF_UNIX, SOCK_STREAM, 0);
    if (fd < 0) goto done;
    int one = 1;
    if (setsockopt(fd, SOL_SOCKET, SO_NOSIGPIPE, &one, sizeof(one))) goto done;
    if (fcntl(fd, F_SETFL, O_NONBLOCK) < 0) goto done;
    if (connect(fd, (struct sockaddr *)&addr, sizeof(addr)) != 0) {
        if (errno != EINPROGRESS && errno != EAGAIN) goto done;
        int64_t start = now_ms();
        if (start < 0 || ready(fd, POLLOUT, start + 4000)) goto done;
        int error = 0;
        socklen_t length = sizeof(error);
        if (getsockopt(fd, SOL_SOCKET, SO_ERROR, &error, &length) || error) goto done;
    }
    stage = "VERSION";
    if (query(fd, 4, 0x63, version, sizeof(version))) goto done;
    stage = "STATE";
    if (query(fd, 1, 0x60, state, sizeof(state))) goto done;
    printf("BTSTACK_VERSION=%u.%u\n", version[2], version[3]);
    printf("BTSTACK_REVISION=%u\n", le16(version + 4));
    printf("BTSTACK_STATE=%u\n", state[2]);
    result = 0;
done:
    if (fd >= 0) close(fd);
    if (result) printf("BTSTACK_QUERY_FAILED=%s\n", stage);
    else puts("BTSTACK_QUERY_OK");
    return result;
}

#ifdef OPENHC_BTSTACK_TEST
int main(int argc, char **argv) { return argc == 2 ? probe(argv[1]) : 2; }
#endif
