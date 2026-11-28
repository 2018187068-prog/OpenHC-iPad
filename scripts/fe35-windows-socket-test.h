/* Test-only OS binding for running the actual btstack-probe.c on Windows.
 * Winsock IO, WSAPoll and QPC are real OS calls, not a protocol implementation.
 * This does not validate Darwin/POSIX ABI or SIGPIPE behavior. */
#ifndef OPENHC_FE35_WINDOWS_SOCKET_TEST_H
#define OPENHC_FE35_WINDOWS_SOCKET_TEST_H
#if !defined(_WIN32) || !defined(OPENHC_BTSTACK_TEST) || !defined(OPENHC_FE35_SIMULATOR_TEST)
#error Windows socket adapter is restricted to the standalone test carrier
#endif
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
#include <afunix.h>
#include <io.h>
#include <limits.h>
#include <errno.h>
#include <stdint.h>
#include <time.h>
#include <sys/types.h>
#ifndef F_SETFL
#define F_SETFL 4
#endif
#ifndef F_SETFD
#define F_SETFD 2
#define FD_CLOEXEC 1
#endif
#define SHUT_RDWR SD_BOTH
#ifndef O_NONBLOCK
#define O_NONBLOCK 0x800
#endif
#ifndef F_OK
#define F_OK 0
#endif
#ifndef STDIN_FILENO
#define STDIN_FILENO 0
#endif
#ifndef CLOCK_MONOTONIC
#define CLOCK_MONOTONIC 1
#endif

static int ohc_windows_error(void) {
    switch (WSAGetLastError()) {
        case WSAEWOULDBLOCK: errno = EAGAIN; break;
        case WSAEINTR: errno = EINTR; break;
        case WSAECONNRESET: errno = ECONNRESET; break;
        default: errno = EIO; break;
    }
    return -1;
}
static int ohc_windows_socket(int family, int type, int protocol) {
    SOCKET s = socket(family, type, protocol);
    if (s == INVALID_SOCKET) return ohc_windows_error();
    /* Production fd type is int. Fail rather than silently truncate a handle. */
    if (s > INT_MAX) { closesocket(s); errno = EMFILE; return -1; }
    return (int)s;
}
static int ohc_windows_connect(int fd, const struct sockaddr *address, int size) {
    int r = connect((SOCKET)fd, address, size);
    if (r == SOCKET_ERROR) {
        if (WSAGetLastError() == WSAEWOULDBLOCK) { errno = EINPROGRESS; return -1; }
        return ohc_windows_error();
    }
    return r;
}
static int ohc_windows_fcntl(int fd, int operation, int flags) {
    if (operation == F_SETFD && flags == FD_CLOEXEC)
        return SetHandleInformation((HANDLE)(uintptr_t)fd, HANDLE_FLAG_INHERIT, 0) ? 0 : -1;
    if (operation != F_SETFL || flags != O_NONBLOCK) { errno = EINVAL; return -1; }
    u_long nonblocking = 1;
    return ioctlsocket((SOCKET)fd, FIONBIO, &nonblocking) ? ohc_windows_error() : 0;
}
static int ohc_windows_poll(struct pollfd *fds, unsigned long count, int ms) {
    int r = WSAPoll(fds, count, ms);
    return r == SOCKET_ERROR ? ohc_windows_error() : r;
}
static ssize_t ohc_windows_send(int fd, const void *data, size_t size, int flags) {
    if (size > INT_MAX) { errno = EINVAL; return -1; }
    int r = send((SOCKET)fd, data, (int)size, flags);
    return r == SOCKET_ERROR ? ohc_windows_error() : r;
}
static ssize_t ohc_windows_recv(int fd, void *data, size_t size, int flags) {
    if (size > INT_MAX) { errno = EINVAL; return -1; }
    int r = recv((SOCKET)fd, data, (int)size, flags);
    return r == SOCKET_ERROR ? ohc_windows_error() : r;
}
static ssize_t ohc_windows_read(int fd, void *data, size_t size) {
    if (fd == STDIN_FILENO) return _read(fd, data, (unsigned int)size);
    return ohc_windows_recv(fd, data, size, 0);
}
static int ohc_windows_close(int fd) {
    return closesocket((SOCKET)fd) == SOCKET_ERROR ? ohc_windows_error() : 0;
}
static int ohc_windows_getsockopt(int fd, int level, int name, void *value, socklen_t *size) {
    return getsockopt((SOCKET)fd, level, name, value, size) ? ohc_windows_error() : 0;
}
static int ohc_windows_clock(int clock_id, struct timespec *value) {
    LARGE_INTEGER count, frequency;
    if (clock_id != CLOCK_MONOTONIC || !QueryPerformanceCounter(&count) ||
        !QueryPerformanceFrequency(&frequency) || frequency.QuadPart <= 0) return -1;
    value->tv_sec = (time_t)(count.QuadPart / frequency.QuadPart);
    value->tv_nsec = (long)((count.QuadPart % frequency.QuadPart) * 1000000000 / frequency.QuadPart);
    return 0;
}
#define socket ohc_windows_socket
#define connect ohc_windows_connect
#define fcntl ohc_windows_fcntl
#define poll ohc_windows_poll
#define send ohc_windows_send
#define recv ohc_windows_recv
#define read ohc_windows_read
#define close ohc_windows_close
#define getsockopt ohc_windows_getsockopt
#define clock_gettime ohc_windows_clock
#define access _access
#endif
