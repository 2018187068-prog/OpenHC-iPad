/* Only OS admission/daemon/lease effects are synthetic. The owner runtime,
 * framing, completion/recovery decisions, C transport and Kotlin are production
 * sources. Never linked into a shipped helper or enabled by runtime flags. */
#import "../theos/scan-owner/ScanOwnerRuntime.h"
#import "../theos/scan-owner/ScanOwnerForeground.h"
#import <UIKit/UIKit.h>
#import "../theos/scan-ui/ScanQRCode.h"
#include <sys/socket.h>
#include <unistd.h>
#include <stdio.h>
#include <string.h>
#include <stdatomic.h>

@interface OHCFixtureLease : NSObject <OHCScanLeaseAdapter>
@property(nonatomic, copy) NSString *privateRunDirectory;
@property(nonatomic) int armed, taken, beats, stopped, restores, delegated;
@property(nonatomic) int64_t deadline;
@end
@implementation OHCFixtureLease
- (void)arm:(uint64_t)g deadline:(int64_t)d result:(void (^)(BOOL))r { (void)g; self.armed++; self.deadline=d; r(YES); }
- (void)takeover:(uint64_t)g result:(void (^)(BOOL))r { (void)g; self.taken++; r(YES); }
- (void)heartbeat:(uint64_t)g { (void)g; self.beats++; }
- (void)stopHeartbeat:(uint64_t)g { (void)g; self.stopped++; }
- (void)requestRestore:(uint64_t)g result:(void (^)(BOOL))r { (void)g; self.restores++; r(YES); }
- (void)delegateOnce:(uint64_t)g { (void)g; self.delegated++; }
@end
int openhc_scan_owner_fixture(const char *run_dir, const char *scenario) {
    NSString *caseName=[NSString stringWithUTF8String:scenario];
    OHCFixtureLease *lease=[OHCFixtureLease new];
    lease.privateRunDirectory=[NSString stringWithUTF8String:run_dir];
    FILE *trace=fopen([[lease.privateRunDirectory stringByAppendingPathComponent:@"scan-events"] fileSystemRepresentation],"w");
    if(!trace) return 91;
    int fds[2]; if(socketpair(AF_UNIX,SOCK_STREAM,0,fds)) {fclose(trace); return 91;}
    int client=fds[1];
    OHCScanOwnerForeground *foreground=[[OHCScanOwnerForeground alloc] initWithConnectedDescriptor:client];
    if(!foreground){close(fds[0]);fclose(trace);return 91;}
    OHCBHostIdentity *host=[[OHCBHostIdentity alloc] initWithModelId:@"A1B2C3" subModelId:@"D4" brand:@"Synthetic" deviceName:@"Synthetic"];
    OHCBScanReceiverConfig *config=[[OHCBScanReceiverConfig alloc] initWithHost:host bluetoothAddress:@"A0:B1:C2:D3:E4:F5" supportsUsb:NO lifetimeMillis:2000];
    fe35_bridge_input input={0};
    strcpy(input.device_id,"CD1C73F369C5FE0B80808D3D0335EAF7D99B2AB9FE15403DC621C166FBADCB6F");
    input.root_key_size=input.const_a_size=input.const_b_size=16;
    for(int i=0;i<16;i++){input.const_a[i]=(uint8_t)(0x10+i); input.const_b[i]=(uint8_t)(0x20+i);}
    OHCScanOwnerRuntime *runtime=[[OHCScanOwnerRuntime alloc] initWithConfig:config bridgeInput:&input lease:lease];
    memset(&input,0,sizeof(input));
    dispatch_semaphore_t done=dispatch_semaphore_create(0);
    __block _Atomic int invalid=0;
    __block int ready=0,clear=0,closeCount=0,cleaned=0,coreClear=0,handoff=0;
    __block BOOL returned=NO;
    __block int foregroundReady=0, foregroundClear=0;
    UIImageView *qrView=[UIImageView new]; UILabel *pinLabel=[UILabel new];
    __block NSString *pin=nil;
    void (^stop)(void)=^{
        dispatch_async(dispatch_get_main_queue(),^{
            if([caseName isEqualToString:@"background"])[foreground background];else[foreground stop];
        });
    };
    foreground.publication=^(NSString *kind,uint64_t g,NSString *qr,NSString *value){
        if(!NSThread.isMainThread || g>1)invalid=1;
        if([kind isEqualToString:@"PAIRING_READY"]){
            foregroundReady++;if(!qr || value.length!=6)invalid=1;
            qrView.image=OHCScanQRCode(qr,3,NULL);pinLabel.text=value;
            if(!qrView.image || pinLabel.text.length!=6)invalid=1;
            if([caseName isEqualToString:@"ready_stop"] || [caseName isEqualToString:@"background"])stop();
            if([caseName isEqualToString:@"disconnect"])shutdown(client,SHUT_WR);
        }
        if([kind isEqualToString:@"CLEAR_PAIRING"]){foregroundClear++;qrView.image=nil;pinLabel.text=nil;}
    };
    runtime.clearPairing=^(uint64_t g){ if(g!=1)invalid=1; coreClear++; };
    runtime.events=^(NSArray<OHCBScanReceiverEvent *> *events){
        for(OHCBScanReceiverEvent *e in events){
            fprintf(trace,"EVENT=%s\n",e.kind.UTF8String);
            if(e.generation!=1) invalid=1;
            if([e.kind isEqualToString:@"PAIRING_READY"]){
                ready++; pin=[e.pinCode copy];
                if(!e.qrCode || pin.length!=6)invalid=1;
            }
            if([e.kind isEqualToString:@"CLEAR_PAIRING"])clear++;
            if([e.kind isEqualToString:@"CLOSE_CONTROL_TRANSPORT"]){
                closeCount++;int expectedClear=[caseName isEqualToString:@"success"]?2:1;
                if(!coreClear || clear!=expectedClear)invalid=1;
            }
            if([e.kind isEqualToString:@"AUTH_HANDOFF"]){handoff++;if(![pin isEqualToString:e.pinCode] || !coreClear)invalid=1;}
        } fflush(trace);
    };
    runtime.testNativeCallback=^(NSString *kind){
        if(![kind isEqualToString:@"TICK"])fprintf(trace,"CALLBACK=%s\n",kind.UTF8String);
        if([kind isEqualToString:@"CLEANED"]){cleaned++;if(returned || closeCount!=1)invalid=1;}
        fflush(trace);
    };
    runtime.finished=^(fe35_scan_completion c,BOOL delegated){
        returned=c.returned;
        BOOL expectedCleanup=[@[@"ready_stop",@"ready_timeout",@"background",@"disconnect",@"rfcomm_failure",@"sdp_failure",@"success"] containsObject:caseName];
        int expectedReady=[@[@"ready_stop",@"ready_timeout",@"background",@"disconnect",@"cleanup_failure",@"success"] containsObject:caseName];
        int expectedStatus=[caseName isEqualToString:@"success"]?0:1;
        fprintf(trace,"COMPLETION=%d,%d,%d\n",c.returned,c.cleanup_confirmed,c.status);
        fprintf(trace,"COUNTS=%d,%d,%d,%d\n",ready,clear,closeCount,cleaned);
        fprintf(trace,"OWNER_BOUNDARIES=synthetic-OS-and-lease-real-owner-native-common\n");
        fprintf(trace,"OWNER_HANDOFF_SAME_PIN=%d\n",handoff);
        if(!c.returned || c.cleanup_confirmed!=expectedCleanup || c.status!=expectedStatus ||
           ready!=expectedReady || clear!=([caseName isEqualToString:@"success"]?2:1) || closeCount!=1 || cleaned!=1 || coreClear!=1 ||
           delegated==expectedCleanup || lease.armed!=1 || lease.taken!=1 || lease.stopped!=1 ||
           handoff!=[caseName isEqualToString:@"success"]) invalid=1;
        /* Independent fake recovery observation, explicitly not native CLEANED. */
        [runtime observeVerifiedRecovery:YES generation:1];
        fflush(trace); dispatch_semaphore_signal(done);
    };
    ohc_owner_peer p={0};p.connection=1;p.endpoint_device=1;p.endpoint_inode=1;p.policy_epoch=0x54455354;
    p.kernel_verified=p.endpoint_verified=true;p.token[1]=p.token[2]=501;p.token[5]=123;p.token[7]=10;
    [runtime acceptTestDescriptor:fds[0] evidence:p];
    /* Foreground Start on the actual bounded endpoint. No PID/role,
     * path, identity or guard truth is sent by the foreground side. */
    [foreground start];
    if([caseName isEqualToString:@"stop_rfcomm_wait"] || [caseName isEqualToString:@"stop_sdp_wait"]){
        /* The host marker follows the actual registration command. Do not race
         * a main-queue Stop against construction of the next native request. */
        NSString *marker=[lease.privateRunDirectory stringByAppendingPathComponent:@"stop"];
        for(int n=0;n<800 && access(marker.fileSystemRepresentation,F_OK);n++)
            [[NSRunLoop currentRunLoop] runUntilDate:[NSDate dateWithTimeIntervalSinceNow:.01]];
        if(access(marker.fileSystemRepresentation,F_OK))invalid=1;
        stop();
    }
    NSDate *limit=[NSDate dateWithTimeIntervalSinceNow:15];
    long waitResult;
    while((waitResult=dispatch_semaphore_wait(done,DISPATCH_TIME_NOW)) && limit.timeIntervalSinceNow>0)
        [[NSRunLoop currentRunLoop] runUntilDate:[NSDate dateWithTimeIntervalSinceNow:.01]];
    if(waitResult){
        /* Process exits; do not free borrowed callback state underneath worker. */
        _exit(95);
    }
    /* Barrier: final callback still owns fixture storage; get test count via the
     * serial queue before closing trace or dropping retained event/sink objects. */
    if(runtime.testHandoffCount!=handoff)invalid=1;
    runtime.finished=nil;runtime.events=nil;runtime.testNativeCallback=nil;runtime.clearPairing=nil;
    /* Drain bounded owner frames, then local foreground teardown synchronously
     * invalidates even if remote CLEAR was not delivered before disconnect. */
    [[NSRunLoop currentRunLoop] runUntilDate:[NSDate dateWithTimeIntervalSinceNow:.08]];
    [foreground stop];
    if(!foregroundClear || foregroundReady>1)invalid=1;
    if(qrView.image || pinLabel.text.length)invalid=1;
    if([@[@"ready_stop",@"background",@"disconnect",@"ready_timeout"] containsObject:caseName] && foregroundReady!=1)invalid=1;
    fprintf(trace,"OWNER_FOREGROUND_CLEAR_OK=1\n");
    fclose(trace);
    return invalid?96:0;
}
