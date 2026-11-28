/* Only OS admission/daemon/lease effects are synthetic. The owner runtime,
 * framing, completion/recovery decisions, C transport and Kotlin are production
 * sources. Never linked into a shipped helper or enabled by runtime flags. */
#import "../theos/scan-owner/ScanOwnerRuntime.h"
#import "../theos/scan-owner/ScanOwnerForeground.h"
#ifdef OPENHC_SCAN_OWNER_PROCESS_TEST
#import "../theos/scan-owner/ScanProcessLeaseAdapter.h"
#include <netinet/in.h>
#endif
#import <UIKit/UIKit.h>
#import "../theos/scan-ui/ScanQRCode.h"
#include <sys/socket.h>
#include <unistd.h>
#include <stdio.h>
#include <string.h>
#include <stdatomic.h>
int openhc_fe36_auth_fixture(OHCBScanReceiverEvent *handoff);
/* Static labels only: never include QR, PIN, keys or identity in diagnostics. */
#define OWNER_CHECK(condition, label) do { \
    if (!(condition)) { \
        invalid=1; \
        fprintf(trace,"OWNER_ASSERT_FAIL=%s line=%d\n",label,__LINE__); \
        fflush(trace); \
    } \
} while (0)

/* OWNER_GUARD_EVIDENCE_BEGIN: pure C, exercised by test-scan-owner.py.
 * Read only at typed completion, never in the native packet loop. The existing
 * test-only owner log is an observation, not recovery authority. Fail closed
 * on missing/truncated/contradictory evidence; never print its contents here. */
static int fixture_guard_decision(const char *path, bool cleanup, bool delegated) {
    FILE *file=fopen(path,"r");
    if(!file) return 0;
    struct { int count, state, order; long long now, phase; } effects[10]={0};
    char line[512]; int lines=0, sequence=0, expiry=0, expiryOrder=0, valid=1;
    long long last=-1, lease=-1, expiryNow=-1, expiryDeadline=-1;
    while(fgets(line,sizeof(line),file)) {
        if(++lines>4096 || !strchr(line,'\n')) { valid=0; break; }
        if(!strncmp(line,"OWNER_PHASE ",12)) {
            int e,s,w,n=0; unsigned long long g; long long now,d,p;
            if(sscanf(line,"OWNER_PHASE effect=%d state=%d generation=%llu now=%lld deadline=%lld phase_deadline=%lld worker_started=%d%n",
                &e,&s,&g,&now,&d,&p,&w,&n)!=7 || strcmp(line+n,"\n") ||
                e<0 || e>9 || s<0 || s>6 || g!=1 || now<last || now<0 ||
                d<=0 || p<0 || (w!=0 && w!=1) || (lease!=-1 && lease!=d)) { valid=0; break; }
            lease=d; last=now; ++sequence;
            effects[e].count++; effects[e].state=s; effects[e].order=sequence;
            effects[e].now=now; effects[e].phase=p;
        } else if(!strncmp(line,"OWNER_EXPIRY ",13)) {
            int s,n=0; long long now,p;
            if(sscanf(line,"OWNER_EXPIRY cause=phase state=%d now=%lld phase_deadline=%lld%n",
                &s,&now,&p,&n)!=3 || strcmp(line+n,"\n") || s!=OHC_STOPPING ||
                now<last || now<p || p<=0 || ++expiry!=1) { valid=0; break; }
            last=now; expiryNow=now; expiryDeadline=p; expiryOrder=++sequence;
        }
    }
    if(ferror(file)) valid=0;
    fclose(file);
    const int once[]={OHC_ARM_GUARD,OHC_TAKEOVER,OHC_RUN_WORKER,OHC_CLEAR,OHC_CANCEL_WORKER,OHC_STOP_HEARTBEAT};
    for(unsigned i=0;i<sizeof(once)/sizeof(*once);i++) {
        int e=once[i]; if(effects[e].count!=1) valid=0;
        if(i && effects[once[i-1]].order>=effects[e].order) valid=0;
    }
    const int states[]={OHC_ARMING,OHC_TAKING,OHC_RUNNING,OHC_RUNNING,OHC_RUNNING,OHC_STOPPING};
    for(unsigned i=0;i<sizeof(once)/sizeof(*once);i++)
        if(effects[once[i]].state!=states[i]) valid=0;
    if(!valid || effects[OHC_HEARTBEAT].count<1 || effects[OHC_RELEASED].count>1 ||
        effects[OHC_STOP_HEARTBEAT].state!=OHC_STOPPING) return 0;
    long long stopDeadline=effects[OHC_STOP_HEARTBEAT].phase;
    /* CANCEL's log samples the clock inside the effect; stop() assigns its
     * deadline from the earlier tick, so equality to sampled-now+1000 is wrong. */
    if(stopDeadline<1000 || stopDeadline-1000>effects[OHC_CANCEL_WORKER].now ||
        stopDeadline>=lease) return 0;
    int decision=delegated?OHC_DELEGATE_GUARD:OHC_REQUEST_RESTORE;
    if(effects[decision].count!=1 || effects[delegated?OHC_REQUEST_RESTORE:OHC_DELEGATE_GUARD].count ||
        effects[decision].order<=effects[OHC_STOP_HEARTBEAT].order ||
        effects[decision].state!=(delegated?OHC_DELEGATED:OHC_RESTORING) ||
        (effects[OHC_RELEASED].count && effects[OHC_RELEASED].order<=effects[decision].order)) return 0;
    if(!cleanup) return delegated?3:0;
    if(delegated) {
        if(expiry!=1 || expiryDeadline!=stopDeadline || expiryOrder<=effects[OHC_CANCEL_WORKER].order ||
            expiryOrder>=effects[OHC_STOP_HEARTBEAT].order ||
            effects[decision].phase!=stopDeadline || effects[decision].now<expiryNow) return 0;
        return 2; /* confirmed cleanup after observed STOPPING expiry */
    }
    /* RESTORING records the exact completion tick as its fixed deadline-3000.
     * The log's separately sampled wall time may cross STOPPING's deadline. */
    long long completed=effects[decision].phase-3000;
    return !expiry && completed>=stopDeadline-1000 && completed<stopDeadline &&
        effects[decision].now>=completed ? 1:0;
}
/* OWNER_GUARD_EVIDENCE_END */

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
    BOOL processLease=[caseName hasPrefix:@"process_"];
    if(processLease) { caseName=[caseName substringFromIndex:8]; }
    NSString *directory=[NSString stringWithUTF8String:run_dir];
    OHCFixtureLease *synthetic=[OHCFixtureLease new]; synthetic.privateRunDirectory=directory;
    id<OHCScanLeaseAdapter> lease=synthetic;
#ifdef OPENHC_SCAN_OWNER_PROCESS_TEST
    if(processLease) {
        /* Test-only loopback relay to host broker/guard, never app admission.
         * No production factory reads this file or accepts a TCP grant. */
        NSString *portText=[NSString stringWithContentsOfFile:[directory stringByAppendingPathComponent:@"process-port"]
            encoding:NSASCIIStringEncoding error:NULL];
        int port=portText.intValue;
        if(port<=0||port>65535) { return 91; }
        int fd=socket(AF_INET,SOCK_STREAM,0);
        struct sockaddr_in address={0}; address.sin_family=AF_INET;
        address.sin_port=htons((uint16_t)port); address.sin_addr.s_addr=htonl(INADDR_LOOPBACK);
        if(fd<0||connect(fd,(struct sockaddr *)&address,sizeof(address))) { if(fd>=0) { close(fd); } return 91; }
        lease=[[OHCScanProcessLeaseAdapter alloc] initWithTestDescriptor:fd runDirectory:directory];
        if(!lease) { return 91; }
    }
#else
    if(processLease) { return 91; }
#endif
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
#ifdef OPENHC_SCAN_OWNER_PROCESS_TEST
    OWNER_CHECK([OHCScanProcessLeaseAdapter productionAdapter]==nil,"production_process_factory_unconditionally_disabled");
#endif
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
        OWNER_CHECK(NSThread.isMainThread && g<=1,"foreground_main_thread_generation");
        if([kind isEqualToString:@"PAIRING_READY"]){
            foregroundReady++;
            OWNER_CHECK(qr && value.length==6,"foreground_pairing_shape");
            qrView.image=OHCScanQRCode(qr,3,NULL);pinLabel.text=value;
            OWNER_CHECK(qrView.image && pinLabel.text.length==6,"foreground_qr_render");
            if([caseName isEqualToString:@"ready_stop"] || [caseName isEqualToString:@"background"])stop();
            if([caseName isEqualToString:@"disconnect"])shutdown(client,SHUT_WR);
        }
        if([kind isEqualToString:@"CLEAR_PAIRING"]){foregroundClear++;qrView.image=nil;pinLabel.text=nil;}
    };
    runtime.clearPairing=^(uint64_t g){
        OWNER_CHECK(g==1,"core_clear_generation");
        coreClear++;fprintf(trace,"OWNER_CORE_CLEAR\n");fflush(trace);
    };
    runtime.events=^(NSArray<OHCBScanReceiverEvent *> *events){
        for(OHCBScanReceiverEvent *e in events){
            fprintf(trace,"EVENT=%s\n",e.kind.UTF8String);
            OWNER_CHECK(e.generation==1,"common_event_generation");
            if([e.kind isEqualToString:@"PAIRING_READY"]){
                ready++; pin=[e.pinCode copy];
                OWNER_CHECK(e.qrCode && pin.length==6,"common_pairing_shape");
            }
            if([e.kind isEqualToString:@"CLEAR_PAIRING"]){
                clear++;
                OWNER_CHECK(coreClear==1,"owner_revoke_before_common_clear");
            }
            if([e.kind isEqualToString:@"CLOSE_CONTROL_TRANSPORT"]){
                closeCount++;int expectedClear=[caseName isEqualToString:@"success"]?2:1;
                OWNER_CHECK(coreClear!=0,"owner_revoke_before_common_close");
                OWNER_CHECK(clear==expectedClear,"common_clear_before_transport_close");
            }
            if([e.kind isEqualToString:@"AUTH_HANDOFF"]){
                handoff++;
                OWNER_CHECK([pin isEqualToString:e.pinCode],"handoff_same_pin");
                OWNER_CHECK(coreClear!=0,"handoff_after_owner_revoke");
                /* Real owner/common event and original PIN enter the actual
                 * exported auth bridge. Separately coded test phone, real crypto
                 * and socket bytes; no radio or production listener enabled. */
                OWNER_CHECK(openhc_fe36_auth_fixture(e)==0,"real_fe36_auth_bridge_exchange");
            }
        } fflush(trace);
    };
    runtime.testNativeCallback=^(NSString *kind){
        if(![kind isEqualToString:@"TICK"])fprintf(trace,"CALLBACK=%s\n",kind.UTF8String);
        if([kind isEqualToString:@"CLEANED"]){
            cleaned++;
            OWNER_CHECK(!returned,"cleaned_before_typed_return");
            OWNER_CHECK(closeCount==1,"common_close_before_cleaned");
        }
        fflush(trace);
    };
    runtime.finished=^(fe35_scan_completion c,BOOL delegated){
        returned=c.returned;
        BOOL expectedCleanup=[@[@"ready_stop",@"ready_timeout",@"background",@"disconnect",@"rfcomm_failure",@"sdp_failure",@"success"] containsObject:caseName];
        int expectedReady=[@[@"ready_stop",@"ready_timeout",@"background",@"disconnect",@"cleanup_failure",@"success"] containsObject:caseName];
        int expectedStatus=[caseName isEqualToString:@"success"]?0:1;
        fprintf(trace,"COMPLETION=%d,%d,%d\n",c.returned,c.cleanup_confirmed,c.status);
        fprintf(trace,"COUNTS=%d,%d,%d,%d\n",ready,clear,closeCount,cleaned);
        fprintf(trace,"OWNER_BOUNDARIES=%s\n",processLease?
            "real-owner-native-common-private-channel-guard-process;injected-OS-admission-and-inert-Trial":
            "synthetic-OS-and-lease-real-owner-native-common");
        fprintf(trace,"OWNER_HANDOFF_SAME_PIN=%d\n",handoff);
        OWNER_CHECK(c.returned,"worker_returned");
        OWNER_CHECK(c.cleanup_confirmed==expectedCleanup,"cleanup_certainty");
        OWNER_CHECK(c.status==expectedStatus,"native_status");
        OWNER_CHECK(ready==expectedReady,"dual_ready_count");
        OWNER_CHECK(clear==([caseName isEqualToString:@"success"]?2:1),"common_clear_count");
        OWNER_CHECK(closeCount==1,"common_close_once");
        OWNER_CHECK(cleaned==1,"cleaned_once");
        OWNER_CHECK(coreClear==1,"owner_core_clear_once");
        fflush(stderr);
        NSString *statusPath=[[directory stringByDeletingLastPathComponent]
            stringByAppendingPathComponent:@"fe35-cli-status.log"];
        int guardDecision=fixture_guard_decision(statusPath.fileSystemRepresentation,expectedCleanup,delegated);
        fprintf(trace,"OWNER_GUARD_DECISION=%d\n",guardDecision);
        OWNER_CHECK(guardDecision!=0,"cleanup_controls_guard_decision");
        if(!processLease) {
            OWNER_CHECK(synthetic.armed==1,"guard_armed_once");
            OWNER_CHECK(synthetic.taken==1,"lease_taken_once");
            OWNER_CHECK(synthetic.stopped==1,"sole_heartbeat_stopped_once");
            OWNER_CHECK(synthetic.restores==!delegated,"guard_restore_exactly_once_or_none");
            OWNER_CHECK(synthetic.delegated==delegated,"guard_delegate_exactly_once_or_none");
        }
        OWNER_CHECK(handoff==[caseName isEqualToString:@"success"],"handoff_one_shot");
        /* Independent fake recovery observation, explicitly not native CLEANED. */
        if(!processLease) { [runtime observeVerifiedRecovery:YES generation:1]; }
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
        OWNER_CHECK(!access(marker.fileSystemRepresentation,F_OK),"registration_marker_observed");
        stop();
    }
    NSDate *limit=[NSDate dateWithTimeIntervalSinceNow:15];
    long waitResult;
    while((waitResult=dispatch_semaphore_wait(done,DISPATCH_TIME_NOW)) && limit.timeIntervalSinceNow>0)
        [[NSRunLoop currentRunLoop] runUntilDate:[NSDate dateWithTimeIntervalSinceNow:.01]];
    if(waitResult){
        /* Process exits; do not free borrowed callback state underneath worker. */
        fprintf(trace,"OWNER_ASSERT_FAIL=bounded_completion_process_exit status=95\n");
        fflush(trace);
        fprintf(stderr,"OWNER_FIXTURE_EXIT=95 scenario=%s\n",scenario); fflush(stderr);
        _exit(95);
    }
    /* Barrier: final callback still owns fixture storage; get test count via the
     * serial queue before closing trace or dropping retained event/sink objects. */
    OWNER_CHECK(runtime.testHandoffCount==handoff,"final_callback_lifetime_barrier");
#ifdef OPENHC_SCAN_OWNER_PROCESS_TEST
    if(processLease) {
        dispatch_semaphore_t flushed=dispatch_semaphore_create(0);
        [(OHCScanProcessLeaseAdapter *)lease testFlush:^{ dispatch_semaphore_signal(flushed); }];
        OWNER_CHECK(!dispatch_semaphore_wait(flushed,dispatch_time(DISPATCH_TIME_NOW,3*NSEC_PER_SEC)),"private_adapter_completion_flush");
    }
#endif
    runtime.finished=nil;runtime.events=nil;runtime.testNativeCallback=nil;runtime.clearPairing=nil;
    /* Drain bounded owner frames, then local foreground teardown synchronously
     * invalidates even if remote CLEAR was not delivered before disconnect. */
    [[NSRunLoop currentRunLoop] runUntilDate:[NSDate dateWithTimeIntervalSinceNow:.08]];
    [foreground stop];
    OWNER_CHECK(foregroundClear && foregroundReady<=1,"foreground_clear_and_single_ready");
    OWNER_CHECK(!qrView.image && !pinLabel.text.length,"foreground_no_stale_pairing");
    if([@[@"ready_stop",@"background",@"disconnect",@"ready_timeout"] containsObject:caseName])
        OWNER_CHECK(foregroundReady==1,"foreground_expected_ready");
    fprintf(trace,"OWNER_FOREGROUND_CLEAR_OK=1\n");
    fclose(trace);
    return invalid?96:0;
}
