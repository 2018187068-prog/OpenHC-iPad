#import <Foundation/Foundation.h>
#import <objc/runtime.h>
#include <dlfcn.h>
#include <ifaddrs.h>
#include <arpa/inet.h>
#include <sys/stat.h>
#include <sys/sysctl.h>
#include <net/if.h>
#include <string.h>

/* Read-only capability inventory: no Wi-Fi setters, credentials or BT socket connect. */
int openhc_platform_probe(void) {
    char machine[128] = {0}; size_t len = sizeof(machine);
    if(sysctlbyname("hw.machine", machine, &len, NULL, 0) == 0) printf("HW_MACHINE=%s\n",machine);
    printf("OS_VERSION=%s\n", [[[NSProcessInfo processInfo] operatingSystemVersionString] UTF8String]);
    struct ifaddrs *interfaces = NULL;
    if(getifaddrs(&interfaces) == 0) {
        for(struct ifaddrs *p=interfaces; p; p=p->ifa_next) {
            if(!p->ifa_addr || p->ifa_addr->sa_family != AF_INET || (p->ifa_flags & IFF_LOOPBACK)) continue;
            char ip[INET_ADDRSTRLEN];
            struct sockaddr_in *sa=(struct sockaddr_in *)p->ifa_addr;
            if(inet_ntop(AF_INET,&sa->sin_addr,ip,sizeof(ip))) printf("INTERFACE_IPV4=%s,%s\n",p->ifa_name,ip);
        }
        freeifaddrs(interfaces);
    }
    void *mis=dlopen("/System/Library/PreferenceBundles/WirelessModemSettings.bundle/WirelessModemSettings",RTLD_LAZY|RTLD_LOCAL);
    Class manager=NSClassFromString(@"MISManager");
    printf("MIS_BUNDLE_LOADABLE=%s\n",mis?"YES":"NO");
    printf("MIS_MANAGER_CLASS=%s\n",manager?"YES":"NO");
    printf("MIS_STATE_SELECTOR=%s\n",manager && class_getInstanceMethod(manager,NSSelectorFromString(@"getState:andReason:"))?"YES":"NO");
    // Keep loaded ObjC bundle resident; do not instantiate or toggle sharing.
    void *wifi=dlopen("/System/Library/PrivateFrameworks/MobileWiFi.framework/MobileWiFi",RTLD_LAZY|RTLD_LOCAL);
    printf("MOBILEWIFI_LOADABLE=%s\n",wifi?"YES":"NO");
    printf("MOBILEWIFI_CLIENT_SYMBOL=%s\n",wifi && dlsym(wifi,"WiFiManagerClientCreate")?"YES":"NO");
    struct stat st;
    printf("BTSTACK_UNIX_SOCKET=%s\n",stat("/tmp/BTstack",&st)==0 && S_ISSOCK(st.st_mode)?"PRESENT":"NOT_FOUND");
    printf("BTDAEMON_ROOTLESS_FILE=%s\n",stat("/var/jb/usr/bin/BTdaemon",&st)==0?"PRESENT":"NOT_FOUND");
    puts("HOTSPOT_AP_CAPABILITY=UNVERIFIED");
    puts("HOTSPOT_SSID=UNVERIFIED");
    puts("HOTSPOT_BSSID=UNVERIFIED");
    puts("HOTSPOT_FREQUENCY=UNVERIFIED");
    puts("BTSTACK_FE35_FE36=UNVERIFIED");
    puts("PLATFORM_INVENTORY_DONE");
    return 0;
}
