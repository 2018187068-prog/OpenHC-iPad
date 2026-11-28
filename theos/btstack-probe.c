/* Bounded BTstack daemon query/local-service probes. Wire format checked against Showcase
 * ce9d1d50758f67307deb3f00c901a8e82894930c:
 * platform/daemon/src/{socket_connection.c,daemon.c}, src/btstack_defines.h.
 * No BTstack implementation code is copied. No power/discovery commands sent.
 */
/* Strict C11 on glibc hides POSIX time declarations without this request.
 * Darwin retains its existing SDK feature visibility and socket option. */
#if defined(__linux__) && !defined(_POSIX_C_SOURCE)
#define _POSIX_C_SOURCE 200809L
#endif
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
static int guard_ready(const char *run_dir);
static int receive_transport_packet(int fd, uint16_t expected_cid, uint16_t *type,
                                    uint16_t *channel, uint8_t *body, size_t *size,
                                    int64_t deadline, const char *run_dir);
static int transfer_guarded(int fd, uint8_t *buf, size_t size, int sending,
                            int64_t deadline, const char *run_dir);

/* Per-thread scoped binding: cancellation/deadline also interrupt fragmented
 * registration replies. Cleared before cleanup so Stop cannot cancel teardown. */
static _Thread_local fe35_scan_transport *current_scan;
static _Thread_local int scan_ended;
static _Thread_local int auth_strict_exchange;

/* Darwin suppresses SIGPIPE per socket; Linux requires MSG_NOSIGNAL on
 * every send. Never change the process-wide SIGPIPE disposition. */
static int protect_socket_sigpipe(int fd) {
#if defined(__APPLE__)
    int one = 1;
    return setsockopt(fd, SOL_SOCKET, SO_NOSIGPIPE, &one, sizeof(one));
#elif defined(__linux__)
    (void)fd;
    return 0; /* Both send paths below use MSG_NOSIGNAL. */
#else
#error Unsupported socket SIGPIPE protection platform
#endif
}

static ssize_t send_without_sigpipe(int fd, const void *buffer, size_t size) {
#if defined(__linux__)
    return send(fd, buffer, size, MSG_NOSIGNAL);
#else
    return send(fd, buffer, size, 0);
#endif
}

static int scan_event(const char *kind, int channel) {
    if (!current_scan || scan_ended) return scan_ended ? -1 : 0;
    int result = current_scan->notify(current_scan->context, current_scan->generation,
                                       kind, channel, now_ms());
    if (result) scan_ended = 1;
    return result ? -1 : 0;
}

static int scan_poll(void) {
    if (!current_scan) return 0;
    if (scan_ended) return -1;
    if (current_scan->stop_fd >= 0) {
        struct pollfd stop = {current_scan->stop_fd, POLLIN, 0};
        int result = poll(&stop, 1, 0);
        if (result < 0 && errno != EINTR) return scan_event("FAILED", 0), -1;
        if (result > 0) return scan_event("STOP", 0), -1;
    }
    return scan_event("TICK", 0);
}

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
        if (scan_poll()) return -1;
        int64_t now = now_ms();
        if (now < 0 || now >= deadline) return -1;
        struct pollfd p = {fd, events, 0};
        int wait = (int)(deadline - now);
        if (current_scan && wait > 20) wait = 20;
        int r = poll(&p, 1, wait);
        if (r < 0 && errno == EINTR) continue;
        if (r == 0 && current_scan) continue;
        if (scan_poll()) return -1;
        return r > 0 && (p.revents & events) ? 0 : -1;
    }
}

static int transfer(int fd, uint8_t *buf, size_t size, int sending, int64_t deadline) {
    while (size) {
        if (ready(fd, sending ? POLLOUT : POLLIN, deadline) != 0) return -1;
        ssize_t n = sending ? send_without_sigpipe(fd, buf, size) : recv(fd, buf, size, 0);
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
        if (le16(header) != 4) { if (auth_strict_exchange) return -1; continue; }
        if (size < 2 || body[1] != size - 2) return -1;
        if (body[0] != expected) { if (auth_strict_exchange) return -1; continue; }
        if (le16(header + 2) != 0 || size != expected_size) return -1;
        memcpy(reply, body, size);
        return 0;
    }
    return -1;
}

/* Read the controller's own public address while WORKING. The daemon routes
 * ordinary HCI command-complete events to all clients; never print the result.
 */
static int local_bd_addr(const char *path, const char *run_dir, uint8_t address[6]) {
    uint8_t state[3], request[] = {1, 0, 0, 0, 3, 0, 0x09, 0x10, 0};
    int fd = -1, result = -1;
    int64_t start = now_ms();
    if (start < 0 || guard_ready(run_dir)) return -1;
    int64_t deadline = start + 4000;
#ifdef OPENHC_TRANSPORT_TEST_TIMEOUTS
    deadline = start + 150;
#endif
    fd = connect_daemon(path);
    if (fd < 0) goto done;
    if (query(fd, 1, 0x60, state, sizeof(state)) || state[2] != 2) goto done;
    if (transfer_guarded(fd, request, sizeof(request), 1, deadline, run_dir)) goto done;
    for (unsigned i = 0; i < 32; ++i) {
        uint8_t header[6];
        uint16_t type, channel, packet_size;
        uint8_t body[1024];
        if (transfer_guarded(fd, header, sizeof(header), 0, deadline, run_dir)) goto done;
        type = (uint16_t)le16(header);
        channel = (uint16_t)le16(header + 2);
        packet_size = (uint16_t)le16(header + 4);
        if (packet_size > sizeof(body) ||
            transfer_guarded(fd, body, packet_size, 0, deadline, run_dir)) goto done;
        if (type != 4 || channel != 0 || packet_size < 2 || body[0] != 0x0e) continue;
        if (packet_size != 12 || body[1] != 10 || le16(body + 3) != 0x1009 || body[5]) goto done;
        for (unsigned j = 0; j < 6; ++j) address[j] = body[11 - j];
        if (!memcmp(address, "\0\0\0\0\0\0", 6) ||
            !memcmp(address, "\xff\xff\xff\xff\xff\xff", 6)) goto done;
        result = 0;
        break;
    }
done:
    if (fd >= 0) close(fd);
    return result ? 1 : 0;
}

static int transport_local_address(const char *path, const char *run_dir) {
    uint8_t address[6] = {0};
    int result = local_bd_addr(path, run_dir, address);
    if (!result && fwrite(address, 1, sizeof(address), stdout) != sizeof(address)) result = -1;
    memset(address, 0, sizeof(address));
    return result;
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
        if (scan_poll()) return -1;
        int64_t now = now_ms();
        if (now < 0 || now >= deadline) return -1;
        int64_t slice = now + (current_scan ? 20 : 2000);
        if (slice > deadline) slice = deadline;
        struct pollfd p = {fd, sending ? POLLOUT : POLLIN, 0};
        int r = poll(&p, 1, (int)(slice - now));
        if (r < 0 && errno == EINTR) continue;
        if (r == 0) continue;
        if (scan_poll()) return -1;
        if (r < 0 || !(p.revents & (sending ? POLLOUT : POLLIN))) return -1;
        ssize_t n = sending ? send_without_sigpipe(fd, buf, size) : recv(fd, buf, size, 0);
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
        if ((expected_cid != UINT16_MAX && *channel != expected_cid) || !*channel || *size > 512) return -2;
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
        /* Private peer correlation only. Neither these addresses nor data are
         * printed. Both incoming/open BTstack events use reversed BD_ADDR. */
        if (transfer_guarded(fd, body + 2, *size - 2, 0, deadline, run_dir)) {
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
        if (protect_socket_sigpipe(fd)) goto tcp_failed;
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
    if (protect_socket_sigpipe(fd)) goto failed;
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

static int dispatch_bridge_batch(int fd, uint16_t cid, uint16_t mtu, fe35_bridge_handle bridge,
                                 fe35_bridge_batch batch, uint8_t *auth_channel,
                                 uint32_t *auth_handle, uint8_t auth_uuid[16],
                                 int64_t deadline, const char *run_dir) {
    size_t count = fe35_bridge_event_count(batch);
    int result = (!mtu || mtu>512) ? -1 : 0;
    if (count > FE35_BRIDGE_MAX_EVENTS) result = -1;
    for (size_t i = 0; !result && i < count; ++i) {
        fe35_bridge_event event;
        if (fe35_bridge_copy_event(batch, i, &event)) { result = -1; break; }
        if (strcmp(event.kind, "SEND_FRAME") == 0) {
            if (!event.frame_size || event.frame_size > FE35_BRIDGE_MAX_FRAME) result = -1;
            for (size_t offset = 0; !result && offset < event.frame_size;) {
                size_t part = event.frame_size - offset;
                if (part > mtu) part = mtu;
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
                        result = dispatch_bridge_batch(fd, cid, mtu, bridge, ready, auth_channel,
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
typedef struct {
    int fd; uint16_t cid, mtu; int64_t deadline; const char *run_dir;
} auth_writer;
static int auth_send(void *context,const uint8_t *bytes,size_t size) {
    auth_writer *w=context;
    if(!bytes || !size || size>4096 || !w->cid || !w->mtu || w->mtu>512) return -1;
    for(size_t at=0;at<size;) {
        size_t n=size-at; if(n>w->mtu) n=w->mtu;
        if(scan_poll() || send_btstack_packet(w->fd,7,w->cid,bytes+at,n,w->deadline,w->run_dir)) return -1;
        at+=n;
    }
    return scan_poll();
}
/* No packet=JSON assumption: every byte is copied into the Native framer. A
 * single accepted incarnation (1) is scoped to this stack invocation and
 * captured common generation; reusable daemon CIDs are never authority. */
static int auth_stream(int fd,const char *run_dir,fe36_auth_transport *auth,
    fe35_bridge_handle bridge,uint16_t control_cid,uint16_t control_mtu,uint8_t *listener,uint32_t *listener_handle,
    uint8_t uuid[16],const uint8_t peer[6],uint16_t acl,
    uint16_t *auth_cid,int *auth_opened,int *auth_disconnected,int *control_disconnected,int *uncertain) {
    uint8_t body[1024]; uint16_t type,channel,mtu=0; size_t size;
    int connected=0; int64_t start=now_ms(),last=start,deadline=start+30000;
#ifdef OPENHC_TRANSPORT_TEST_TIMEOUTS
    deadline=start+2500;
#endif
    auth_writer writer={fd,0,0,deadline,run_dir};
    for(unsigned packets=0;packets<4096;packets++) {
        int64_t now=now_ms();
        if(now<last || now>=deadline || scan_poll()) return -1;
        last=now;
        if(connected && auth->step(auth->context,FE36_IO_TICK,1,NULL,0,now,auth_send,&writer)<0) return -1;
        if(receive_transport_packet(fd,UINT16_MAX,&type,&channel,body,&size,deadline,run_dir)) return -1;
        if(type==4) {
            if(body[0]==0x82) {
                /* Unknown/duplicate/control-CID reuse/other peer never accepted. */
                uint16_t candidate=(uint16_t)le16(body+9);
                if(*auth_cid || body[8]!=*listener || !candidate || candidate==control_cid ||
                    memcmp(body+2,peer,6)) { *uncertain=1; return -1; }
                *auth_cid=candidate;
                uint8_t params[]={(uint8_t)candidate,(uint8_t)(candidate>>8)};
                if(command(fd,0x44,params,sizeof(params),deadline)) return -1;
            } else if(body[0]==0x80) {
                if(connected || (size==17 && (!*auth_cid || le16(body+12)!=*auth_cid))) *uncertain=1;
                if(!*auth_cid || connected || size!=17 || body[2] || body[11]!=*listener ||
                    le16(body+12)!=*auth_cid || body[16]!=1 || memcmp(body+3,peer,6) ||
                    le16(body+9)!=acl || !(mtu=(uint16_t)le16(body+14)) || mtu>512) return -1;
                *auth_opened=connected=1; writer.cid=*auth_cid; writer.mtu=mtu;
                if(auth->step(auth->context,FE36_IO_CONNECTED,1,NULL,0,now_ms(),auth_send,&writer)) return -1;
            } else if(body[0]==0x81) {
                if(le16(body+2)!=control_cid && (!*auth_cid || le16(body+2)!=*auth_cid)) *uncertain=1;
                if(le16(body+2)==control_cid) *control_disconnected=1;
                if(*auth_cid && le16(body+2)==*auth_cid) *auth_disconnected=1;
                /* Reference WirelessReceiverSession: before WiFi, FE35 close is
                 * fatal even during authentication. This slice has no WiFi. */
                return -1;
            } else return -1;
        } else {
            if(channel==control_cid) {
                fe35_bridge_batch batch=fe35_bridge_feed(bridge,body,size);
                if(!batch) return -1;
                int failed=dispatch_bridge_batch(fd,control_cid,control_mtu,bridge,batch,listener,
                    listener_handle,uuid,deadline,run_dir);
                fe35_bridge_release_batch(batch);memset(body,0,sizeof(body));
                if(failed) *uncertain=1;
                if(failed || !*listener) return -1;
                continue;
            }
            if(!connected || channel!=*auth_cid || !size || size>mtu) {
                if(channel!=*auth_cid) *uncertain=1;
                return -1;
            }
            int step=auth->step(auth->context,FE36_IO_DATA,1,body,size,now_ms(),auth_send,&writer);
            memset(body,0,sizeof(body));
            if(step<0 || scan_poll()) return -1;
            if(step==1) return 0;
        }
    }
    return -1;
}
/* All effects stay on the existing synchronous transport worker. Provider only supplies an
 * already owned listener/config; no radio configuration or detached lease is introduced. */
static int wifi_batch(int fd,uint16_t cid,uint16_t mtu,fe35_bridge_batch batch,
                       int *listen_requested,int *wait_tcp,int *accepted,int64_t deadline,const char *dir) {
    if(!batch) return -1;
    int failed=0;size_t count=fe35_bridge_event_count(batch);
    if(count>FE35_BRIDGE_MAX_EVENTS) failed=1;
    for(size_t i=0;!failed && i<count;i++) {
        fe35_bridge_event e;
        if(fe35_bridge_copy_event(batch,i,&e)) {failed=1;break;}
        if(!strcmp(e.kind,"SEND_FRAME")) {
            if(!e.frame_size || e.frame_size>FE35_BRIDGE_MAX_FRAME) failed=1;
            for(size_t at=0;!failed && at<e.frame_size;) {
                size_t n=e.frame_size-at;if(n>mtu)n=mtu;
                if(scan_poll() || send_btstack_packet(fd,7,cid,e.frame+at,n,deadline,dir)) failed=1;
                at+=n;
            }
        } else if(!strcmp(e.kind,"WIFI_LISTEN")) *listen_requested=1;
        else if(!strcmp(e.kind,"WIFI_WAIT_TCP")) *wait_tcp=1;
        else if(!strcmp(e.kind,"TCP_CONTROL_ACCEPTED")) *accepted=1;
        else if(!strcmp(e.kind,"WIFI_NETWORK_REQUESTED")) {
#ifdef OPENHC_FE35_SIMULATOR_TEST
            puts("BTSTACK_WIFI_NETWORK_PENDING");fflush(stdout);
#endif
        } else if(strcmp(e.kind,"IGNORED_FRAME")) failed=1;
        memset(&e,0,sizeof(e));
    }
    fe35_bridge_release_batch(batch);return failed?-1:0;
}
/* Owned TCP stays on this worker and uses the existing owner poll, not a fresh lease.
 * Batches are fully bounded; all writes handle partial progress/EAGAIN and cancellation. */
static int tcp_control_batch(int tcp,fe35_bridge_batch batch,int *ended) {
    if(!batch) return -1;
    int failed=0;size_t count=fe35_bridge_event_count(batch);
    if(count>FE35_BRIDGE_MAX_EVENTS) failed=1;
    for(size_t i=0;!failed && i<count;i++) {
        fe35_bridge_event e;
        if(fe35_bridge_copy_event(batch,i,&e)) {failed=1;break;}
        if(!strcmp(e.kind,"SEND_FRAME")) {
            if(!e.frame_size || e.frame_size>FE35_BRIDGE_MAX_FRAME) failed=1;
            for(size_t at=0;!failed && at<e.frame_size;) {
                if(scan_poll()) {failed=1;break;}
                struct pollfd p={tcp,POLLOUT,0};int ready=poll(&p,1,20);
                if(ready<0) {if(errno==EINTR)continue;failed=1;break;}
                if(!ready) continue;
                if(!(p.revents&POLLOUT) || (p.revents&(POLLERR|POLLHUP|POLLNVAL))) {failed=1;break;}
                ssize_t n=send_without_sigpipe(tcp,e.frame+at,e.frame_size-at);
                if(n<0 && (errno==EINTR || errno==EAGAIN || errno==EWOULDBLOCK)) continue;
                if(n<=0) {failed=1;break;}
                at+=(size_t)n;
            }
        } else if(!strcmp(e.kind,"TCP_DISCONNECT")) *ended=1;
        else if(strcmp(e.kind,"HANDSHAKE_COMPLETED") && strcmp(e.kind,"SOCKET_REQUEST_REJECTED") &&
                strcmp(e.kind,"IGNORED_FRAME")) failed=1;
        memset(&e,0,sizeof(e));
    }
    fe35_bridge_release_batch(batch);return failed?-1:0;
}
static int tcp_control_stream(int fd,int tcp,const char *dir,fe35_wifi_transport *wifi,
                              uint16_t cid,int *disconnected,int *settled,int *uncertain) {
    int ended=0;
    if(scan_poll() || tcp_control_batch(tcp,wifi->tcp_step(wifi->context,tcp,NULL,0,now_ms()),&ended)) return -1;
#ifdef OPENHC_FE35_SIMULATOR_TEST
    puts("BTSTACK_WIFI_LIVE_CONTROL_STARTED");fflush(stdout);
#endif
    for(;;) {
        if(scan_poll()) return -1;
        if(tcp_control_batch(tcp,wifi->tcp_step(wifi->context,tcp,NULL,0,now_ms()),&ended)) return -1;
        struct pollfd p[2]={{fd,POLLIN,0},{tcp,POLLIN,0}};
        int ready=poll(p,2,20);if(ready<0) {if(errno==EINTR)continue;return -1;}
        /* The daemon and original owner still have priority over simultaneous TCP input. */
        if(p[0].revents) {
            uint8_t body[1024];uint16_t type,channel;size_t size;
            if(receive_transport_packet(fd,UINT16_MAX,&type,&channel,body,&size,now_ms()+4000,dir)) {
                *uncertain=1;return -1;
            }
            /* Pinned WirelessReceiverSession: remote FE35 close after phoneOnWifi is
             * settled. Keep TCP and lease; do not proactively close FE35 on join. */
            if(type==4 && channel==0 && size==4 && body[0]==0x81 && le16(body+2)==cid && !*disconnected) {
                *disconnected=1;*settled=1;continue;
            }
            memset(body,0,sizeof(body));*uncertain=1;return -1;
        }
        if(p[1].revents) {
            if(scan_poll()) return -1;
            uint8_t body[4096];ssize_t n=recv(tcp,body,sizeof(body),0);
            if(n<0 && (errno==EINTR || errno==EAGAIN || errno==EWOULDBLOCK)) continue;
            if(n<=0) return -1; /* TCP peer death is terminal, not protocol success. */
            int failed=tcp_control_batch(tcp,wifi->tcp_step(wifi->context,tcp,body,(size_t)n,now_ms()),&ended);
            memset(body,0,sizeof(body));
            if(failed || scan_poll()) return -1;
            if(ended) return 0; /* ACK written before final close and typed cleanup. */
        }
    }
}
static int wifi_stream(int fd,const char *dir,fe35_bridge_handle bridge,fe35_wifi_transport *wifi,
                         uint16_t cid,uint16_t mtu,int *tcp,int *disconnected,int *settled,int *uncertain) {
    int listener=-1,wants_listen=0,wait_tcp=0,accepted=0,reported_listen=0;
    uint32_t peer=0;
    int64_t last=now_ms();
    if(wifi_batch(fd,cid,mtu,wifi->step(wifi->context,FE35_WIFI_BEGIN,bridge,last,-1,&listener,&peer),
        &wants_listen,&wait_tcp,&accepted,last+4000,dir)) return -1;
    for(unsigned iterations=0;iterations<20000;iterations++) {
        int64_t now=now_ms();
        if(now<last || scan_poll()) return -1;
        last=now;
        if(wifi_batch(fd,cid,mtu,fe35_bridge_tick(bridge,now),&wants_listen,&wait_tcp,&accepted,now+4000,dir)) return -1;
        if(wifi_batch(fd,cid,mtu,wifi->step(wifi->context,FE35_WIFI_NETWORK,bridge,now,-1,&listener,&peer),
            &wants_listen,&wait_tcp,&accepted,now+4000,dir)) return -1;
        if(wants_listen && !reported_listen) {
            reported_listen=1;
            if(wifi_batch(fd,cid,mtu,wifi->step(wifi->context,FE35_WIFI_LISTEN,bridge,now,-1,&listener,&peer),
                &wants_listen,&wait_tcp,&accepted,now+4000,dir)) return -1;
            if(listener<0) return -1;
        }
        struct pollfd p[2]={{fd,POLLIN,0},{wait_tcp?listener:-1,POLLIN,0}};
        int ready=poll(p,2,20);if(ready<0) {if(errno==EINTR)continue;return -1;}
        /* Bluetooth cancellation/EOF always wins over an accept ready in the same poll. */
        if(p[0].revents) {
            uint8_t body[1024];uint16_t type,channel;size_t size;
            if(receive_transport_packet(fd,UINT16_MAX,&type,&channel,body,&size,now+4000,dir)) return -1;
            if(type==4) {
                if(body[0]==0x81 && le16(body+2)==cid) *disconnected=1;
                else *uncertain=1;
                return -1; /* before accepted TCP, FE35 EOF is fatal */
            }
            if(type!=7 || channel!=cid || !size || size>mtu) {*uncertain=1;return -1;}
            fe35_bridge_batch batch=fe35_bridge_feed(bridge,body,size);memset(body,0,sizeof(body));
            if(wifi_batch(fd,cid,mtu,batch,&wants_listen,&wait_tcp,&accepted,now+4000,dir)) return -1;
            continue; /* re-poll original owner before accepting TCP */
        }
        if(p[1].revents) {
            if(!(p[1].revents&POLLIN) || scan_poll()) return -1;
            struct sockaddr_in address={0};socklen_t size=sizeof(address);
            *tcp=accept(listener,(struct sockaddr *)&address,&size);
            if(*tcp<0 || size!=sizeof(address) || address.sin_family!=AF_INET ||
               address.sin_addr.s_addr!=peer || fcntl(*tcp,F_SETFD,FD_CLOEXEC) ||
               fcntl(*tcp,F_SETFL,O_NONBLOCK) || scan_poll()) return -1;
            if(protect_socket_sigpipe(*tcp)) return -1;
            if(wifi_batch(fd,cid,mtu,wifi->step(wifi->context,FE35_WIFI_ACCEPT,bridge,now_ms(),*tcp,&listener,&peer),
                &wants_listen,&wait_tcp,&accepted,now+4000,dir) || !accepted || scan_poll()) return -1;
            return wifi->tcp_step ? tcp_control_stream(fd,*tcp,dir,wifi,cid,disconnected,settled,uncertain) : 0;
        }
    }
    return -1;
}
static const char *inbound_primary_stage(const char *stage) {
    /* Fixed labels only; never render transport bytes or exception text. */
    static const char *const labels[] = {
        "GUARD", "CONNECT", "STATE", "RFCOMM_LISTEN", "RFCOMM_CHANNELS_BUSY",
        "FE35_SDP", "INCOMING_TIMEOUT", "INCOMING_EVENT_REJECTED",
        "INCOMING_EVENT_SHAPE", "INCOMING_CID_INVALID", "RFCOMM_ACCEPT",
        "INCOMING_OPEN", "OPEN_EVENT_REJECTED", "ACCEPT_FAILED",
        "INCOMING_OPEN_PROFILE", "BRIDGE_START", "CONTROL_STREAM",
        "BRIDGE_TICK_FAILED", "HANDSHAKE_TIMEOUT", "CONTROL_PACKET_REJECTED",
        "CONTROL_IO", "CONTROL_PACKET_SHAPE", "BRIDGE_FEED_FAILED",
        "BRIDGE_EVENT_INVALID", "BRIDGE_EVENT_DISPATCH", "AUTH_STREAM",
        "CONTROL_DISCONNECTED_EARLY", "SESSION_DEADLINE",
        "WIFI_AUTH_RELEASE", "WIFI_NEGOTIATION_TCP"
    };
    for (size_t i = 0; i < sizeof(labels) / sizeof(labels[0]); ++i)
        if (stage && strcmp(stage, labels[i]) == 0) return labels[i];
    return "UNCLASSIFIED";
}

static int transport_inbound(const char *path, const char *run_dir, fe35_bridge_handle bridge,
                              fe35_scan_transport *scan, bool *cleanup_confirmed,fe36_auth_transport *auth,
                              fe35_wifi_transport *wifi) {
    uint8_t state[3], reply[7], owned_channel = 0;
    uint32_t handle = 0;
    uint16_t cid = 0, packet_type = 0, packet_channel = 0, control_mtu=512;
    uint8_t body[1024], auth_channel = 0, auth_uuid[16] = {0};
    uint32_t auth_handle = 0;
    uint8_t peer[6]={0}; uint16_t acl=0, auth_cid=0;
    int auth_opened=0, auth_disconnected=0, auth_verified=0;
    size_t size = 0;
    int fd = -1, result = 1, accepted = 0, opened = 0, disconnected = 0;
    int tcp=-1;
    int tcp_control_settled=0;
    int listener_ready = 0, session_started = 0;
    int registration_pending = 0, cleanup_uncertain = 0;
    if (cleanup_confirmed) *cleanup_confirmed = false;
    unsigned status = 0;
    const char *stage = "GUARD";
    if (current_scan || (scan && (!scan->notify || scan->generation <= 0)) ||
        (auth && (!scan || !auth->context || !auth->step || !auth->commit || !auth->cancel)) ||
        (wifi && (!auth || !wifi->context || !wifi->step || !wifi->cancel))) {
        if (bridge) fe35_bridge_close(bridge);
        return 1;
    }
    current_scan = scan;
    scan_ended = 0;
    if (guard_ready(run_dir) || !bridge) goto done;
    if (scan_poll()) goto done;
    fd = connect_daemon(path);
    if (fd < 0) { stage = "CONNECT"; goto done; }
    stage = "STATE";
    if (query(fd, 1, 0x60, state, sizeof(state)) || state[2] != 2) goto done;

    stage = "RFCOMM_LISTEN";
    for (uint8_t channel = 16; channel <= 23; ++channel) {
        uint8_t params[] = {channel, 0, 2};
        registration_pending = 1;
        if (exchange(fd, 0x42, params, sizeof(params), 0x85, reply, 4)) goto done;
        status = reply[2];
        if (reply[3] != channel) goto done;
        registration_pending = 0;
        if (status == 0) { owned_channel = channel; break; }
        if (status != 0x71) goto done;
    }
    if (!owned_channel) { stage = "RFCOMM_CHANNELS_BUSY"; goto done; }
    if (scan_event("RFCOMM_READY", owned_channel)) goto done;

    stage = "FE35_SDP";
    {
        uint8_t record[64];
        size_t record_size = service_record(record, 0xfe35, owned_channel);
        registration_pending = 1;
        if (exchange(fd, 0x30, record, record_size, 0x90, reply, 7)) goto done;
        status = reply[2];
        uint32_t candidate = le32(reply + 3);
        if (status) { registration_pending = 0; goto done; }
        if (candidate < 0x10000) goto done;
        handle = candidate;
        registration_pending = 0;
    }
    if (scan_poll() || scan_event("SDP_READY", owned_channel)) goto done;

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
            memcpy(peer,body+2,6);
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
                le16(body + 12) != cid || body[16] != 1 ||
                (auth && (memcmp(peer,body+3,6) || !le16(body+14) || le16(body+14)>512))) {
                stage = "INCOMING_OPEN_PROFILE";
                goto done;
            }
            found = opened = 1;
            acl=(uint16_t)le16(body+9);
            if(auth) control_mtu=(uint16_t)le16(body+14);
            if (scan_event("ACCEPTED", owned_channel)) goto done;
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
        int dispatched = dispatch_bridge_batch(fd, cid, control_mtu, bridge, batch, &auth_channel,
            &auth_handle, auth_uuid, deadline, run_dir);
        fe35_bridge_release_batch(batch);
        if (dispatched) { cleanup_uncertain = 1; goto done; }
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
            int dispatched = dispatch_bridge_batch(fd, cid, control_mtu, bridge, batch, &auth_channel,
                &auth_handle, auth_uuid, now_ms() + 4000, run_dir);
            fe35_bridge_release_batch(batch);
            if (dispatched) { cleanup_uncertain = 1; stage = "BRIDGE_EVENT_DISPATCH"; goto done; }
            if (auth_channel) listener_ready = 1;
            if(auth && auth_channel && listener_ready) {
                stage="AUTH_STREAM"; auth_strict_exchange=1;
                if(auth_stream(fd,run_dir,auth,bridge,cid,control_mtu,&auth_channel,&auth_handle,auth_uuid,peer,acl,&auth_cid,
                    &auth_opened,&auth_disconnected,&disconnected,&cleanup_uncertain)) goto done;
                auth_verified=1; break;
            }
        }
    }
    if (session_started && listener_ready && (!auth || auth_verified)) {
        result = 0;
    } else stage = disconnected ? "CONTROL_DISCONNECTED_EARLY" : "SESSION_DEADLINE";
    if(wifi && !result) {
        stage="WIFI_AUTH_RELEASE";
        uint8_t params[]={(uint8_t)auth_cid,(uint8_t)(auth_cid>>8),0};
        if(!auth_cid || command(fd,0x41,params,sizeof(params),now_ms()+4000)) {result=1;goto done;}
        if(receive_transport_packet(fd,auth_cid,&packet_type,&packet_channel,body,&size,now_ms()+4000,run_dir) ||
            packet_type!=4 || body[0]!=0x81 || le16(body+2)!=auth_cid) {result=1;cleanup_uncertain=1;goto done;}
        auth_disconnected=1;
        if(close_auth_listener(fd,auth_channel,auth_handle)) {result=1;cleanup_uncertain=1;goto done;}
        auth_channel=0;auth_handle=0;
        /* This is private one-shot transfer into the continuing owner, not final success. */
        if(scan_poll() || auth->commit(auth->context,1,now_ms()) || scan_poll()) {result=1;goto done;}
        stage="WIFI_NEGOTIATION_TCP";
        if(wifi_stream(fd,run_dir,bridge,wifi,cid,control_mtu,&tcp,&disconnected,&tcp_control_settled,&cleanup_uncertain)) result=1;
    }
done:;
    /* Immutable pre-cleanup observation. Final failure/cleanup certainty below
     * remains independent. No packet-loop IO or protocol/timing changes. */
    const char *const primary_failure_stage = result ? inbound_primary_stage(stage) : "NONE";
    if(tcp>=0 && close(tcp)) {result=1;cleanup_uncertain=1;stage="WIFI_TCP_CLOSE_UNCONFIRMED";}
    if(wifi && !wifi->cancel(wifi->context)) {result=1;cleanup_uncertain=1;stage="WIFI_NETWORK_CLEANUP_UNCONFIRMED";}
    /* Revoke pairing before touching resources. The common model emits CLOSE
     * once; a later CLEANED/failed callback cannot request a second cleanup. */
    if (scan && (!auth || result)) {
        (void)scan->notify(scan->context, scan->generation, result ? "FAILED" : "STOP", 0, now_ms());
        current_scan = NULL;
    }
    if (fd >= 0) {
        int cleanup_ok = 1;
        int64_t deadline = now_ms() + 4000;
        /* Pending accepted CID is owned even if OPEN was malformed/lost. Try
         * closing it, but never manufacture cleanup certainty from socket EOF. */
        if(auth_cid && !auth_disconnected) {
            uint8_t params[]={(uint8_t)auth_cid,(uint8_t)(auth_cid>>8),0};
            if(command(fd,0x41,params,sizeof(params),deadline)) cleanup_ok=0;
            else {
                int confirmed=0; int64_t close_deadline=now_ms()+5000;
#ifdef OPENHC_TRANSPORT_TEST_TIMEOUTS
                close_deadline=now_ms()+150;
#endif
                for(unsigned i=0;i<64;i++) {
                    if(receive_transport_packet(fd,auth_cid,&packet_type,&packet_channel,body,&size,close_deadline,run_dir)) break;
                    if(packet_type==4 && body[0]==0x81 && le16(body+2)==auth_cid) {confirmed=1;break;}
                    /* Do not swallow a remote control close/extra data and
                     * then promote a candidate. Unknown events fail closed. */
                    cleanup_ok=0;
                }
                if(!confirmed) cleanup_ok=0; else auth_disconnected=1;
            }
        }
        if (auth_channel || auth_handle) {
            if (close_auth_listener(fd, auth_channel, auth_handle)) cleanup_ok = 0;
            auth_channel = 0;
            auth_handle = 0;
        }
        if (opened && cid && !tcp_control_settled) {
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
                    /* A verified candidate is still revocable throughout
                     * cleanup. Do not discard unexpected data/events here
                     * and subsequently promote it on a later close ACK. */
                    if (auth) cleanup_ok = 0;
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
        /* Socket teardown alone does not confirm an unacknowledged registration
         * or pending CID. Preserve protocol status; report certainty separately. */
        int close_ok = close(fd) == 0;
        bool confirmed=cleanup_ok && close_ok && !registration_pending &&
                !cleanup_uncertain && (!cid || opened || disconnected) &&
                (!auth_cid || auth_disconnected);
        if (cleanup_confirmed) *cleanup_confirmed = confirmed;
        if(auth && !result && (!confirmed || scan_poll() || (!wifi && auth->commit(auth->context,1,now_ms())))) {
            result=1; stage=wifi?"WIFI_COMPLETION_REVOKED":"AUTH_COMMIT_REVOKED";
        }
    }
    if(auth) {
        auth->cancel(auth->context);
        if(scan && current_scan) (void)scan->notify(scan->context,scan->generation,result?"FAILED":"STOP",0,now_ms());
    }
    current_scan=NULL; auth_strict_exchange=0;
    memset(peer,0,sizeof(peer));
    printf("BTSTACK_FE35_INBOUND_PRIMARY_STAGE=%s\n", primary_failure_stage);
    if (result) printf("BTSTACK_FE35_INBOUND_FAILED=%s\n", stage);
    else {
        puts("BTSTACK_FE35_BRIDGE_SESSION_OK");
        if(wifi) puts("BTSTACK_NEARBY_TCP_BOUNDARY_CLEANED");
        if (disconnected) puts("BTSTACK_FE35_DISCONNECT_CONFIRMED");
    }
    if (bridge) fe35_bridge_close(bridge);
    if (scan) {
        /* Teardown-tail notification only, including CLEANUP_UNCONFIRMED.
         * The typed return, not this callback, carries cleanup certainty. */
        (void)scan->notify(scan->context, scan->generation, "CLEANED", 0, now_ms());
        scan_ended = 0;
    }
    (void)accepted;
    (void)auth_opened;
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
    return transport_inbound(path, run_dir, bridge, NULL, NULL,NULL,NULL);
}

fe35_scan_completion openhc_btstack_scan_inbound(const char *run_dir, fe35_bridge_handle bridge,
                                                fe35_scan_transport *scan) {
    return openhc_btstack_scan_auth_inbound(run_dir,bridge,scan,NULL);
}
fe35_scan_completion openhc_btstack_scan_auth_inbound(const char *run_dir, fe35_bridge_handle bridge,
                                                fe35_scan_transport *scan,fe36_auth_transport *auth) {
    return openhc_btstack_scan_wifi_inbound(run_dir,bridge,scan,auth,NULL);
}
fe35_scan_completion openhc_btstack_scan_wifi_inbound(const char *run_dir, fe35_bridge_handle bridge,
    fe35_scan_transport *scan,fe36_auth_transport *auth,fe35_wifi_transport *wifi) {
    fe35_scan_completion completion = { .returned = true, .cleanup_confirmed = false, .status = 1 };
    if (!scan) { if (bridge) fe35_bridge_close(bridge); return completion; }
#ifdef OPENHC_FE35_SIMULATOR_TEST
    const char *path = getenv("OPENHC_FE35_TEST_SOCKET");
    if (!path || !*path) { if (bridge) fe35_bridge_close(bridge); return completion; }
#else
    const char *path = "/tmp/BTstack";
#endif
    completion.status = transport_inbound(path, run_dir, bridge, scan, &completion.cleanup_confirmed,auth,wifi);
    return completion;
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
    if (argc == 4 && strcmp(argv[2], "--btstack-local-address") == 0)
        return transport_local_address(argv[1], argv[3]);
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
int openhc_btstack_local_address(const char *run_dir) {
    return transport_local_address("/tmp/BTstack", run_dir);
}
#endif
