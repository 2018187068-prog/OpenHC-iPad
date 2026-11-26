#import "ScanHelperClient.h"
#import <sys/socket.h>
#import <sys/un.h>
#import <poll.h>
#import <fcntl.h>
#import <unistd.h>
#import <errno.h>
#import <stdint.h>
#import <time.h>
#if __has_include(<rootless.h>)
#import <rootless.h>
#define OHC_HELPER_SOCKET_PATH ROOT_PATH("/var/run/openhc/scan-ping.sock")
#else
#define OHC_HELPER_SOCKET_PATH "/var/jb/var/run/openhc/scan-ping.sock"
#endif
#import <string.h>

static int64_t monotonicMillis(void) {
    struct timespec now;
    if (clock_gettime(CLOCK_MONOTONIC, &now) != 0) return -1;
    return (int64_t)now.tv_sec * 1000 + now.tv_nsec / 1000000;
}

static int waitSocket(int fd, short events, int64_t deadlineMs) {
    struct pollfd pfd = { .fd = fd, .events = events };
    int result;
    do {
        int64_t nowMs = monotonicMillis();
        int64_t remaining = deadlineMs - nowMs;
        if (nowMs < 0 || remaining <= 0) return -1;
        result = poll(&pfd, 1, remaining > INT32_MAX ? INT32_MAX : (int)remaining);
    } while (result < 0 && errno == EINTR);
    return result > 0 && (pfd.revents & (events | POLLERR | POLLHUP)) ? 0 : -1;
}

static BOOL writeAll(int fd, const void *bytes, size_t count, int64_t deadlineMs) {
    const uint8_t *cursor = bytes;
    while (count) {
        if (waitSocket(fd, POLLOUT, deadlineMs) != 0) return NO;
        ssize_t n = write(fd, cursor, count);
        if (n < 0 && (errno == EINTR || errno == EAGAIN || errno == EWOULDBLOCK)) continue;
        if (n <= 0) return NO;
        cursor += n; count -= (size_t)n;
    }
    return YES;
}

static BOOL readAll(int fd, void *bytes, size_t count, int64_t deadlineMs) {
    uint8_t *cursor = bytes;
    while (count) {
        if (waitSocket(fd, POLLIN, deadlineMs) != 0) return NO;
        ssize_t n = read(fd, cursor, count);
        if (n < 0 && (errno == EINTR || errno == EAGAIN || errno == EWOULDBLOCK)) continue;
        if (n <= 0) return NO;
        cursor += n; count -= (size_t)n;
    }
    return YES;
}

@implementation OHCScanHelperClient
+ (void)pingWithTimeout:(NSTimeInterval)timeout completion:(void (^)(NSString *))completion {
    const int timeoutMs = (int)(MAX(0.1, MIN(timeout, 5.0)) * 1000.0);
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_UTILITY, 0), ^{
        const int64_t startedAtMs = monotonicMillis();
        const int64_t deadlineMs = startedAtMs + timeoutMs;
        int fd = socket(AF_UNIX, SOCK_STREAM, 0);
        BOOL ok = fd >= 0 && startedAtMs >= 0;
        if (ok) {
            int noSigPipe = 1;
            if (setsockopt(fd, SOL_SOCKET, SO_NOSIGPIPE, &noSigPipe, sizeof(noSigPipe)) != 0)
                ok = NO;
            struct sockaddr_un address = { .sun_family = AF_UNIX };
            const char *path = OHC_HELPER_SOCKET_PATH;
            size_t pathLength = strlen(path);
            if (pathLength >= sizeof(address.sun_path)) ok = NO;
            else {
                strlcpy(address.sun_path, path, sizeof(address.sun_path));
                int flags = fcntl(fd, F_GETFL, 0);
                if (flags < 0 || fcntl(fd, F_SETFL, flags | O_NONBLOCK) != 0) ok = NO;
                int result = ok ? connect(fd, (struct sockaddr *)&address, sizeof(address)) : -1;
                if (ok && result != 0 && (errno == EINPROGRESS || errno == EAGAIN)
                    && waitSocket(fd, POLLOUT, deadlineMs) == 0) {
                    int error = 0; socklen_t length = sizeof(error);
                    ok = getsockopt(fd, SOL_SOCKET, SO_ERROR, &error, &length) == 0 && error == 0;
                } else if (ok && result != 0) ok = NO;
            }
        }
        const char request[] = "PING\n";
        char response[5] = {0};
        if (ok) ok = writeAll(fd, request, sizeof(request) - 1, deadlineMs)
            && shutdown(fd, SHUT_WR) == 0
            && readAll(fd, response, 5, deadlineMs)
            && memcmp(response, "PONG\n", 5) == 0;
        if (fd >= 0) close(fd);
        NSString *reply = ok ? @"PONG" : @"HELPER_UNAVAILABLE";
        dispatch_async(dispatch_get_main_queue(), ^{ if (completion) completion(reply); });
    });
}
@end
