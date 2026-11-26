/* Runs the actual production send paths with default SIGPIPE handling.
 * If either path loses platform protection, the process dies instead of PASS. */
#define OPENHC_BTSTACK_TEST
#define main openhc_probe_unused_main
#include "../theos/btstack-probe.c"
#undef main
#include <signal.h>

static int closed_peer(int guarded) {
    int sockets[2];
    if (socketpair(AF_UNIX, SOCK_STREAM, 0, sockets)) return 2;
    if (protect_socket_sigpipe(sockets[0])) {
        close(sockets[0]); close(sockets[1]); return 3;
    }
    close(sockets[1]);
    uint8_t byte = 0;
    if (guarded == 2) {
        /* Exercise send itself even if poll would reject a closed endpoint. */
        ssize_t sent = send_without_sigpipe(sockets[0], &byte, 1);
        int error = errno;
        close(sockets[0]);
        return sent == -1 && error == EPIPE ? 0 : 7;
    }
    int result = guarded
        ? transfer_guarded(sockets[0], &byte, 1, 1, now_ms() + 1000, NULL)
        : transfer(sockets[0], &byte, 1, 1, now_ms() + 1000);
    close(sockets[0]);
    return result == -1 ? 0 : 4;
}

int main(void) {
    if (signal(SIGPIPE, SIG_DFL) == SIG_ERR) return 5;
    int result = closed_peer(0);
    if (result) return result;
    result = closed_peer(1);
    if (result) return result;
    result = closed_peer(2);
    if (result) return result;
    /* Prove the tests did not accidentally gain global SIGPIPE suppression. */
    if (signal(SIGPIPE, SIG_DFL) != SIG_DFL) return 6;
    puts("BTSTACK_CLOSED_PEER_SIGPIPE_PROTECTION_OK=3");
    return 0;
}
