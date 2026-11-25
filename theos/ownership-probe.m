#import <Foundation/Foundation.h>
#include <sys/stat.h>
#include <sys/sysctl.h>
#include <stdio.h>

/* Read-only snapshot. No launchctl bootstrap/kickstart, unload, kill, power,
 * pairing, socket connection, or peer operation is performed. */
int openhc_btstack_ownership_probe(void) {
    struct stat st;
    char machine[128] = {0}; size_t len = sizeof(machine);
    if (sysctlbyname("hw.machine", machine, &len, NULL, 0) == 0)
        printf("OWNERSHIP_MACHINE=%s\n", machine);
    printf("OWNERSHIP_OS=%s\n", [[[NSProcessInfo processInfo] operatingSystemVersionString] UTF8String]);
    printf("BTSTACK_SOCKET=%s\n", stat("/tmp/BTstack", &st) == 0 && S_ISSOCK(st.st_mode) ? "PRESENT" : "ABSENT");
    printf("BTDAEMON_FILE=%s\n", stat("/var/jb/usr/bin/BTdaemon", &st) == 0 ? "PRESENT" : "ABSENT");
    printf("BTSTACK_PLIST=%s\n", stat("/var/jb/Library/LaunchDaemons/ch.ringwald.BTstack.plist", &st) == 0 ? "PRESENT" : "ABSENT");
    puts("OWNERSHIP_SERVICE_PRINT=UNAVAILABLE_IN_SANDBOX");
    puts("OWNERSHIP_PROCESS_SNAPSHOT=UNAVAILABLE_IN_SANDBOX");
    puts("OWNERSHIP_SNAPSHOT_DONE");
    return 0;
}
