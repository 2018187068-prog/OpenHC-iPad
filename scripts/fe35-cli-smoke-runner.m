#import <Foundation/Foundation.h>
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

int openhc_cli_main(int argc, const char *argv[]);
int openhc_scan_transport_fixture(const char *run_dir, const char *scenario);
int openhc_scan_owner_fixture(const char *run_dir, const char *scenario);
int openhc_fe36_cid_fixture(const char *run_dir, const char *scenario);

static int write_all(int fd, const uint8_t *bytes, size_t size) {
    while (size) {
        ssize_t written = write(fd, bytes, size);
        if (written < 0 && errno == EINTR) continue;
        if (written <= 0) return -1;
        bytes += written;
        size -= (size_t)written;
    }
    return 0;
}

static int setup_bridge_input(void) {
    static const char device_id[] =
        "CD1C73F369C5FE0B80808D3D0335EAF7D99B2AB9FE15403DC621C166FBADCB6F";
    uint8_t config[2 + sizeof(device_id) - 1 + 3 * 17];
    size_t offset = 0;
    config[offset++] = 1;
    config[offset++] = (uint8_t)(sizeof(device_id) - 1);
    memcpy(config + offset, device_id, sizeof(device_id) - 1);
    offset += sizeof(device_id) - 1;
    config[offset++] = 16;
    memset(config + offset, 0, 16);
    offset += 16;
    config[offset++] = 16;
    for (int i = 0; i < 16; ++i) config[offset++] = (uint8_t)(0x10 + i);
    config[offset++] = 16;
    for (int i = 0; i < 16; ++i) config[offset++] = (uint8_t)(0x20 + i);

    int descriptors[2];
    if (pipe(descriptors)) return -1;
    int result = write_all(descriptors[1], config, offset);
    close(descriptors[1]);
    memset(config, 0, sizeof(config));
    if (result || dup2(descriptors[0], STDIN_FILENO) < 0) {
        close(descriptors[0]);
        return -1;
    }
    close(descriptors[0]);
    return 0;
}

int main(int argc, char *argv[]) {
    @autoreleasepool {
        int result;
        if (argc == 2 && strcmp(argv[1], "--fe35-bridge-smoke") == 0) {
            result = openhc_cli_main(argc, (const char **)argv);
        } else if (argc == 3 || argc == 4) {
            if (chdir(NSHomeDirectory().fileSystemRepresentation) != 0 ||
                setenv("OPENHC_FE35_TEST_SOCKET", argv[1], 1) != 0 || setup_bridge_input()) return 91;
            NSString *logPath = [NSHomeDirectory() stringByAppendingPathComponent:
                @"Documents/fe35-cli-status.log"];
            int logFD = open(logPath.fileSystemRepresentation, O_WRONLY | O_CREAT | O_TRUNC, 0600);
            if (logFD < 0 || dup2(logFD, STDOUT_FILENO) < 0 || dup2(logFD, STDERR_FILENO) < 0) {
                if (logFD >= 0) close(logFD);
                return 91;
            }
            close(logFD);
            const char *cli_argv[] = {"openhc-bridge-check", "--btstack-control-inbound", argv[2]};
            result = argc == 4 ? (!strncmp(argv[3], "auth_", 5) ?
                openhc_fe36_cid_fixture(argv[2],argv[3]+5) : !strncmp(argv[3], "owner_", 6) ?
                openhc_scan_owner_fixture(argv[2], argv[3] + 6) :
                openhc_scan_transport_fixture(argv[2], argv[3])) : openhc_cli_main(3, cli_argv);
        } else {
            return 92;
        }
        NSString *path = [NSHomeDirectory() stringByAppendingPathComponent:
            @"Documents/fe35-cli-result"];
        NSError *error = nil;
        NSString *directory = [path stringByDeletingLastPathComponent];
        if (![[NSFileManager defaultManager] createDirectoryAtPath:directory
                withIntermediateDirectories:YES attributes:nil error:&error]) return 90;
        error = nil;
        if (![[NSString stringWithFormat:@"%d\n", result] writeToFile:path
                atomically:YES encoding:NSUTF8StringEncoding error:&error]) return 90;
        return result;
    }
}
