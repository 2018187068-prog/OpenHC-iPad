/* Actual production inbound path + real sockets; bridge/owner effects injected.
 * Fault modes inject one syscall failure only, never replace cleanup logic. */
#if defined(__linux__) && !defined(_POSIX_C_SOURCE)
#define _POSIX_C_SOURCE 200809L
#endif
#define OPENHC_BTSTACK_TEST
#define OPENHC_FE35_SIMULATOR_TEST
#define OPENHC_TRANSPORT_TEST_TIMEOUTS
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#ifdef OPENHC_WINDOWS_SOCKET_TEST
#include "fe35-windows-socket-test.h"
#else
#include <sys/socket.h>
#include <unistd.h>
#endif
static int fault_mode, cleanup_phase, fault_count;
static ssize_t incoming_test_send(int fd, const void *data, size_t size, int flags) {
    const uint8_t *p = data;
    int ocf = size >= 9 && p[0] == 1 && p[1] == 0 && p[7] == 0xf4 ? p[6] : -1;
    if (cleanup_phase && !fault_count &&
        ((fault_mode == 1 && ocf == 0x31) ||
         (fault_mode == 2 && ocf == 0x43) || (fault_mode == 3 && ocf == 1))) {
        fault_count++;
        errno = EIO;
        return -1;
    }
#ifdef OPENHC_WINDOWS_SOCKET_TEST
    return ohc_windows_send(fd, data, size, flags);
#else
    return send(fd, data, size, flags);
#endif
}
static int incoming_test_close(int fd) {
#ifdef OPENHC_WINDOWS_SOCKET_TEST
    int result = ohc_windows_close(fd);
#else
    int result = close(fd);
#endif
    if (cleanup_phase && fault_mode == 4 && !fault_count && !result) {
        fault_count++;
        errno = EIO;
        return -1; /* Real socket already closed, report injected close error. */
    }
    return result;
}
#ifdef OPENHC_WINDOWS_SOCKET_TEST
#undef send
#undef close
#endif
#define send incoming_test_send
#define close incoming_test_close
#define main incoming_unused_probe_main
#include "../theos/btstack-probe.c"
#undef main
#undef send
#undef close
static int notifications[3];
static int observe(void *context, int64_t generation, const char *kind, int channel, int64_t now) {
    (void)context; (void)generation; (void)channel; (void)now;
    if (!strcmp(kind, "FAILED")) { cleanup_phase = 1; notifications[0]++; }
    if (!strcmp(kind, "CLEANED")) notifications[1]++;
    if (!strcmp(kind, "SDP_READY")) notifications[2]++;
    return 0; /* Injected owner callback, no cancellation or timing emulation. */
}
int main(int argc, char **argv) {
    if (argc != 4) return 2;
#ifdef OPENHC_WINDOWS_SOCKET_TEST
    WSADATA wsa;
    if (WSAStartup(MAKEWORD(2, 2), &wsa)) return 3;
#endif
    fault_mode = atoi(argv[3]);
    if (fault_mode < 0 || fault_mode > 4) return 2;
    fe35_bridge_input input = {.root_key_size=16, .const_a_size=16, .const_b_size=16};
    strcpy(input.device_id, "synthetic-exception");
    fe35_bridge_handle bridge = fe35_bridge_create(&input);
    if (!bridge) return 4;
    fe35_scan_transport scan = {.generation=1, .stop_fd=-1, .notify=observe};
    bool confirmed = false;
    int result = transport_inbound(argv[1], argv[2], bridge, &scan, &confirmed, NULL, NULL);
    printf("FE35_INCOMING_C_COMPLETION=1,%d,%d\n", confirmed, result);
    printf("FE35_INCOMING_C_CALLBACKS=%d,%d,%d\n", notifications[0],notifications[1],notifications[2]);
    printf("FE35_INCOMING_C_FAULTS=%d\n", fault_count);
#ifdef OPENHC_WINDOWS_SOCKET_TEST
    if (WSACleanup()) return 5;
#endif
    return 0; /* Python independently checks protocol status and cleanup. */
}
