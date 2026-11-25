/* Bounded BTstack daemon query/local-service probes. Wire format checked against Showcase
 * ce9d1d50758f67307deb3f00c901a8e82894930c:
 * platform/daemon/src/{socket_connection.c,daemon.c}, src/btstack_defines.h.
 * No BTstack implementation code is copied. No power/discovery commands sent.
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

static int command(int fd, uint8_t ocf, const uint8_t *params, size_t size, int64_t deadline) {
    if (size > 255) return -1;
    uint8_t request[264] = {1, 0, 0, 0, 0, 0, ocf, 0xf4, (uint8_t)size};
    request[4] = (uint8_t)(size + 3);
    request[5] = (uint8_t)((size + 3) >> 8);
    if (size) memcpy(request + 9, params, size);
    return transfer(fd, request, size + 9, 1, deadline);
}

static int exchange(int fd, uint8_t ocf, const uint8_t *params, size_t size,
                    uint8_t expected, uint8_t *reply, unsigned expected_size) {
    /* Six-byte LE type/channel/length header, then opcode LE + parameter length.
     * OGF 0x3d -> opcode 0xf400 | OCF.
     */
    int64_t start = now_ms();
    if (start < 0) return -1;
    int64_t deadline = start + 4000;
    if (command(fd, ocf, params, size, deadline)) return -1;
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

static int query(int fd, uint8_t ocf, uint8_t expected, uint8_t *reply, unsigned size) {
    return exchange(fd, ocf, NULL, 0, expected, reply, size);
}

static int connect_daemon(const char *path) {
    int fd = -1;
    struct sockaddr_un addr;
    memset(&addr, 0, sizeof(addr));
    addr.sun_family = AF_UNIX;
    if (strlen(path) >= sizeof(addr.sun_path)) return -1;
    memcpy(addr.sun_path, path, strlen(path) + 1);
    fd = socket(AF_UNIX, SOCK_STREAM, 0);
    if (fd < 0) return -1;
    int one = 1;
    if (setsockopt(fd, SOL_SOCKET, SO_NOSIGPIPE, &one, sizeof(one))) goto failed;
    if (fcntl(fd, F_SETFL, O_NONBLOCK) < 0) goto failed;
    if (connect(fd, (struct sockaddr *)&addr, sizeof(addr)) != 0) {
        if (errno != EINPROGRESS && errno != EAGAIN) goto failed;
        int64_t start = now_ms();
        if (start < 0 || ready(fd, POLLOUT, start + 4000)) goto failed;
        int error = 0;
        socklen_t length = sizeof(error);
        if (getsockopt(fd, SOL_SOCKET, SO_ERROR, &error, &length) || error) goto failed;
    }
    return fd;
failed:
    close(fd);
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
    fd = connect_daemon(path);
    if (fd < 0) goto done;
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

/* Daemon-side registration only. No HCI power lease, discovery or peer traffic.
 * Two transient channels are selected from 16..23; UUIDs are never treated as
 * channel numbers. Do not mutate the persistent channel database.
 */
static uint32_t le32(const uint8_t *p) { return le16(p) | ((uint32_t)le16(p + 2) << 16); }

static size_t service_record(uint8_t *out, uint16_t uuid, uint8_t channel) {
    /* SDP sequence: ServiceClassIDList, ProtocolDescriptorList (L2CAP/RFCOMM),
     * BrowseGroupList. UUID16 is Bluetooth-base UUID compression; not an SPP
     * profile assertion. Daemon adds its own record handle. Ascending attr IDs.
     */
    const uint8_t record[] = {
        0x35, 33,
        0x09, 0, 1, 0x35, 3, 0x19, (uint8_t)(uuid >> 8), (uint8_t)uuid,
        0x09, 0, 4, 0x35, 12,
        0x35, 3, 0x19, 1, 0, 0x35, 5, 0x19, 0, 3, 0x08, channel,
        0x09, 0, 5, 0x35, 3, 0x19, 0x10, 2
    };
    memcpy(out, record, sizeof(record));
    return sizeof(record);
}

static int remove_services(int fd, uint8_t channels[2], uint32_t handles[2]) {
    /* Unregister has no reply. A subsequent GET_STATE is an ordered processing
     * barrier; this is not a remote SDP-absence query or a radio-close proof.
     */
    int64_t start = now_ms();
    if (start < 0) return -1;
    int64_t deadline = start + 4000;
    for (int i = 1; i >= 0; --i) {
        if (handles[i]) {
            uint32_t h = handles[i];
            uint8_t params[] = {(uint8_t)h, (uint8_t)(h >> 8), (uint8_t)(h >> 16), (uint8_t)(h >> 24)};
            if (command(fd, 0x31, params, sizeof(params), deadline)) return -1;
        }
        if (channels[i]) {
            uint8_t params[] = {channels[i], 0};
            if (command(fd, 0x43, params, sizeof(params), deadline)) return -1;
        }
    }
    uint8_t state[3];
    if (query(fd, 1, 0x60, state, sizeof(state))) return -1;
    memset(channels, 0, 2);
    memset(handles, 0, 2 * sizeof(*handles));
    return state[2] == 0 ? 0 : -1;
}

#ifdef OPENHC_BTSTACK_TEST
static int services_probe(const char *path) {
#else
int openhc_btstack_services_probe(void) {
    const char *path = "/tmp/BTstack";
#endif
    uint8_t chosen[2] = {0}, owned[2] = {0}, reply[7], state[3];
    uint32_t handles[2] = {0};
    int fd = -1, result = 1;
    const char *stage = "CONNECT";
    unsigned status = 0;
    /* Two independent connections, explicit cleanup then same-channel reuse.
     * This verifies local re-registration, not an over-the-air close/reopen.
     */
    for (unsigned cycle = 0; cycle < 2; ++cycle) {
        fd = connect_daemon(path);
        if (fd < 0) goto done;
        stage = "STATE";
        if (query(fd, 1, 0x60, state, sizeof(state))) goto done;
        if (state[2] != 0) { stage = "STATE_NOT_OFF"; goto done; }
        for (unsigned i = 0; i < 2; ++i) {
            stage = i == 0 ? "FE35_RFCOMM" : "FE36_RFCOMM";
            uint8_t first = cycle ? chosen[i] : (i ? chosen[0] + 1 : 16);
            uint8_t last = cycle ? first : 23;
            for (uint8_t channel = first; channel <= last; ++channel) {
                uint8_t params[] = {channel, 0, 2}; /* requested MTU 512 */
                if (exchange(fd, 0x42, params, sizeof(params), 0x85, reply, 4)) goto done;
                status = reply[2];
                if (reply[3] != channel) goto done;
                if (!status) { chosen[i] = owned[i] = channel; break; }
                /* Only busy is safe to skip; never unregister somebody else's channel. */
                if (status != 0x71) goto done;
            }
            if (!owned[i]) { stage = "CHANNELS_UNAVAILABLE"; goto done; }
            stage = i == 0 ? "FE35_SDP" : "FE36_SDP";
            uint8_t record[64];
            size_t size = service_record(record, (uint16_t)(0xfe35 + i), chosen[i]);
            if (exchange(fd, 0x30, record, size, 0x90, reply, 7)) goto done;
            status = reply[2];
            uint32_t handle = le32(reply + 3);
            if (status || handle < 0x10000 || (i && handle == handles[0])) goto done;
            handles[i] = handle;
            printf("BTSTACK_FE%02X_LOCAL_CHANNEL=%u\n", 0x35 + i, chosen[i]);
            printf("BTSTACK_FE%02X_SDP_HANDLE=%u\n", 0x35 + i, handle);
        }
        stage = "CLEANUP";
        if (remove_services(fd, owned, handles)) goto done;
        close(fd);
        fd = -1;
        printf("BTSTACK_LOCAL_SERVICE_CYCLE_OK=%u\n", cycle + 1);
    }
    result = 0;
done:
    if (fd >= 0) {
        if (owned[0] || owned[1] || handles[0] || handles[1]) {
            /* A broken stream cannot guarantee explicit cleanup. Close still
             * invokes daemon-owned-client cleanup in the fixed reference.
             */
            if (remove_services(fd, owned, handles)) puts("BTSTACK_CLEANUP_UNCONFIRMED");
        }
        close(fd);
    }
    if (result) printf("BTSTACK_SERVICES_FAILED=%s STATUS=%u\n", stage, status);
    else puts("BTSTACK_LOCAL_SERVICES_OK");
    return result;
}

#ifdef OPENHC_BTSTACK_TEST
int main(int argc, char **argv) {
    if (argc == 2) return probe(argv[1]);
    if (argc == 3 && strcmp(argv[2], "--services") == 0) return services_probe(argv[1]);
    return 2;
}
#endif
