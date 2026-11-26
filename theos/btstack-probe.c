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
#include <stdlib.h>
#include <string.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <time.h>
#include <unistd.h>
#include "fe35-control-bridge.h"

static int query(int fd, uint8_t ocf, uint8_t expected, uint8_t *reply, unsigned size);
static int connect_daemon(const char *path);
static int64_t now_ms(void);
static int transfer_guarded(int fd, uint8_t *buf, size_t size, int sending,
                            int64_t deadline, const char *run_dir);

static int read_bounded(int fd, uint8_t *buf, size_t size, int64_t deadline) {
    while (size) {
        int64_t now = now_ms();
        if (now < 0 || now >= deadline) return -1;
        struct pollfd p = {fd, POLLIN, 0};
        int ready_count = poll(&p, 1, (int)(deadline - now));
        if (ready_count < 0 && errno == EINTR) continue;
        if (ready_count <= 0 || !(p.revents & (POLLIN | POLLHUP))) return -1;
        ssize_t n = read(fd, buf, size);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) return -1;
        buf += n;
        size -= (size_t)n;
    }
    return 0;
}

static int require_input_eof(int fd, int64_t deadline) {
    for (;;) {
        int64_t now = now_ms();
        if (now < 0 || now >= deadline) return -1;
        struct pollfd p = {fd, POLLIN, 0};
        int ready_count = poll(&p, 1, (int)(deadline - now));
        if (ready_count < 0 && errno == EINTR) continue;
        if (ready_count <= 0 || !(p.revents & (POLLIN | POLLHUP))) return -1;
        uint8_t extra;
        ssize_t n = read(fd, &extra, 1);
        if (n < 0 && errno == EINTR) continue;
        return n == 0 ? 0 : -1;
    }
}

static int read_bridge_input(fe35_bridge_input *input) {
    uint8_t header[2], length;
    uint8_t *parts[] = {NULL, input->root_key, input->const_a, input->const_b};
    size_t *sizes[] = {NULL, &input->root_key_size, &input->const_a_size, &input->const_b_size};
    memset(input, 0, sizeof(*input));
    int64_t deadline = now_ms() + 3000;
    if (read_bounded(STDIN_FILENO, header, sizeof(header), deadline)) return -1;
    if (header[0] != 1 || header[1] == 0 || header[1] > sizeof(input->device_id) - 1) return -1;
    if (read_bounded(STDIN_FILENO, (uint8_t *)input->device_id, header[1], deadline)) return -1;
    if (memchr(input->device_id, 0, header[1])) return -1;
    input->device_id[header[1]] = 0;
    for (unsigned i = 1; i <= 3; ++i) {
        if (read_bounded(STDIN_FILENO, &length, 1, deadline) ||
            length == 0 || length > 64 ||
            read_bounded(STDIN_FILENO, parts[i], length, deadline)) return -1;
        *sizes[i] = length;
    }
    return require_input_eof(STDIN_FILENO, deadline);
}

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

static int guard_ready(const char *run_dir) {
    char path[512], value[64];
    if (!run_dir || snprintf(path, sizeof(path), "%s/ready", run_dir) >= (int)sizeof(path)) return -1;
    FILE *file = fopen(path, "r");
    if (!file) return -1;
    int ok = fgets(value, sizeof(value), file) && strcmp(value, "READY\n") == 0;
    fclose(file);
    if (!ok) return -1;
    if (snprintf(path, sizeof(path), "%s/result", run_dir) >= (int)sizeof(path)) return -1;
    if (access(path, F_OK) == 0) return -1;
    if (snprintf(path, sizeof(path), "%s/deadline", run_dir) >= (int)sizeof(path)) return -1;
    file = fopen(path, "r");
    if (!file) return -1;
    long long deadline = 0;
    ok = fscanf(file, "%lld", &deadline) == 1 && deadline > (long long)time(NULL) + 30;
    fclose(file);
    if (!ok) return -1;
    return 0;
}

static int transfer_guarded(int fd, uint8_t *buf, size_t size, int sending,
                            int64_t deadline, const char *run_dir) {
    while (size) {
        int64_t now = now_ms();
        if (now < 0 || now >= deadline) return -1;
        int64_t slice = now + 2000;
        if (slice > deadline) slice = deadline;
        struct pollfd p = {fd, sending ? POLLOUT : POLLIN, 0};
        int r = poll(&p, 1, (int)(slice - now));
        if (r < 0 && errno == EINTR) continue;
        if (r == 0) continue;
        if (r < 0 || !(p.revents & (sending ? POLLOUT : POLLIN))) return -1;
        ssize_t n = sending ? send(fd, buf, size, 0) : recv(fd, buf, size, 0);
        if (n < 0 && (errno == EINTR || errno == EAGAIN || errno == EWOULDBLOCK)) continue;
        if (n <= 0) return -1;
        buf += n;
        size -= (size_t)n;
    }
    (void)run_dir; /* Only the power driver owns guard heartbeat updates. */
    return 0;
}

static int send_btstack_packet(int fd, uint16_t type, uint16_t channel,
                               const uint8_t *body, size_t size, int64_t deadline,
                               const char *run_dir) {
    if (size > 1024) return -1;
    uint8_t header[6] = {(uint8_t)type, (uint8_t)(type >> 8),
                         (uint8_t)channel, (uint8_t)(channel >> 8),
                         (uint8_t)size, (uint8_t)(size >> 8)};
    if (transfer_guarded(fd, header, sizeof(header), 1, deadline, run_dir)) return -1;
    return transfer_guarded(fd, (uint8_t *)body, size, 1, deadline, run_dir);
}

/* Returns 0 for an allowlisted event/data frame, -2 for a rejected frame. */
static int receive_transport_packet(int fd, uint16_t expected_cid, uint16_t *type,
                                    uint16_t *channel, uint8_t *body, size_t *size,
                                    int64_t deadline, const char *run_dir) {
    uint8_t header[6];
    if (transfer_guarded(fd, header, sizeof(header), 0, deadline, run_dir)) return -1;
    *type = (uint16_t)le16(header);
    *channel = (uint16_t)le16(header + 2);
    *size = le16(header + 4);
    if (*size > 1024) return -2;
    if (*type == 7) {
        if (*channel != expected_cid || *size > 512) return -2;
    } else if (*type == 4 && *channel == 0 && *size >= 2) {
        uint8_t event_header[2];
        if (transfer_guarded(fd, event_header, 2, 0, deadline, run_dir)) return -1;
        if (event_header[0] != 0x60 && event_header[0] != 0x80 &&
            event_header[0] != 0x81 && event_header[0] != 0x82) return -2;
        body[0] = event_header[0];
        body[1] = event_header[1];
        if (event_header[1] != *size - 2 &&
            !(event_header[0] == 0x80 && *size == 17 && event_header[1] == 16)) return -2;
        if ((event_header[0] == 0x60 && *size != 3) ||
            (event_header[0] == 0x80 && *size != 16 && *size != 17) ||
            (event_header[0] == 0x82 && *size != 11) ||
            (event_header[0] == 0x81 && *size != 4)) return -2;
        if (event_header[0] == 0x80) {
            uint8_t discard[6];
            if (transfer_guarded(fd, body + 2, 1, 0, deadline, run_dir) ||
                transfer_guarded(fd, discard, sizeof(discard), 0, deadline, run_dir) ||
                transfer_guarded(fd, body + 9, *size - 9, 0, deadline, run_dir)) return -1;
        } else if (event_header[0] == 0x82) {
            uint8_t discard_address[6];
            if (transfer_guarded(fd, discard_address, sizeof(discard_address), 0, deadline, run_dir) ||
                transfer_guarded(fd, body + 8, *size - 8, 0, deadline, run_dir)) return -1;
        } else if (transfer_guarded(fd, body + 2, *size - 2, 0, deadline, run_dir)) {
            return -1;
        }
        return 0;
    } else {
        return -2;
    }
    return transfer_guarded(fd, body, *size, 0, deadline, run_dir);
}

static int addr_from_text(const char *text, uint8_t reversed[6]) {
    unsigned values[6];
    char tail;
    if (sscanf(text, "%2x:%2x:%2x:%2x:%2x:%2x%c", &values[0], &values[1], &values[2],
               &values[3], &values[4], &values[5], &tail) != 6) return -1;
    for (unsigned i = 0; i < 6; ++i) {
        if (values[i] > 255) return -1;
        reversed[5 - i] = (uint8_t)values[i];
    }
    return 0;
}

static int transport_synthetic(const char *path, const char *address, unsigned server_channel,
                               const char *profile, const char *run_dir) {
    static const uint8_t payload[] = "OPENHC-SYNTHETIC-CONTROL-v1";
    uint8_t address_wire[6], state[3], params[7];
    uint8_t body[1024];
    uint16_t packet_type, channel, cid = 0;
    size_t size;
    int fd = -1, result = 1, opened = 0, disconnected = 0;
    const char *stage = "GUARD";
    if (guard_ready(run_dir) || addr_from_text(address, address_wire) ||
        server_channel < 1 || server_channel > 30 ||
        (strcmp(profile, "auto") && strcmp(profile, "strict") && strcmp(profile, "reference"))) goto done;
    fd = connect_daemon(path);
    if (fd < 0) { stage = "CONNECT"; goto done; }
    stage = "STATE";
    if (query(fd, 1, 0x60, state, sizeof(state)) || state[2] != 2) goto done;
    memcpy(params, address_wire, 6);
    params[6] = (uint8_t)server_channel;
    stage = "CREATE";
    if (command(fd, 0x40, params, sizeof(params), now_ms() + 4000)) goto done;
    stage = "OPEN_EVENT";
    {
        int64_t deadline = now_ms() + 25000;
#ifdef OPENHC_TRANSPORT_TEST_TIMEOUTS
        deadline = now_ms() + 150;
#endif
        for (unsigned n = 0; n < 256; ++n) {
            int received = receive_transport_packet(fd, 0, &packet_type, &channel, body, &size, deadline, run_dir);
            if (received) {
                stage = received == -1 ? "OPEN_EVENT_TIMEOUT_OR_IO" : "OPEN_EVENT_REJECTED";
                goto done;
            }
            if (packet_type != 4 || body[0] != 0x80) continue;
            if (size >= 14 && body[2] == 0) cid = (uint16_t)le16(body + 12);
            int strict = size == 17 && body[1] == 15;
            int reference = size == 17 && body[1] == 16;
            int failed = size == 16 && body[1] == 14 && body[2] != 0;
            if (failed) { stage = "CREATE_FAILED"; goto done; }
            if (!cid || body[2] || body[11] != server_channel || (!strict && !reference) ||
                (!strcmp(profile, "strict") && !strict) ||
                (!strcmp(profile, "reference") && !reference)) { stage = "OPEN_PROFILE"; goto done; }
            opened = 1;
            printf("BTSTACK_OPENED_PROFILE=%s\n", strict ? "strict-17" : "reference-17-len16");
            break;
        }
        if (!opened) { stage = "OPEN_TIMEOUT"; goto done; }
    }
    stage = "SYNTHETIC_SEND";
    if (send_btstack_packet(fd, 7, cid, payload, sizeof(payload) - 1, now_ms() + 4000, run_dir)) goto done;
    stage = "SYNTHETIC_ECHO";
    {
        int64_t deadline = now_ms() + 10000;
#ifdef OPENHC_TRANSPORT_TEST_TIMEOUTS
        deadline = now_ms() + 150;
#endif
#ifdef OPENHC_TRANSPORT_TEST_HEARTBEAT
        deadline = now_ms() + 4000;
#endif
        int echoed = 0;
        for (unsigned n = 0; n < 256; ++n) {
            int received = receive_transport_packet(fd, cid, &packet_type, &channel, body, &size, deadline, run_dir);
            if (received) {
                stage = received == -1 ? "ECHO_TIMEOUT_OR_IO" : "ECHO_EVENT_REJECTED";
                goto done;
            }
            if (packet_type == 4) {
                if (body[0] == 0x81 && le16(body + 2) == cid) { stage = "CLOSED_EARLY"; goto done; }
                continue;
            }
            if (size != sizeof(payload) - 1 || memcmp(body, payload, size)) { stage = "ECHO_MISMATCH"; goto done; }
            echoed = 1;
            break;
        }
        if (!echoed) { stage = "ECHO_TIMEOUT"; goto done; }
    }
    puts("BTSTACK_SYNTHETIC_CONTROL_ECHO_OK");
    result = 0;
    stage = "CLOSE";
done:
    if (fd >= 0 && cid) {
        uint8_t disconnect[] = {(uint8_t)cid, (uint8_t)(cid >> 8), 0};
        if (command(fd, 0x41, disconnect, sizeof(disconnect), now_ms() + 3000) == 0) {
            int64_t deadline = now_ms() + 5000;
#ifdef OPENHC_TRANSPORT_TEST_TIMEOUTS
            deadline = now_ms() + 150;
#endif
            for (unsigned n = 0; n < 128; ++n) {
                if (receive_transport_packet(fd, cid, &packet_type, &channel, body, &size, deadline, run_dir)) break;
                if (packet_type == 4 && body[0] == 0x81 && le16(body + 2) == cid) {
                    disconnected = 1;
                    break;
                }
            }
        }
        if (!disconnected) { result = 1; stage = "CLOSE_UNCONFIRMED"; }
    }
    if (fd >= 0) close(fd); /* Daemon client teardown is the fallback owner cleanup. */
    if (result) printf("BTSTACK_SYNTHETIC_CONTROL_FAILED=%s\n", stage);
    else if (disconnected) puts("BTSTACK_RFCOMM_CLOSE_CONFIRMED");
    return result;
}

static int query(int fd, uint8_t ocf, uint8_t expected, uint8_t *reply, unsigned size) {
    return exchange(fd, ocf, NULL, 0, expected, reply, size);
}

static int connect_daemon(const char *path) {
    int fd = -1;
#ifdef OPENHC_FE35_SIMULATOR_TEST
    if (strncmp(path, "tcp:", 4) == 0) {
        char *end = NULL;
        long port = strtol(path + 4, &end, 10);
        if (!end || *end || port < 1 || port > 65535) return -1;
        struct sockaddr_in tcp_addr;
        memset(&tcp_addr, 0, sizeof(tcp_addr));
        tcp_addr.sin_family = AF_INET;
        tcp_addr.sin_port = htons((uint16_t)port);
        tcp_addr.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
        fd = socket(AF_INET, SOCK_STREAM, 0);
        if (fd < 0) return -1;
        int one = 1;
        if (setsockopt(fd, SOL_SOCKET, SO_NOSIGPIPE, &one, sizeof(one))) goto tcp_failed;
        if (fcntl(fd, F_SETFL, O_NONBLOCK) < 0) goto tcp_failed;
        if (connect(fd, (struct sockaddr *)&tcp_addr, sizeof(tcp_addr)) != 0) {
            if (errno != EINPROGRESS) goto tcp_failed;
            struct pollfd p = {fd, POLLOUT, 0};
            if (poll(&p, 1, 2000) <= 0 || !(p.revents & POLLOUT)) goto tcp_failed;
            int error = 0;
            socklen_t error_size = sizeof(error);
            if (getsockopt(fd, SOL_SOCKET, SO_ERROR, &error, &error_size) || error) goto tcp_failed;
        }
        return fd;
tcp_failed:
        close(fd);
        return -1;
    }
#endif
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

static size_t service_record_uuid128(uint8_t *out, const uint8_t uuid[16], uint8_t channel) {
    uint8_t record[] = {
        0x35, 47,
        0x09, 0, 1, 0x35, 17, 0x1c,
        0, 0, 0, 0, 0, 0, 0x10, 0, 0x80, 0, 0, 0x80, 0x5f, 0x9b, 0x34, 0xfb,
        0x09, 0, 4, 0x35, 12,
        0x35, 3, 0x19, 1, 0, 0x35, 5, 0x19, 0, 3, 0x08, channel,
        0x09, 0, 5, 0x35, 3, 0x19, 0x10, 2
    };
    memcpy(record + 8, uuid, 16);
    memcpy(out, record, sizeof(record));
    return sizeof(record);
}

static int open_auth_listener(int fd, const uint8_t uuid[16], uint8_t *channel_out,
                              uint32_t *handle_out) {
    uint8_t reply[7];
    for (uint8_t channel = 16; channel <= 23; ++channel) {
        uint8_t params[] = {channel, 0, 2};
        if (exchange(fd, 0x42, params, sizeof(params), 0x85, reply, 4) || reply[3] != channel) return -1;
        if (reply[2] == 0) {
            *channel_out = channel;
            break;
        }
        if (reply[2] != 0x71) return -1;
    }
    if (!*channel_out) return -1;
    uint8_t record[64];
    size_t record_size = service_record_uuid128(record, uuid, *channel_out);
    if (exchange(fd, 0x30, record, record_size, 0x90, reply, 7) || reply[2]) return -1;
    *handle_out = le32(reply + 3);
    return *handle_out >= 0x10000 ? 0 : -1;
}

static int close_auth_listener(int fd, uint8_t channel, uint32_t handle) {
    int64_t deadline = now_ms() + 4000;
    if (handle) {
        uint8_t params[] = {(uint8_t)handle, (uint8_t)(handle >> 8),
                            (uint8_t)(handle >> 16), (uint8_t)(handle >> 24)};
        if (command(fd, 0x31, params, sizeof(params), deadline)) return -1;
    }
    if (channel) {
        uint8_t params[] = {channel, 0};
        if (command(fd, 0x43, params, sizeof(params), deadline)) return -1;
    }
    if (channel || handle) {
        uint8_t barrier[3];
        if (query(fd, 1, 0x60, barrier, sizeof(barrier))) return -1;
    }
    return 0;
}

static int dispatch_bridge_batch(int fd, uint16_t cid, fe35_bridge_handle bridge,
                                 fe35_bridge_batch batch, uint8_t *auth_channel,
                                 uint32_t *auth_handle, uint8_t auth_uuid[16],
                                 int64_t deadline, const char *run_dir) {
    size_t count = fe35_bridge_event_count(batch);
    int result = 0;
    if (count > FE35_BRIDGE_MAX_EVENTS) result = -1;
    for (size_t i = 0; !result && i < count; ++i) {
        fe35_bridge_event event;
        if (fe35_bridge_copy_event(batch, i, &event)) { result = -1; break; }
        if (strcmp(event.kind, "SEND_FRAME") == 0) {
            if (!event.frame_size || event.frame_size > FE35_BRIDGE_MAX_FRAME) result = -1;
            for (size_t offset = 0; !result && offset < event.frame_size;) {
                size_t part = event.frame_size - offset;
                if (part > 512) part = 512;
                if (send_btstack_packet(fd, 7, cid, event.frame + offset, part, deadline, run_dir)) result = -1;
                offset += part;
            }
        } else if (strcmp(event.kind, "OPEN_AUTH_LISTENER") == 0) {
            if (event.uuid_size != 16 || *auth_channel || *auth_handle) { result = -1; }
            else {
                memcpy(auth_uuid, event.uuid, 16);
                if (open_auth_listener(fd, auth_uuid, auth_channel, auth_handle)) result = -1;
                else {
                    fe35_bridge_batch ready = fe35_bridge_listener_ready(bridge, *auth_channel);
                    if (!ready) result = -1;
                    else {
                        result = dispatch_bridge_batch(fd, cid, bridge, ready, auth_channel,
                            auth_handle, auth_uuid, deadline, run_dir);
                        fe35_bridge_release_batch(ready);
                    }
                }
            }
        } else if (strcmp(event.kind, "CLOSE_AUTH_LISTENER") == 0) {
            if (close_auth_listener(fd, *auth_channel, *auth_handle)) result = -1;
            else { *auth_channel = 0; *auth_handle = 0; memset(auth_uuid, 0, 16); }
        } else if (strncmp(event.kind, "ERROR", 5) == 0 ||
                   strcmp(event.kind, "CONTROL_ABORTED") == 0 ||
                   strcmp(event.kind, "CLOSED") == 0) {
            result = -1;
        } else if (strcmp(event.kind, "HANDSHAKE_COMPLETED") != 0 &&
                   strcmp(event.kind, "IGNORED") != 0 &&
                   strcmp(event.kind, "INPUT_DISCARDED") != 0 &&
                   strcmp(event.kind, "SOCKET_REQUEST_REJECTED") != 0) {
            result = -1;
        }
        memset(&event, 0, sizeof(event));
    }
    return result;
}

/* Bounded FE35 control path: accept one RFCOMM stream, pass data through the
 * public Kotlin/Native bridge, then explicitly release owned services/CID.
 * Peer addresses, session bytes, UUIDs, and key material are never logged.
 */
static int transport_inbound(const char *path, const char *run_dir, fe35_bridge_handle bridge) {
    uint8_t state[3], reply[7], owned_channel = 0;
    uint32_t handle = 0;
    uint16_t cid = 0, packet_type = 0, packet_channel = 0;
    uint8_t body[1024], auth_channel = 0, auth_uuid[16] = {0};
    uint32_t auth_handle = 0;
    size_t size = 0;
    int fd = -1, result = 1, accepted = 0, opened = 0, disconnected = 0;
    int listener_ready = 0, session_started = 0;
    unsigned status = 0;
    const char *stage = "GUARD";
    if (guard_ready(run_dir) || !bridge) goto done;
    fd = connect_daemon(path);
    if (fd < 0) { stage = "CONNECT"; goto done; }
    stage = "STATE";
    if (query(fd, 1, 0x60, state, sizeof(state)) || state[2] != 2) goto done;

    stage = "RFCOMM_LISTEN";
    for (uint8_t channel = 16; channel <= 23; ++channel) {
        uint8_t params[] = {channel, 0, 2};
        if (exchange(fd, 0x42, params, sizeof(params), 0x85, reply, 4)) goto done;
        status = reply[2];
        if (reply[3] != channel) goto done;
        if (status == 0) { owned_channel = channel; break; }
        if (status != 0x71) goto done;
    }
    if (!owned_channel) { stage = "RFCOMM_CHANNELS_BUSY"; goto done; }

    stage = "FE35_SDP";
    {
        uint8_t record[64];
        size_t record_size = service_record(record, 0xfe35, owned_channel);
        if (exchange(fd, 0x30, record, record_size, 0x90, reply, 7)) goto done;
        status = reply[2];
        handle = le32(reply + 3);
        if (status || handle < 0x10000) goto done;
    }

    stage = "INCOMING_TIMEOUT";
    {
        int64_t deadline = now_ms() + 25000;
#ifdef OPENHC_TRANSPORT_TEST_TIMEOUTS
        deadline = now_ms() + 150;
#endif
        int found = 0;
        for (unsigned n = 0; n < 64; ++n) {
            int received = receive_transport_packet(fd, 0, &packet_type, &packet_channel,
                                                    body, &size, deadline, run_dir);
            if (received) { if (received == -2) stage = "INCOMING_EVENT_REJECTED"; goto done; }
            if (packet_type != 4 || body[0] != 0x82) continue;
            if (size != 11 || body[8] != owned_channel) { stage = "INCOMING_EVENT_SHAPE"; goto done; }
            cid = (uint16_t)le16(body + 9);
            if (!cid) { stage = "INCOMING_CID_INVALID"; goto done; }
            found = 1;
            break;
        }
        if (!found) goto done;
    }

    stage = "RFCOMM_ACCEPT";
    {
        uint8_t params[] = {(uint8_t)cid, (uint8_t)(cid >> 8)};
        if (command(fd, 0x44, params, sizeof(params), now_ms() + 4000)) goto done;
        accepted = 1;
    }
    stage = "INCOMING_OPEN";
    {
        int64_t deadline = now_ms() + 10000;
#ifdef OPENHC_TRANSPORT_TEST_TIMEOUTS
        deadline = now_ms() + 150;
#endif
        int found = 0;
        for (unsigned n = 0; n < 64; ++n) {
            int received = receive_transport_packet(fd, 0, &packet_type, &packet_channel,
                                                    body, &size, deadline, run_dir);
            if (received) { if (received == -2) stage = "OPEN_EVENT_REJECTED"; goto done; }
            if (packet_type != 4 || body[0] != 0x80) continue;
            if (size == 16 && body[2] != 0) { stage = "ACCEPT_FAILED"; goto done; }
            int strict = size == 17 && body[1] == 15;
            int reference = size == 17 && body[1] == 16;
            if ((!strict && !reference) || body[2] || body[11] != owned_channel ||
                le16(body + 12) != cid || body[16] != 1) {
                stage = "INCOMING_OPEN_PROFILE";
                goto done;
            }
            found = opened = 1;
            printf("BTSTACK_FE35_INCOMING_OPENED_PROFILE=%s\n",
                   strict ? "strict-17" : "reference-17-len16");
            break;
        }
        if (!found) goto done;
    }

    stage = "BRIDGE_START";
    {
        fe35_bridge_batch batch = fe35_bridge_start(bridge, now_ms());
        if (!batch) goto done;
        session_started = 1;
        int64_t deadline = now_ms() + 4000;
        int dispatched = dispatch_bridge_batch(fd, cid, bridge, batch, &auth_channel,
            &auth_handle, auth_uuid, deadline, run_dir);
        fe35_bridge_release_batch(batch);
        if (dispatched) goto done;
    }

    stage = "CONTROL_STREAM";
    {
        int64_t session_deadline = now_ms() + 30000;
#ifdef OPENHC_TRANSPORT_TEST_TIMEOUTS
        session_deadline = now_ms() + 2500;
#endif
        for (unsigned n = 0; n < 512 && now_ms() < session_deadline; ++n) {
            int64_t receive_deadline = now_ms() + 1000;
            if (receive_deadline > session_deadline) receive_deadline = session_deadline;
            int received = receive_transport_packet(fd, cid, &packet_type, &packet_channel,
                                                    body, &size, receive_deadline, run_dir);
            if (received == -1) {
                fe35_bridge_batch tick = fe35_bridge_tick(bridge, now_ms());
                if (!tick) { stage = "BRIDGE_TICK_FAILED"; goto done; }
                int timed_out = 0;
                for (size_t i = 0; i < fe35_bridge_event_count(tick); ++i) {
                    fe35_bridge_event event;
                    if (fe35_bridge_copy_event(tick, i, &event)) { timed_out = 1; break; }
                    if (strcmp(event.kind, "HANDSHAKE_TIMED_OUT") == 0) timed_out = 1;
                    memset(&event, 0, sizeof(event));
                }
                fe35_bridge_release_batch(tick);
                if (timed_out) { stage = "HANDSHAKE_TIMEOUT"; goto done; }
                continue;
            }
            if (received) { stage = received == -2 ? "CONTROL_PACKET_REJECTED" : "CONTROL_IO"; goto done; }
            if (packet_type == 4 && body[0] == 0x81 && le16(body + 2) == cid) {
                disconnected = 1;
                break;
            }
            if (packet_type != 7 || packet_channel != cid) { stage = "CONTROL_PACKET_SHAPE"; goto done; }
            fe35_bridge_batch batch = fe35_bridge_feed(bridge, body, size);
            if (!batch) { stage = "BRIDGE_FEED_FAILED"; goto done; }
            for (size_t i = 0; i < fe35_bridge_event_count(batch); ++i) {
                fe35_bridge_event event;
                if (fe35_bridge_copy_event(batch, i, &event)) { stage = "BRIDGE_EVENT_INVALID"; result = 1; break; }
                if (strcmp(event.kind, "HANDSHAKE_COMPLETED") == 0) listener_ready = 1;
                if (strcmp(event.kind, "OPEN_AUTH_LISTENER") == 0) listener_ready = 0;
                memset(&event, 0, sizeof(event));
            }
            if (strcmp(stage, "BRIDGE_EVENT_INVALID") == 0) { fe35_bridge_release_batch(batch); goto done; }
            int dispatched = dispatch_bridge_batch(fd, cid, bridge, batch, &auth_channel,
                &auth_handle, auth_uuid, now_ms() + 4000, run_dir);
            fe35_bridge_release_batch(batch);
            if (dispatched) { stage = "BRIDGE_EVENT_DISPATCH"; goto done; }
            if (auth_channel) listener_ready = 1;
        }
    }
    if (session_started && listener_ready) {
        result = 0;
    } else stage = disconnected ? "CONTROL_DISCONNECTED_EARLY" : "SESSION_DEADLINE";
done:
    if (fd >= 0) {
        int cleanup_ok = 1;
        int64_t deadline = now_ms() + 4000;
        if (auth_channel || auth_handle) {
            if (close_auth_listener(fd, auth_channel, auth_handle)) cleanup_ok = 0;
            auth_channel = 0;
            auth_handle = 0;
        }
        if (opened && cid) {
            uint8_t params[] = {(uint8_t)cid, (uint8_t)(cid >> 8), 0};
            if (command(fd, 0x41, params, sizeof(params), deadline)) cleanup_ok = 0;
            else {
                int64_t close_deadline = now_ms() + 5000;
#ifdef OPENHC_TRANSPORT_TEST_TIMEOUTS
                close_deadline = now_ms() + 150;
#endif
                int confirmed = 0;
                for (unsigned i = 0; i < 64; ++i) {
                    if (receive_transport_packet(fd, cid, &packet_type, &packet_channel,
                                                 body, &size, close_deadline, run_dir)) break;
                    if (packet_type == 4 && body[0] == 0x81 && le16(body + 2) == cid) {
                        confirmed = 1;
                        break;
                    }
                }
                if (!confirmed) cleanup_ok = 0;
                else disconnected = 1;
            }
        }
        if (handle) {
            uint8_t params[] = {(uint8_t)handle, (uint8_t)(handle >> 8),
                                (uint8_t)(handle >> 16), (uint8_t)(handle >> 24)};
            if (command(fd, 0x31, params, sizeof(params), deadline)) cleanup_ok = 0;
        }
        if (owned_channel) {
            uint8_t params[] = {owned_channel, 0};
            if (command(fd, 0x43, params, sizeof(params), deadline)) cleanup_ok = 0;
        }
        if (handle || owned_channel) {
            uint8_t barrier[3];
            if (query(fd, 1, 0x60, barrier, sizeof(barrier))) cleanup_ok = 0;
        }
        if (!cleanup_ok) { result = 1; stage = "CLEANUP_UNCONFIRMED"; }
        close(fd); /* daemon client teardown also releases any pending CID */
    }
    if (result) printf("BTSTACK_FE35_INBOUND_FAILED=%s\n", stage);
    else {
        puts("BTSTACK_FE35_BRIDGE_SESSION_OK");
        if (disconnected) puts("BTSTACK_FE35_DISCONNECT_CONFIRMED");
    }
    if (bridge) fe35_bridge_close(bridge);
    (void)accepted;
    return result;
}

static int inbound_with_bridge(const char *path, const char *run_dir) {
    fe35_bridge_input input;
    if (guard_ready(run_dir)) {
        puts("BTSTACK_FE35_INBOUND_FAILED=GUARD");
        return 1;
    }
    if (read_bridge_input(&input)) {
        memset(&input, 0, sizeof(input));
        puts("BTSTACK_FE35_INBOUND_FAILED=BRIDGE_INPUT");
        return 1;
    }
    fe35_bridge_handle bridge = fe35_bridge_create(&input);
    memset(&input, 0, sizeof(input));
    if (!bridge) {
        puts("BTSTACK_FE35_INBOUND_FAILED=BRIDGE_CREATE");
        return 1;
    }
    return transport_inbound(path, run_dir, bridge);
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
    if (argc == 4 && strcmp(argv[2], "--btstack-control-inbound") == 0)
        return inbound_with_bridge(argv[1], argv[3]);
    if (argc == 7 && strcmp(argv[2], "--transport") == 0) {
        char *end = NULL;
        unsigned long channel = strtoul(argv[4], &end, 10);
        if (!end || *end) return 2;
        return transport_synthetic(argv[1], argv[3], (unsigned)channel, argv[5], argv[6]);
    }
    return 2;
}
#else
int openhc_btstack_control_synthetic(const char *address, unsigned channel,
                                     const char *profile, const char *run_dir) {
    return transport_synthetic("/tmp/BTstack", address, channel, profile, run_dir);
}
int openhc_btstack_control_inbound(const char *run_dir) {
#ifdef OPENHC_FE35_SIMULATOR_TEST
    const char *path = getenv("OPENHC_FE35_TEST_SOCKET");
    if (!path || !*path) path = "/tmp/BTstack";
    return inbound_with_bridge(path, run_dir);
#else
    return inbound_with_bridge("/tmp/BTstack", run_dir);
#endif
}
#endif
