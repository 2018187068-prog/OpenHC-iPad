#ifndef OHC_SCAN_HELPER_PATH_H
#define OHC_SCAN_HELPER_PATH_H

/*
 * Use launchd's stable rootless alias explicitly. ROOT_PATH can expand through
 * the relocated preboot root, whose resolved pathname may exceed sockaddr_un's
 * short AF_UNIX path limit. Both processes traverse the same /var/jb alias.
 */
#define OHC_SCAN_HELPER_RUNTIME_PATH "/var/jb/var/run/openhc"
#define OHC_SCAN_HELPER_SOCKET_PATH OHC_SCAN_HELPER_RUNTIME_PATH "/scan-ping.sock"
#define OHC_SCAN_HELPER_LOCK_PATH OHC_SCAN_HELPER_RUNTIME_PATH "/scan-ping.lock"

#endif
