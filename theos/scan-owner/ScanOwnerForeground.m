#import "ScanOwnerForeground.h"
#import <UIKit/UIKit.h>
#include <sys/socket.h>
#include <fcntl.h>
#include <unistd.h>
#include <errno.h>
#include <string.h>
@interface OHCScanOwnerForeground ()
- (void)fail;
- (void)readFrames;
- (void)backgroundNotification:(NSNotification *)notification;
@end
@implementation OHCScanOwnerForeground {
    int _fd;
    dispatch_queue_t _io;
    dispatch_source_t _timer;
    NSMutableData *_input;
    BOOL _started, _accepting, _pairing;
    uint64_t _generation;
}
- (instancetype)initWithConnectedDescriptor:(int)fd {
    NSAssert(NSThread.isMainThread,@"foreground constructed on main");
    if((self=[super init])) {
        _fd=fd; int flags=fcntl(fd,F_GETFL),one=1;
        if(flags<0 || fcntl(fd,F_SETFD,FD_CLOEXEC) || fcntl(fd,F_SETFL,flags|O_NONBLOCK) ||
           setsockopt(fd,SOL_SOCKET,SO_NOSIGPIPE,&one,sizeof(one))) {close(fd);_fd=-1;return nil;}
        _io=dispatch_queue_create("org.openhc.scan-foreground.io",DISPATCH_QUEUE_SERIAL);
        _input=[NSMutableData data];
        [NSNotificationCenter.defaultCenter addObserver:self selector:@selector(backgroundNotification:)
            name:UIApplicationWillResignActiveNotification object:nil];
    } return self;
}
- (void)clear {
    NSAssert(NSThread.isMainThread,@"foreground lifecycle on main");
    _pairing=NO;
    if(self.publication)self.publication(@"CLEAR_PAIRING",_generation,nil,nil);
}
- (void)invalidate:(const char *)frame {
    NSAssert(NSThread.isMainThread,@"foreground lifecycle on main");
    _accepting=NO;[self clear];
    dispatch_async(_io,^{
        if(self->_fd>=0) {
            if(frame){ssize_t n=send(self->_fd,frame,strlen(frame),0);(void)n;}
            shutdown(self->_fd,SHUT_RDWR);close(self->_fd);self->_fd=-1;
        }
        if(self->_timer)dispatch_source_cancel(self->_timer);
        [self->_input setLength:0];
    });
}
- (void)stop {[self invalidate:"STOP\n"];}
- (void)background {[self invalidate:"BACKGROUND\n"];}
- (void)backgroundNotification:(NSNotification *)notification {(void)notification;[self background];}
- (void)start {
    NSAssert(NSThread.isMainThread,@"foreground Start on main");
    if(_started)return;_started=YES;_accepting=_pairing=YES;
    dispatch_async(_io,^{
        if(self->_fd<0 || send(self->_fd,"START\n",6,0)!=6){[self fail];return;}
        self->_timer=dispatch_source_create(DISPATCH_SOURCE_TYPE_TIMER,0,0,self->_io);
        dispatch_source_set_timer(self->_timer,dispatch_time(DISPATCH_TIME_NOW,0),20*NSEC_PER_MSEC,2*NSEC_PER_MSEC);
        __weak OHCScanOwnerForeground *weak=self;
        dispatch_source_set_event_handler(self->_timer,^{[weak readFrames];});dispatch_resume(self->_timer);
    });
}
- (void)fail {dispatch_async(dispatch_get_main_queue(),^{[self invalidate:NULL];});}
- (void)readFrames {
    if(_fd<0)return;
    uint8_t bytes[4096];ssize_t count=recv(_fd,bytes,sizeof(bytes),0);
    if(count==0 || (count<0 && errno!=EAGAIN && errno!=EWOULDBLOCK && errno!=EINTR)){[self fail];return;}
    if(count>0)[_input appendBytes:bytes length:(NSUInteger)count];
    if(_input.length>8192){[self fail];return;}
    for(int i=0;i<16 && _input.length>=4;i++) {
        const uint8_t *p=_input.bytes;
        uint32_t size=((uint32_t)p[0]<<24)|((uint32_t)p[1]<<16)|((uint32_t)p[2]<<8)|p[3];
        if(!size || size>4096){[self fail];return;}
        if(_input.length<4+size)return;
        NSData *body=[_input subdataWithRange:NSMakeRange(4,size)];
        [_input replaceBytesInRange:NSMakeRange(0,4+size) withBytes:NULL length:0];
        id object=[NSJSONSerialization JSONObjectWithData:body options:0 error:NULL];
        if(![object isKindOfClass:NSDictionary.class]){[self fail];return;}
        NSDictionary *e=object; NSString *kind=e[@"kind"];NSNumber *gen=e[@"generation"];
        if(![kind isKindOfClass:NSString.class] || ![gen isKindOfClass:NSNumber.class] || !gen.unsignedLongLongValue ||
           ![@[@"STARTED",@"PAIRING_READY",@"CLEAR_PAIRING",@"AUTH_HANDOFF"] containsObject:kind]){[self fail];return;}
        NSString *qr=e[@"qr"],*pin=e[@"pin"];
        if([kind isEqualToString:@"PAIRING_READY"] &&
           (![qr isKindOfClass:NSString.class] || [qr lengthOfBytesUsingEncoding:NSUTF8StringEncoding]>2048 ||
            ![pin isKindOfClass:NSString.class] || pin.length!=6 ||
            [pin rangeOfCharacterFromSet:NSCharacterSet.decimalDigitCharacterSet.invertedSet].location!=NSNotFound)){
            [self fail];return;
        }
        dispatch_async(dispatch_get_main_queue(),^{
            if(!self->_accepting)return;
            uint64_t g=gen.unsignedLongLongValue;
            if([kind isEqualToString:@"STARTED"]){
                if(self->_generation){[self invalidate:NULL];return;}
                self->_generation=g;return;
            }
            if(g!=self->_generation)return;
            if([kind isEqualToString:@"CLEAR_PAIRING"])[self clear];
            else if([kind isEqualToString:@"PAIRING_READY"]){
                if(self->_pairing && self.publication)self.publication(kind,g,qr,pin);
            }else if(self.publication)self.publication(kind,g,nil,nil);
        });
    }
}
- (void)dealloc {
    [NSNotificationCenter.defaultCenter removeObserver:self];
    if(_timer)dispatch_source_cancel(_timer);if(_fd>=0)close(_fd);
}
@end
