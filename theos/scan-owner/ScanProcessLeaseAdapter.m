#import "ScanProcessLeaseAdapter.h"
#include "ScanLeaseChannel.h"
#include <fcntl.h>
#include <unistd.h>
@interface OHCScanProcessLeaseAdapter () {
    ohc_lease_channel _channel;
    int _pending;
    dispatch_queue_t _io;
    BOOL _stopped, _delegated, _reported, _armed;
    NSString *_privateRunDirectory;
}
- (BOOL)exchange:(uint8_t)op generation:(uint64_t)generation flags:(uint32_t)flags status:(int)status;
@end
@implementation OHCScanProcessLeaseAdapter
+ (instancetype)productionAdapter {
    /* Even an inherited socket or root UID is not a deployed launch policy. */
    return nil;
}
#ifdef OPENHC_SCAN_OWNER_PROCESS_TEST
- (instancetype)initWithTestDescriptor:(int)fd runDirectory:(NSString *)directory {
    if(fd<0) { return nil; }
    if(!directory.length || fcntl(fd,F_SETFD,FD_CLOEXEC)) { close(fd); return nil; }
    if((self=[super init])) {
        _pending=fd; _channel=(ohc_lease_channel){.fd=-1};
        _privateRunDirectory=[directory copy];
        _io=dispatch_queue_create("org.openhc.scan-lease.private-io",DISPATCH_QUEUE_SERIAL);
    } else { close(fd); }
    return self;
}
- (void)testFlush:(void (^)(void))completion { dispatch_async(_io,completion); }
#endif
- (NSString *)privateRunDirectory { return _privateRunDirectory; }
- (BOOL)exchange:(uint8_t)op generation:(uint64_t)g flags:(uint32_t)flags status:(int)status {
    if(g!=_channel.generation || !_armed) { return NO; }
    BOOL ok=ohc_lease_exchange(&_channel,op,flags,status);
    if(!ok&&!_reported) {
        _reported=YES;
        if(self.unavailable) { self.unavailable(g); }
    }
    return ok;
}
- (void)arm:(uint64_t)g deadline:(int64_t)d result:(void (^)(BOOL))r {
    dispatch_async(_io,^{
        if(self->_armed) { r(NO); return; }
        int fd=self->_pending; self->_pending=-1;
        if(!ohc_lease_adopt(&self->_channel,fd,g,d)) { if(fd>=0) { close(fd); } r(NO); return; }
        self->_armed=YES; r([self exchange:OHC_L_ARM generation:g flags:0 status:0]);
    });
}
- (void)takeover:(uint64_t)g result:(void (^)(BOOL))r {
    dispatch_async(_io,^{ r([self exchange:OHC_L_TAKEOVER generation:g flags:0 status:0]); });
}
- (void)heartbeat:(uint64_t)g {
    dispatch_async(_io,^{ if(!self->_stopped) { (void)[self exchange:OHC_L_BEAT generation:g flags:0 status:0]; } });
}
- (void)stopHeartbeat:(uint64_t)g {
    dispatch_async(_io,^{ if(g==self->_channel.generation) { self->_stopped=YES; } });
}
- (void)workerCompletion:(fe35_scan_completion)c generation:(uint64_t)g executionExited:(BOOL)exited {
    uint32_t flags=(c.returned?OHC_L_RETURNED:0)|(c.cleanup_confirmed?OHC_L_CLEANUP:0)|(exited?OHC_L_EXITED:0);
    dispatch_async(_io,^{
        if(!self->_delegated) { (void)[self exchange:OHC_L_COMPLETE generation:g flags:flags status:c.status]; }
    });
}
- (void)requestRestore:(uint64_t)g result:(void (^)(BOOL))r {
    dispatch_async(_io,^{ r([self exchange:OHC_L_RESTORE generation:g flags:0 status:0]); });
}
- (void)delegateOnce:(uint64_t)g {
    dispatch_async(_io,^{
        if(g==self->_channel.generation&&!self->_delegated) {
            self->_delegated=YES; (void)[self exchange:OHC_L_DELEGATE generation:g flags:0 status:0];
        }
    });
}
- (void)dealloc {
    if(_pending>=0) { close(_pending); }
    ohc_lease_close(&_channel);
}
@end
