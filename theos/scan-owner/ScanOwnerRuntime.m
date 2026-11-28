#import "ScanOwnerRuntime.h"
#include <fcntl.h>
#include <sys/socket.h>
#include <errno.h>
#include <string.h>
#include <time.h>
#include <stdio.h>
#include <unistd.h>

static int64_t ownerNow(void) {
    struct timespec t; clock_gettime(CLOCK_MONOTONIC,&t);
    return (int64_t)t.tv_sec*1000+t.tv_nsec/1000000;
}
typedef struct { void *runtime; uint64_t owner_generation; } OHCScanWorkerContext;
@interface OHCScanOwnerRuntime () {
    ohc_owner _owner;
    ohc_owner_connection _connection;
    fe35_bridge_input _input;
    fe35_scan_binding _binding;
    int _client, _stop[2];
    uint64_t _nonce, _workerGeneration;
    int64_t _commonGeneration;
    dispatch_queue_t _executor, _worker;
    dispatch_source_t _timer;
    OHCBScanReceiverConfig *_config;
    OHCBScanReceiverSession *_session;
    id<OHCScanLeaseAdapter> _lease;
    NSString *_pairingPIN;
    BOOL _testEvidence;
    ohc_owner_peer _injectedEvidence;
    int _handoffCount;
    OHCScanOwnerRuntime *_keepAlive;
    NSMutableData *_output;
    BOOL _outputFailed;
    OHCBFe36AuthConfig *_authConfig;
    id<OHCBTrustStore> _authTrust;
    OHCScanOwnerKeySink _keySink;
    OHCFe36AuthTransport *_authTransport;
    id<OHCNearbyNetwork> _network;
    OHCWifiBoundary _wifiBoundary;
    OHCNearbyWifiTransport *_wifiTransport;
}
- (void)effect:(ohc_owner_effect)e generation:(uint64_t)g;
- (void)pollConnection;
- (void)consume:(NSArray<OHCBScanReceiverEvent *> *)events;
- (int)notify:(const char *)kind generation:(int64_t)g ownerGeneration:(uint64_t)captured channel:(int)channel now:(int64_t)now;
- (void)launchWorker;
- (void)failedLaunch:(int)status;
- (void)publishKind:(NSString *)kind generation:(uint64_t)g qr:(NSString *)qr pin:(NSString *)pin;
@end
static void ownerEffect(void *p, ohc_owner_effect e, uint64_t g, int64_t deadline) {
    (void)deadline;
    [(__bridge OHCScanOwnerRuntime *)p effect:e generation:g];
}
static void ownerSink(void *p, void *events) {
    [(__bridge OHCScanOwnerRuntime *)p consume:(__bridge NSArray *)events];
}
static int ownerNotify(void *p,int64_t g,const char *kind,int channel,int64_t now) {
    OHCScanWorkerContext *worker=p;
    return [(__bridge OHCScanOwnerRuntime *)worker->runtime notify:kind generation:g
        ownerGeneration:worker->owner_generation channel:channel now:now];
}
#ifdef OPENHC_SCAN_OWNER_TEST
static bool testAdmission(const ohc_owner_peer *p) { return p->policy_epoch == 0x54455354; }
#endif
@implementation OHCScanOwnerRuntime
- (instancetype)initWithConfig:(OHCBScanReceiverConfig *)config
                    bridgeInput:(const fe35_bridge_input *)input lease:(id<OHCScanLeaseAdapter>)lease {
    if (!config || !input || !lease || config.lifetimeMillis<=0 || config.lifetimeMillis>240000) return nil;
    if ((self=[super init])) {
        _config=config; _input=*input; _lease=lease;
        _client=_stop[0]=_stop[1]=-1;
        _output=[NSMutableData data];
        _executor=dispatch_queue_create("org.openhc.scan-owner.serial",DISPATCH_QUEUE_SERIAL);
        _worker=dispatch_queue_create("org.openhc.scan-owner.native",DISPATCH_QUEUE_SERIAL);
        ohc_owner_init(&_owner,ownerEffect,(__bridge void *)self);
        _timer=dispatch_source_create(DISPATCH_SOURCE_TYPE_TIMER,0,0,_executor);
        dispatch_source_set_timer(_timer,dispatch_time(DISPATCH_TIME_NOW,0),20*NSEC_PER_MSEC,2*NSEC_PER_MSEC);
        __weak OHCScanOwnerRuntime *weak=self;
        if([_lease respondsToSelector:@selector(setUnavailable:)]) {
            _lease.unavailable=^(uint64_t generation) {
                OHCScanOwnerRuntime *strong=weak;
                if(!strong) { return; }
                dispatch_async(strong->_executor,^{
                    if(generation!=strong->_owner.generation) { return; }
                    /* Revoke/cancel first, then retain fence and delegate. A
                     * lost guard is NOT independent execution-exit knowledge. */
                    (void)ohc_owner_transport_event(&strong->_owner,generation,"STOP",ownerNow());
                    ohc_owner_execution_exited(&strong->_owner,generation,false);
                });
            };
        }
        dispatch_source_set_event_handler(_timer,^{ [weak pollConnection]; });
        dispatch_resume(_timer);
    } return self;
}
- (void)acceptConnectedDescriptor:(int)fd {
    dispatch_async(_executor,^{
        if (self->_client>=0 || self->_owner.state!=OHC_IDLE || self->_nonce==UINT64_MAX) { close(fd); return; }
        int flags=fcntl(fd,F_GETFL);
        int one=1;
        if (flags<0 || fcntl(fd,F_SETFD,FD_CLOEXEC) || fcntl(fd,F_SETFL,flags|O_NONBLOCK) ||
            setsockopt(fd,SOL_SOCKET,SO_NOSIGPIPE,&one,sizeof(one))) { close(fd); return; }
        ohc_owner_peer p={0};
        if (!ohc_owner_collect_peer(fd,++self->_nonce,1,&p) || !ohc_owner_open(&self->_connection,&p)) { close(fd); return; }
        self->_client=fd;
    });
}
- (BOOL)configureAuthentication:(OHCBFe36AuthConfig *)config trust:(id<OHCBTrustStore>)trust
    keySink:(OHCScanOwnerKeySink)sink {
    if(!config || !trust || !sink) return NO;
    __block BOOL configured=NO;
    dispatch_sync(_executor,^{
        if(self->_owner.state!=OHC_IDLE || self->_authConfig || self->_client>=0) return;
        self->_authConfig=config; self->_authTrust=trust; self->_keySink=[sink copy]; configured=YES;
    }); return configured;
}
- (BOOL)configureContinuingAuthentication:(OHCBFe36AuthConfig *)config trust:(id<OHCBTrustStore>)trust
    network:(id<OHCNearbyNetwork>)network boundary:(OHCWifiBoundary)boundary {
    if(!config || !trust || !network || !boundary) return NO;
    __block BOOL configured=NO;
    dispatch_sync(_executor,^{
        if(self->_owner.state!=OHC_IDLE || self->_authConfig || self->_client>=0) return;
        self->_authConfig=config;self->_authTrust=trust;self->_network=network;
        self->_wifiBoundary=[boundary copy];configured=YES;
    });return configured;
}
#ifdef OPENHC_SCAN_OWNER_TEST
- (void)acceptTestDescriptor:(int)fd evidence:(ohc_owner_peer)evidence {
    dispatch_sync(_executor,^{
        NSAssert(self->_client<0 && self->_owner.state==OHC_IDLE,@"test single owner");
        self->_testEvidence=YES; self->_injectedEvidence=evidence;
        self->_owner.test_admit=testAdmission;
        NSAssert(!fcntl(fd,F_SETFD,FD_CLOEXEC) && !fcntl(fd,F_SETFL,O_NONBLOCK),@"test fd");
        int one=1;
        NSAssert(!setsockopt(fd,SOL_SOCKET,SO_NOSIGPIPE,&one,sizeof(one)),@"test SIGPIPE");
        NSAssert(ohc_owner_open(&self->_connection,&evidence),@"test evidence");
        self->_client=fd;
    });
}
- (int)testHandoffCount { __block int n; dispatch_sync(_executor,^{n=self->_handoffCount;}); return n; }
#endif
- (void)pollConnection {
    int64_t now=ownerNow();
    if (_client>=0) {
        if(_outputFailed) goto disconnect;
        ohc_owner_peer p={0}; BOOL valid=NO;
#ifdef OPENHC_SCAN_OWNER_TEST
        if (_testEvidence) { p=_injectedEvidence; valid=YES; }
#endif
        if (!valid) valid=ohc_owner_collect_peer(_client,_connection.peer.connection,1,&p);
        if (!valid || !ohc_owner_feed(&_owner,&_connection,&p,NULL,0,now)) goto disconnect;
        char frame[64]; ssize_t n=recv(_client,frame,sizeof(frame),0);
        if (n==0 || (n<0 && errno!=EAGAIN && errno!=EWOULDBLOCK && errno!=EINTR)) goto disconnect;
        if (n>0 && !ohc_owner_feed(&_owner,&_connection,&p,frame,(size_t)n,now)) goto disconnect;
        if (_output.length) {
            ssize_t written=send(_client,_output.bytes,_output.length,0);
            if(written>0) [_output replaceBytesInRange:NSMakeRange(0,(NSUInteger)written) withBytes:NULL length:0];
            else if(written==0 || (errno!=EAGAIN && errno!=EWOULDBLOCK && errno!=EINTR)) goto disconnect;
        }
    }
    ohc_owner_tick(&_owner,now); return;
disconnect:
    ohc_owner_disconnect(&_owner,&_connection,now); close(_client); _client=-1;
    [_output setLength:0];
    _outputFailed=NO;
    ohc_owner_tick(&_owner,now);
}
- (void)publishKind:(NSString *)kind generation:(uint64_t)g qr:(NSString *)qr pin:(NSString *)pin {
    if(_client<0 || !_connection.connected) return;
    NSMutableDictionary *frame=[@{@"kind":kind,@"generation":@(g)} mutableCopy];
    if(qr)frame[@"qr"]=qr;
    if(pin)frame[@"pin"]=pin;
    NSData *body=[NSJSONSerialization dataWithJSONObject:frame options:0 error:NULL];
    if(!body || body.length>4096 || _output.length+body.length+4>8192) {
        _outputFailed=YES; /* next poll cancels; effect handlers never re-enter */
        return;
    }
    uint32_t n=(uint32_t)body.length;
    uint8_t header[4]={(uint8_t)(n>>24),(uint8_t)(n>>16),(uint8_t)(n>>8),(uint8_t)n};
    [_output appendBytes:header length:4];[_output appendData:body];
}
- (void)observeVerifiedRecovery:(BOOL)verified generation:(uint64_t)generation {
    dispatch_async(_executor,^{ ohc_owner_recovered(&self->_owner,generation,verified); });
}
- (void)effect:(ohc_owner_effect)e generation:(uint64_t)g {
#ifdef OPENHC_SCAN_OWNER_PROCESS_TEST
    fprintf(stderr,"OWNER_PHASE effect=%d state=%d generation=%llu now=%lld deadline=%lld phase_deadline=%lld worker_started=%d\n",
        (int)e,(int)_owner.state,(unsigned long long)g,(long long)ownerNow(),
        (long long)_owner.deadline,(long long)_owner.phase_deadline,_owner.worker_started);
#endif
    switch(e) {
    case OHC_ARM_GUARD: {
        _keepAlive=self;
        [self publishKind:@"STARTED" generation:g qr:nil pin:nil];
        [_lease arm:g deadline:_owner.deadline result:^(BOOL ready) {
            dispatch_async(self->_executor,^{
#ifdef OPENHC_SCAN_OWNER_PROCESS_TEST
                fprintf(stderr,"OWNER_ARM_RESULT ready=%d state=%d now=%lld phase_deadline=%lld\n",ready,
                    (int)self->_owner.state,(long long)ownerNow(),(long long)self->_owner.phase_deadline);
#endif
                ohc_owner_guard_ready(&self->_owner,g,ready,ownerNow());
            });
        }]; break;
    }
    case OHC_TAKEOVER: {
        [_lease takeover:g result:^(BOOL working) {
            dispatch_async(self->_executor,^{ohc_owner_working(&self->_owner,g,working,ownerNow());});
        }]; break;
    }
    case OHC_RUN_WORKER: {
        /* Defer: no state-machine reentrancy from an effect handler. */
        dispatch_async(_executor,^{
            if(self->_owner.state==OHC_RUNNING && self->_owner.generation==g) [self launchWorker];
            else if(self->_owner.generation==g) {
                /* Cancellation before queued launch: actual execution knowledge,
                 * no session/bridge/socket was created, not inferred from CLEANED. */
                fe35_scan_completion c={true,true,1};
                if([self->_lease respondsToSelector:@selector(workerCompletion:generation:executionExited:)]) {
                    [self->_lease workerCompletion:c generation:g executionExited:YES];
                }
                ohc_owner_completed(&self->_owner,g,c,true,ownerNow());
            }
        }); break;
    }
    case OHC_CLEAR:
        _pairingPIN=nil;
        [self publishKind:@"CLEAR_PAIRING" generation:g qr:nil pin:nil];
        if (self.clearPairing) self.clearPairing(g);
        break;
    case OHC_CANCEL_WORKER:
        [_authTransport cancel];
        /* Revoke private key immediately. Provider cleanup runs on worker, outside this executor,
         * so a slow platform provider cannot block Stop/lease heartbeats. */
        [_wifiTransport revoke];
        if (_stop[1]>=0) { ssize_t n=write(_stop[1],"S",1); (void)n; } break;
    case OHC_HEARTBEAT: [_lease heartbeat:g]; break;
    case OHC_STOP_HEARTBEAT: [_lease stopHeartbeat:g]; break;
    case OHC_REQUEST_RESTORE: {
        [_lease requestRestore:g result:^(BOOL verified) {
            dispatch_async(self->_executor,^{ohc_owner_recovered(&self->_owner,g,verified);});
        }]; break;
    }
    case OHC_DELEGATE_GUARD: [_lease delegateOnce:g]; break;
    case OHC_RELEASED: _keepAlive=nil; break;
    }
}
- (void)launchWorker {
    _workerGeneration=_owner.generation;
    if (pipe(_stop) || fcntl(_stop[0],F_SETFD,FD_CLOEXEC) ||
        fcntl(_stop[1],F_SETFD,FD_CLOEXEC) || fcntl(_stop[1],F_SETFL,O_NONBLOCK)) {
        [self failedLaunch:90]; return;
    }
    _session=[[OHCBScanReceiverSession alloc] initWithConfig:_config];
    NSArray *start=[_session startNowMillis:ownerNow()];
    _commonGeneration=_session.generation;
    _binding=(fe35_scan_binding){(__bridge void *)_session,(__bridge void *)self,ownerSink};
    [self consume:start];
    if(_authConfig) {
        __weak OHCScanOwnerRuntime *weak=self;
        const uint64_t ownerGeneration=_workerGeneration;
        if(_network) {
            _wifiTransport=[[OHCNearbyWifiTransport alloc] initWithNetwork:_network
                accept:^BOOL(OHCNearbyWifiTransport *adapter,int fd,int64_t now) {
                    (void)now;OHCScanOwnerRuntime *strong=weak;if(!strong)return NO;
                    __block BOOL accepted=NO;
                    dispatch_sync(strong->_executor,^{
                        [strong pollConnection];
                        int64_t current=ownerNow();ohc_owner_tick(&strong->_owner,current);
                        if(strong->_owner.generation!=ownerGeneration || strong->_owner.state!=OHC_RUNNING ||
                            strong->_owner.cancelled || strong->_wifiTransport!=adapter) return;
                        [strong consume:[strong->_session tickGeneration:strong->_commonGeneration nowMillis:current]];
                        if(strong->_owner.state==OHC_RUNNING && !strong->_owner.cancelled)
                            accepted=[adapter deliverTo:strong->_wifiBoundary owner:ownerGeneration descriptor:fd];
                    });return accepted;
                }];
            if(!_wifiTransport) {[self failedLaunch:93];return;}
        }
        _authTransport=[[OHCFe36AuthTransport alloc] initWithConfig:_authConfig trust:_authTrust
            commit:^BOOL(OHCFe36AuthTransport *adapter,int64_t incarnation,int64_t now) {
                (void)now; OHCScanOwnerRuntime *strong=weak; if(!strong) return NO;
                __block BOOL delivered=NO;
                dispatch_sync(strong->_executor,^{
                    [strong pollConnection]; /* drain queued Stop/background/EOF before promotion */
                    int64_t current=ownerNow(); ohc_owner_tick(&strong->_owner,current);
                    if(strong->_owner.generation!=ownerGeneration || strong->_owner.state!=OHC_RUNNING ||
                        strong->_owner.cancelled || strong->_authTransport!=adapter) return;
                    /* Common deadline, reversal and endpoint cancellation are
                     * processed under the same executor immediately before key. */
                    [strong consume:[strong->_session tickGeneration:strong->_commonGeneration nowMillis:current]];
                    if(strong->_owner.state==OHC_RUNNING && !strong->_owner.cancelled) {
                        __block BOOL stored=YES;
                        delivered=[adapter deliver:incarnation now:current sink:^(int64_t common,int64_t connection,const uint8_t key[16]) {
                            if(strong->_wifiTransport) {
                                stored=[strong->_wifiTransport storeKey:key];
                            } else strong->_keySink(ownerGeneration,common,connection,key);
                        }];
                        delivered=delivered && stored;
                    }
                }); return delivered;
            }];
        if(!_authTransport) { [self failedLaunch:92]; return; }
    }
    fe35_bridge_handle bridge=fe35_bridge_create(&_input);
    if (!bridge) {
        [self failedLaunch:91]; return;
    }
    const uint64_t ownerGeneration=_workerGeneration;
    const int64_t commonGeneration=_commonGeneration;
    NSString *runDirectory=[_lease.privateRunDirectory copy];
    OHCFe36AuthTransport *auth=self->_authTransport;
    OHCNearbyWifiTransport *wifi=self->_wifiTransport;
    /* Strong self capture retains session/binding/sink through final callback and
     * typed return. Worker only touches native; common callbacks sync to executor. */
    dispatch_async(_worker,^{ @autoreleasepool {
        OHCScanWorkerContext context={(__bridge void *)self,ownerGeneration};
        fe35_scan_transport t={&context,commonGeneration,self->_stop[0],ownerNotify};
        fe36_auth_transport a={0}; if(auth) a=[auth binding];
        fe35_wifi_transport w={0};if(wifi) w=[wifi binding];
        fe35_scan_completion completion=wifi ?
            openhc_btstack_scan_wifi_inbound(runDirectory.fileSystemRepresentation,bridge,&t,&a,&w) : auth ?
            openhc_btstack_scan_auth_inbound(runDirectory.fileSystemRepresentation,bridge,&t,&a) :
            openhc_btstack_scan_inbound(runDirectory.fileSystemRepresentation,bridge,&t);
        dispatch_async(self->_executor,^{
            if([self->_lease respondsToSelector:@selector(workerCompletion:generation:executionExited:)]) {
                [self->_lease workerCompletion:completion generation:ownerGeneration executionExited:YES];
            }
            ohc_owner_completed(&self->_owner,ownerGeneration,completion,true,ownerNow());
            /* Returned in-process worker is independent execution knowledge; it
             * does NOT prove daemon absence or successful restoration. */
            close(self->_stop[0]); close(self->_stop[1]); self->_stop[0]=self->_stop[1]=-1;
            self->_binding=(fe35_scan_binding){0}; self->_session=nil;
            self->_authTransport=nil;
            self->_wifiTransport=nil;
            if (self.finished) self.finished(completion,self->_owner.delegated);
        });
    }});
}
- (void)failedLaunch:(int)status {
    fe35_scan_completion c={true,false,status};
    if([_lease respondsToSelector:@selector(workerCompletion:generation:executionExited:)]) {
        [_lease workerCompletion:c generation:_workerGeneration executionExited:YES];
    }
    ohc_owner_completed(&_owner,_workerGeneration,c,true,ownerNow());
    if(_stop[0]>=0)close(_stop[0]);if(_stop[1]>=0)close(_stop[1]);_stop[0]=_stop[1]=-1;
    _binding=(fe35_scan_binding){0};_session=nil;
    [_authTransport cancel];_authTransport=nil;
    [_wifiTransport cancel];_wifiTransport=nil;
    if(self.finished)self.finished(c,_owner.delegated);
}
- (int)notify:(const char *)kind generation:(int64_t)g ownerGeneration:(uint64_t)captured channel:(int)channel now:(int64_t)now {
    (void)now;
    __block int result=1;
    dispatch_sync(_executor,^{
        if (!self->_session || g!=self->_commonGeneration || captured!=self->_workerGeneration ||
            captured!=self->_owner.generation) return;
#ifdef OPENHC_SCAN_OWNER_TEST
        if (self.testNativeCallback) self.testNativeCallback([NSString stringWithUTF8String:kind]);
#endif
        int64_t current=ownerNow(); /* one clock sampled on the serial executor */
        BOOL active=ohc_owner_transport_event(&self->_owner,self->_workerGeneration,kind,current);
        /* Even cancelled sessions receive final STOP/CLEANED and retain sink. */
        const char *forward=active || !strcmp(kind,"CLEANED") ? kind : "STOP";
        result=fe35_scan_notify(&self->_binding,g,forward,channel,current);
        if (!strcmp(kind,"ACCEPTED") && active) {
            [self consume:[self->_session takeAuthHandoffGeneration:g nowMillis:current]];
        }
    }); return result;
}
- (void)consume:(NSArray<OHCBScanReceiverEvent *> *)events {
    if (_workerGeneration!=_owner.generation) return;
    /* The sink runs on _executor after the core call has returned, never from
     * an effect handler. Preflight the whole common batch before forwarding
     * terminal CLEAR/CLOSE: scan expiry need not reach the owner lease deadline.
     * A nonterminal ACCEPTED CLEAR has no CLOSE and does not cancel handoff. */
    int64_t now=ownerNow();
    for (OHCBScanReceiverEvent *e in events) {
        if(e.generation==_commonGeneration)
            ohc_owner_common_event(&_owner,_workerGeneration,e.kind.UTF8String,now);
    }
    for (OHCBScanReceiverEvent *e in events) {
        if(e.generation!=_commonGeneration) continue;
        if([e.kind isEqualToString:@"PAIRING_READY"]) {
            if(!ohc_owner_pairing(&_owner,_workerGeneration)) continue;
            _pairingPIN=[e.pinCode copy];
            [self publishKind:e.kind generation:_workerGeneration qr:e.qrCode pin:e.pinCode];
        }
        if([e.kind isEqualToString:@"AUTH_HANDOFF"]) {
            /* PIN originates only from common; preserve before CLEAR at ACCEPTED
             * using the common handoff contract, never manufacture a new PIN. */
            if(!ohc_owner_handoff(&_owner,_workerGeneration)) continue;
            if(_authTransport) {
                NSNumber *commonDeadline=_session.deadlineMillis;
                int64_t deadline=commonDeadline ? MIN(_owner.deadline,commonDeadline.longLongValue) : 0;
                if((_wifiTransport && ![_wifiTransport handoffGeneration:_commonGeneration deadline:deadline]) ||
                   ![_authTransport handoff:e now:now deadline:deadline]) {
                    (void)ohc_owner_transport_event(&_owner,_workerGeneration,"STOP",now);
                    continue;
                }
            }
            _handoffCount++;
            [self publishKind:e.kind generation:_workerGeneration qr:nil pin:nil];
        }
        if(self.events) self.events(@[e]);
    }
}
- (void)dealloc {
    if(_timer) dispatch_source_cancel(_timer);
    if(_client>=0) close(_client);
    if(_stop[0]>=0) close(_stop[0]); if(_stop[1]>=0) close(_stop[1]);
    memset(&_input,0,sizeof(_input));
}
@end
