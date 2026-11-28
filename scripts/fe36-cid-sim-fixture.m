/* Real production owner/C transport/Native authenticator. OS admission, lease,
 * config, phone and daemon are explicitly synthetic. No deployed factory. */
#import "../theos/scan-owner/ScanOwnerRuntime.h"
#import "../theos/scan-owner/ScanOwnerForeground.h"
#include <arpa/inet.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <unistd.h>
#include <stdatomic.h>
#include <stdio.h>
#include <string.h>
NSData *openhc_fe36_transport_phone(OHCBScanReceiverEvent *,int,int);
@interface OHCCIDLease : NSObject <OHCScanLeaseAdapter>
@property(nonatomic,copy) NSString *privateRunDirectory;
@end
#include <fcntl.h>
/* Injected local network only. Exercises actual listen/accept ownership; never configures WiFi. */
@interface OHCCIDNetwork : NSObject <OHCNearbyNetwork>
@property(nonatomic,copy) NSString *directory;
@property(nonatomic,copy) NSString *scenario;
@property(nonatomic) int socketFD;
@property(nonatomic,strong) OHCBWifiNetworkConfig *info;
@end
@implementation OHCCIDNetwork
- (instancetype)init { if((self=[super init])) _socketFD=-1;return self; }
- (OHCBWifiNetworkConfig *)poll {
    if([_scenario isEqualToString:@"wifi_pending"] &&
       access([[_directory stringByAppendingPathComponent:@"network-ready"] fileSystemRepresentation],F_OK)) return nil;
    if(!_info) _info=[[OHCBWifiNetworkConfig alloc] initWithMode:OHCBWifiMode.direct phoneIp:@"127.0.0.2"
        ssid:@"SYNTHETIC" bssid:@"02:11:22:33:44:55" passphrase:@"synthetic-pass"
        frequencyMhz:2437 carIp:@"127.0.0.1"];
    return _info;
}
- (int)openListener {
    if(_socketFD>=0) return -1;
    int fd=socket(AF_INET,SOCK_STREAM,0);struct sockaddr_in local={0};
    local.sin_family=AF_INET;local.sin_addr.s_addr=htonl(INADDR_LOOPBACK);
    socklen_t size=sizeof(local);
    if(fd<0 || bind(fd,(struct sockaddr *)&local,size) || listen(fd,1) ||
       getsockname(fd,(struct sockaddr *)&local,&size) ||
       fcntl(fd,F_SETFD,FD_CLOEXEC) || fcntl(fd,F_SETFL,O_NONBLOCK)) {
        if(fd>=0)close(fd);[NSException raise:@"CIDNetwork" format:@"synthetic-listener"];return -1;
    }
    _socketFD=fd;
    [[NSString stringWithFormat:@"%u",(unsigned)ntohs(local.sin_port)] writeToFile:
        [_directory stringByAppendingPathComponent:@"tcp-port"] atomically:YES encoding:NSASCIIStringEncoding error:NULL];
    return fd;
}
- (BOOL)close {
    BOOL result=YES;if(_socketFD>=0) {result=close(_socketFD)==0;_socketFD=-1;}_info=nil;
    return result && ![_scenario isEqualToString:@"wifi_cleanup_failure"];
}
- (NSString *)acceptedPeerIPv4 {
    /* Loopback proxy address, not the advertised phone's synthetic assigned WiFi address.
     * No loopback alias/interface mutation is needed on macOS. Wrong peer remains real C reject. */
    return [_scenario isEqualToString:@"wifi_tcp_failure"]?@"192.0.2.99":@"127.0.0.1";
}
@end
@implementation OHCCIDLease
- (void)arm:(uint64_t)g deadline:(int64_t)d result:(void (^)(BOOL))r { (void)g;(void)d;r(YES); }
- (void)takeover:(uint64_t)g result:(void (^)(BOOL))r { (void)g;r(YES); }
- (void)heartbeat:(uint64_t)g { (void)g; }
- (void)stopHeartbeat:(uint64_t)g { (void)g; }
- (void)requestRestore:(uint64_t)g result:(void (^)(BOOL))r { (void)g;r(YES); }
- (void)delegateOnce:(uint64_t)g { (void)g; }
@end
#define CID_CHECK(c,label) do { if(!(c)) { invalid=1;fprintf(trace,"CID_ASSERT_FAIL=%s line=%d\n",label,__LINE__);fflush(trace); } } while(0)
static int rejectSend(void *context,const uint8_t *bytes,size_t size) {
    (void)bytes;(void)size;(*(int *)context)++;return -1;
}
int openhc_fe36_cid_fixture(const char *run_dir,const char *scenario) {
    NSString *name=[NSString stringWithUTF8String:scenario],*directory=[NSString stringWithUTF8String:run_dir];
    BOOL wifiCase=[name hasPrefix:@"wifi_"];
    BOOL boundaryCase=[@[@"wifi_success",@"wifi_pending",@"wifi_duplicate",@"wifi_cleanup_failure"] containsObject:name];
    BOOL cryptoCase=wifiCase || [@[@"success",@"wrong_pin",@"forged_signature",@"cleanup_failure",@"pending_stop",@"late_cleanup_data"] containsObject:name];
    __block _Atomic int invalid=0;
    FILE *trace=fopen([[directory stringByAppendingPathComponent:@"scan-events"] fileSystemRepresentation],"w");
    if(!trace) return 91;
    OHCCIDLease *lease=[OHCCIDLease new];lease.privateRunDirectory=directory;
    OHCBHostIdentity *host=[[OHCBHostIdentity alloc] initWithModelId:@"A1B2C3" subModelId:@"D4" brand:@"Synthetic" deviceName:@"Synthetic"];
    OHCBScanReceiverConfig *config=[[OHCBScanReceiverConfig alloc] initWithHost:host bluetoothAddress:@"A0:B1:C2:D3:E4:F5" supportsUsb:NO lifetimeMillis:2000];
    fe35_bridge_input input={0};
    strcpy(input.device_id,"CD1C73F369C5FE0B80808D3D0335EAF7D99B2AB9FE15403DC621C166FBADCB6F");
    input.root_key_size=input.const_a_size=input.const_b_size=16;
    for(int i=0;i<16;i++) { input.const_a[i]=(uint8_t)(0x10+i);input.const_b[i]=(uint8_t)(0x20+i); }
    OHCScanOwnerRuntime *runtime=[[OHCScanOwnerRuntime alloc] initWithConfig:config bridgeInput:&input lease:lease];
    memset(&input,0,sizeof(input));
    OHCBAuthServiceIdentity *service=[[OHCBAuthServiceIdentity alloc] initWithPackageName:@"org.example.auth" serviceType:@"EXAMPLE"];
    OHCBFe36AuthConfig *auth=[[OHCBFe36AuthConfig alloc] initWithService:service selfAuthId:@"SYNTHETIC_CAR" envelopeVersion:@"X_0@00000000000000" deviceInfo:@{@"model":@"SYNTHETIC"}];
    OHCBInMemoryTrustStore *trust=[[OHCBInMemoryTrustStore alloc] initWithInitial:[[OHCBTrustStoreSnapshot alloc] initWithIdentities:@[] peers:@[]]];
    dispatch_semaphore_t done=dispatch_semaphore_create(0),phoneDone=dispatch_semaphore_create(0);
    NSLock *secretLock=[NSLock new];
    __block NSData *receivedKey=nil,*expectedKey=nil;
    __block int keys=0,handed=0,cleared=0;
    __block BOOL completed=NO;
    OHCScanOwnerKeySink recordKey=^(uint64_t ownerGeneration,int64_t generation,int64_t incarnation,const uint8_t key[16]) {
        CID_CHECK(ownerGeneration==1 && generation==1 && incarnation==1,"trusted_generation_incarnation");
        CID_CHECK(cleared>=1 && handed==1,"authority_cleared_before_key_callback");
        [secretLock lock];keys++;receivedKey=[NSData dataWithBytes:key length:16];[secretLock unlock];
        fprintf(trace,"TRUSTED_KEY_CALLBACK\n");fflush(trace);
    };
    if(wifiCase) {
        OHCCIDNetwork *network=[OHCCIDNetwork new];network.directory=directory;network.scenario=name;
        CID_CHECK([runtime configureContinuingAuthentication:auth trust:trust network:network
            boundary:^BOOL(uint64_t ownerGeneration,int64_t generation,int64_t incarnation,int fd,const uint8_t key[16]) {
                struct sockaddr_in address={0};socklen_t size=sizeof(address);
                CID_CHECK(!getpeername(fd,(struct sockaddr *)&address,&size) && address.sin_family==AF_INET,
                    "actual_owned_tcp_accept");
                CID_CHECK(!completed,"tcp_boundary_before_worker_completion");
                recordKey(ownerGeneration,generation,incarnation,key);
                /* Actual private adapter replay/revoke contract, on the serial executor.
                 * This probe has synthetic bytes and does not grant another auth/lease. */
                OHCNearbyWifiTransport *probe=[[OHCNearbyWifiTransport alloc] initWithNetwork:network
                    accept:^BOOL(OHCNearbyWifiTransport *p,int f,int64_t n) {(void)p;(void)f;(void)n;return NO;}];
                CID_CHECK([probe handoffGeneration:1 deadline:100],"continuation_probe_captured_deadline");
                CID_CHECK(![probe handoffGeneration:2 deadline:200],"continuation_handoff_replay_rejected");
                CID_CHECK([probe storeKey:key] && ![probe storeKey:key],"continuation_key_transfer_one_shot");
                __block int calls=0;
                OHCWifiBoundary once=^BOOL(uint64_t o,int64_t g,int64_t c,int f,const uint8_t k[16]) {
                    (void)o;(void)g;(void)c;(void)f;(void)k;calls++;return YES;
                };
                CID_CHECK([probe deliverTo:once owner:1 descriptor:fd] &&
                    ![probe deliverTo:once owner:1 descriptor:fd] && calls==1,"continuation_key_delivery_one_shot");
                [probe revoke];
                CID_CHECK(![probe storeKey:key] && ![probe deliverTo:once owner:1 descriptor:fd],
                    "continuation_cancel_denies_late_transfer_and_callback");
                fprintf(trace,"OWNED_TCP_CONTROL_BOUNDARY\n");fflush(trace);return YES;
            }],"explicit_continuing_configuration");
    } else CID_CHECK([runtime configureAuthentication:auth trust:trust keySink:recordKey],"explicit_trusted_configuration");
    __block NSString *originalPIN=nil;
    runtime.events=^(NSArray<OHCBScanReceiverEvent *> *events) {
        for(OHCBScanReceiverEvent *event in events) {
            fprintf(trace,"EVENT=%s\n",event.kind.UTF8String);
            if([event.kind isEqualToString:@"PAIRING_READY"]) originalPIN=[event.pinCode copy];
            if([event.kind isEqualToString:@"CLEAR_PAIRING"]) cleared++;
            if([event.kind isEqualToString:@"AUTH_HANDOFF"]) {
                handed++;CID_CHECK([event.pinCode isEqualToString:originalPIN],"original_pin_handoff");
                if([name isEqualToString:@"success"]) {
                    /* Exact adapter SEND failure, injected callback only. The
                     * separate reset case executes actual C socket failure. */
                    OHCFe36AuthTransport *probe=[[OHCFe36AuthTransport alloc] initWithConfig:auth trust:trust
                        commit:^BOOL(OHCFe36AuthTransport *a,int64_t c,int64_t n) { (void)a;(void)c;(void)n;return NO; }];
                    CID_CHECK([probe handoff:event now:10 deadline:20000],"send_failure_probe_handoff");
                    fe36_auth_transport binding=[probe binding];int sends=0;
                    CID_CHECK(binding.step(binding.context,FE36_IO_CONNECTED,1,NULL,0,11,rejectSend,&sends)==0,"probe_connected");
                    NSData *hello=[@"{\"oper_type\":1,\"data\":\"{\\\"deviceId\\\":\\\"SYNTHETIC_PHONE\\\",\\\"has_pin\\\":true,\\\"usb_connection\\\":false}\",\"version\":\"SYNTHETIC_PHONE_VERSION\"}" dataUsingEncoding:NSUTF8StringEncoding];
                    CID_CHECK(binding.step(binding.context,FE36_IO_DATA,1,hello.bytes,hello.length,12,rejectSend,&sends)<0&&sends==1,"send_failure_cancels_adapter");
                    CID_CHECK(![probe deliver:1 now:13 sink:^(int64_t g,int64_t c,const uint8_t k[16]) { (void)g;(void)c;(void)k;CID_CHECK(NO,"failed_send_no_key_sink"); }],"failed_send_no_key");
                    CID_CHECK(![probe handoff:event now:13 deadline:20000],"adapter_handoff_one_shot");
                    fprintf(trace,"FE36_ADAPTER_INJECTED_SEND_FAILURE_OK\n");
                }
                if(cryptoCase) dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED,0),^{ @autoreleasepool {
                    int fd=-1;
                    @try {
                        int port=[[NSString stringWithContentsOfFile:[directory stringByAppendingPathComponent:@"phone-port"] encoding:NSASCIIStringEncoding error:NULL] intValue];
                        CID_CHECK(port>0&&port<=65535,"test_proxy_port");
                        fd=socket(AF_INET,SOCK_STREAM,0);struct sockaddr_in address={0};
                        address.sin_family=AF_INET;address.sin_addr.s_addr=htonl(INADDR_LOOPBACK);address.sin_port=htons((uint16_t)port);
                        struct timeval bound={6,0};int one=1;
                        CID_CHECK(fd>=0&&!setsockopt(fd,SOL_SOCKET,SO_RCVTIMEO,&bound,sizeof(bound))&&
                            !setsockopt(fd,SOL_SOCKET,SO_SNDTIMEO,&bound,sizeof(bound))&&
                            !setsockopt(fd,SOL_SOCKET,SO_NOSIGPIPE,&one,sizeof(one))&&
                            !connect(fd,(struct sockaddr *)&address,sizeof(address)),"test_proxy_connect");
                        int mode=[name isEqualToString:@"wrong_pin"]?1:([name isEqualToString:@"forged_signature"]?2:0);
                        NSData *expected=openhc_fe36_transport_phone(event,fd,mode);
                        [secretLock lock];expectedKey=expected;[secretLock unlock];
                    } @catch(NSException *e) {
                        BOOL known=[e.name isEqualToString:@"AuthFixture"];
                        fprintf(trace,"CID_PHONE_EXCEPTION name=%s reason=%s\n",
                            known?"AuthFixture":"redacted-external",
                            known?"static-assertion":"redacted-external");fflush(trace);
                        CID_CHECK(NO,"phone_real_crypto_exchange");
                    }
                    @finally { if(fd>=0) close(fd);dispatch_semaphore_signal(phoneDone); }
                }});
            }
        } fflush(trace);
    };
    runtime.finished=^(fe35_scan_completion c,BOOL delegated) {
        BOOL success=[name isEqualToString:@"success"] ||
            [@[@"wifi_success",@"wifi_pending",@"wifi_duplicate"] containsObject:name];
        BOOL uncertain=[@[@"send_failure",@"cleanup_failure",@"pending_stop",@"late_cleanup_data",@"wrong_peer",
            @"wrong_cid",@"control_cid_reuse",@"extra_connection",@"wrong_listener",@"wrong_data_cid",@"reopened_cid",
            @"wifi_cleanup_failure"] containsObject:name];
        CID_CHECK(c.returned && c.status==(success?0:1),"typed_protocol_completion");
        CID_CHECK(c.cleanup_confirmed==!uncertain,"independent_cleanup_certainty");
        CID_CHECK(delegated==uncertain,"uncertainty_delegates");
        CID_CHECK(handed==1 && cleared>=1,"one_handoff_pairing_revoked");
        fprintf(trace,"CID_COMPLETION=%d,%d,%d\n",c.returned,c.cleanup_confirmed,c.status);fflush(trace);
        completed=YES;dispatch_semaphore_signal(done);
    };
    int fds[2];if(socketpair(AF_UNIX,SOCK_STREAM,0,fds)) {fclose(trace);return 91;}
    OHCScanOwnerForeground *foreground=[[OHCScanOwnerForeground alloc] initWithConnectedDescriptor:fds[1]];
    ohc_owner_peer peer={0};peer.connection=1;peer.endpoint_device=1;peer.endpoint_inode=1;peer.policy_epoch=0x54455354;
    peer.kernel_verified=peer.endpoint_verified=true;peer.token[1]=peer.token[2]=501;peer.token[5]=123;peer.token[7]=10;
    [runtime acceptTestDescriptor:fds[0] evidence:peer];[foreground start];
    NSDate *limit=[NSDate dateWithTimeIntervalSinceNow:15];
    NSString *stop=[directory stringByAppendingPathComponent:@"stop"];BOOL stopped=NO;
    while(dispatch_semaphore_wait(done,DISPATCH_TIME_NOW) && limit.timeIntervalSinceNow>0) {
        if(!stopped && !access(stop.fileSystemRepresentation,F_OK)) {
            if([name isEqualToString:@"background"]) [foreground background]; else [foreground stop];
            stopped=YES;
        }
        [[NSRunLoop currentRunLoop] runUntilDate:[NSDate dateWithTimeIntervalSinceNow:.005]];
    }
    if(!completed) _exit(95);
    if(cryptoCase) CID_CHECK(!dispatch_semaphore_wait(phoneDone,dispatch_time(DISPATCH_TIME_NOW,8*NSEC_PER_SEC)),"phone_completed");
    CID_CHECK(runtime.testHandoffCount==1,"final_executor_barrier");
    [secretLock lock];
    BOOL success=[name isEqualToString:@"success"] || boundaryCase;
    CID_CHECK(keys==(success?1:0),"key_once_only_on_verified_current_success");
    if(success) CID_CHECK(expectedKey.length==16 && [expectedKey isEqual:receivedKey],"actual_transport_same_pin_key_matches_phone");
    else CID_CHECK(receivedKey==nil,"cancelled_no_key");
    receivedKey=nil;expectedKey=nil;[secretLock unlock];
    if(success) CID_CHECK(trust.snapshot.peers.count==1 && trust.snapshot.identities.count==1,"verified_pairing_trust_commit");
    if([@[@"wrong_pin",@"forged_signature"] containsObject:name])
        CID_CHECK(trust.snapshot.peers.count==0 && trust.snapshot.identities.count==0,"rejected_peer_not_trusted");
    runtime.events=nil;runtime.finished=nil;[foreground stop];
    fprintf(trace,"FE36_CID_BOUNDARY=real-owner-C-transport-ObjC-Native-auth;synthetic-daemon-phone-config-admission-lease\n");
    fclose(trace);return invalid?96:0;
}
