/* Actual production TCP pump; common batches/owner signals are explicitly injected.
 * Real loopback/stream, nonblocking backpressure and independent peer processes.
 * This does not claim Native crypto or device interoperability. */
#define OPENHC_BTSTACK_TEST
#define main openhc_unused_main
#include "../theos/btstack-probe.c"
#undef main
#include "fe35-control-bridge-test-stub.c"
#include <signal.h>
#include <sys/wait.h>

static void nonblocking(int fd) {
    int flags=fcntl(fd,F_GETFL);assert(flags>=0);
    assert(!fcntl(fd,F_SETFL,flags|O_NONBLOCK));assert(!protect_socket_sigpipe(fd));
}
static void pair(int sockets[2]) {
    int listener=socket(AF_INET,SOCK_STREAM,0);assert(listener>=0);
    struct sockaddr_in address={0};address.sin_family=AF_INET;
    assert(inet_pton(AF_INET,"127.0.0.1",&address.sin_addr)==1);
    assert(!bind(listener,(struct sockaddr *)&address,sizeof(address)) && !listen(listener,1));
    socklen_t size=sizeof(address);assert(!getsockname(listener,(struct sockaddr *)&address,&size));
    sockets[1]=socket(AF_INET,SOCK_STREAM,0);assert(sockets[1]>=0);
    assert(!connect(sockets[1],(struct sockaddr *)&address,sizeof(address)));
    sockets[0]=accept(listener,NULL,NULL);assert(sockets[0]>=0);close(listener);
    nonblocking(sockets[0]);assert(!protect_socket_sigpipe(sockets[1]));
}
static void joined(pid_t child) {
    int status;assert(waitpid(child,&status,0)==child && WIFEXITED(status) && WEXITSTATUS(status)==0);
}
static int notify(void *context,int64_t generation,const char *kind,int channel,int64_t now) {
    (void)generation;(void)channel;
    return !strcmp(kind,"TICK") && now>=*(int64_t *)context;
}
static void backpressure_and_cancel(void) {
    int sockets[2];pair(sockets);
    int small=1024;assert(!setsockopt(sockets[0],SOL_SOCKET,SO_SNDBUF,&small,sizeof(small)));
    uint8_t data[65500];memset(data,0x53,sizeof(data));
    size_t prefill=0;
    for(;;) {
        ssize_t n=send_without_sigpipe(sockets[0],data,sizeof(data));
        if(n<0) {assert(errno==EAGAIN || errno==EWOULDBLOCK);break;}
        assert(n>0);prefill+=(size_t)n;
    }
    assert(prefill>0);
    /* An already expired original owner must win before any writable progress;
     * do not infer exhaustion of the remote TCP window from one EAGAIN. */
    int64_t expiry=now_ms();
    fe35_scan_transport scan={&expiry,1,-1,notify};current_scan=&scan;scan_ended=0;
    int ended=0;
    assert(tcp_control_batch(sockets[0],set_event("SEND_FRAME",data,sizeof(data),NULL,0,0),&ended)==-1);
    current_scan=NULL;scan_ended=0;
    /* Cancellation can interrupt a partial write. Retire that whole connection;
     * never replay a batch on its partially written stream. Fresh pair below. */
    close(sockets[0]);close(sockets[1]);pair(sockets);
    assert(!setsockopt(sockets[0],SOL_SOCKET,SO_SNDBUF,&small,sizeof(small)));
    prefill=0;
    for(;;) {
        ssize_t n=send_without_sigpipe(sockets[0],data,sizeof(data));
        if(n<0) {assert(errno==EAGAIN || errno==EWOULDBLOCK);break;}
        assert(n>0);prefill+=(size_t)n;
    }
    pid_t child=fork();assert(child>=0);
    if(child==0) {
        alarm(4);close(sockets[0]);size_t total=prefill+sizeof(data);uint8_t part[37];
        while(total) {
            size_t want=total<sizeof(part)?total:sizeof(part);
            ssize_t n=read(sockets[1],part,want);if(n<0 && errno==EINTR)continue;
            assert(n>0);for(ssize_t i=0;i<n;i++)assert(part[i]==0x53);total-=(size_t)n;
        }
        close(sockets[1]);_exit(0);
    }
    close(sockets[1]);expiry=now_ms()+3000;current_scan=&scan;
    assert(!tcp_control_batch(sockets[0],set_event("SEND_FRAME",data,sizeof(data),NULL,0,0),&ended));
    current_scan=NULL;close(sockets[0]);joined(child);
}
static fe35_bridge_batch terminal_step(void *context,int tcp,const uint8_t *bytes,size_t size,int64_t now) {
    (void)context;(void)tcp;(void)now;
    memset(&batch,0,sizeof(batch));
    if(size) {
        assert(size==1 && bytes[0]==0x55);
        batch.count=2;strcpy(batch.events[0].kind,"SEND_FRAME");batch.events[0].frame[0]=0x66;
        batch.events[0].frame_size=1;strcpy(batch.events[1].kind,"TCP_DISCONNECT");
    }
    return &batch;
}
static void settled_fe35_and_ack(void) {
    int sockets[2],daemon[2];pair(sockets);assert(!socketpair(AF_UNIX,SOCK_STREAM,0,daemon));
    pid_t child=fork();assert(child>=0);
    if(child==0) {
        alarm(4);close(sockets[0]);close(daemon[0]);
        /* Exact BTstack close event; C must retain TCP and not request a second FE35 close. */
        uint8_t event[]={4,0,0,0,4,0,0x81,2,0x45,0x23};
        assert(write(daemon[1],event,sizeof(event))==(ssize_t)sizeof(event));
        uint8_t byte=0x55;assert(write(sockets[1],&byte,1)==1);
        assert(read(sockets[1],&byte,1)==1 && byte==0x66);
        close(sockets[1]);close(daemon[1]);_exit(0);
    }
    close(sockets[1]);close(daemon[1]);
    int64_t expiry=now_ms()+3000;fe35_scan_transport scan={&expiry,1,-1,notify};
    current_scan=&scan;scan_ended=0;
    fe35_wifi_transport wifi={0};wifi.tcp_step=terminal_step;
    int disconnected=0,settled=0,uncertain=0;
    assert(!tcp_control_stream(daemon[0],sockets[0],NULL,&wifi,0x2345,&disconnected,&settled,&uncertain));
    assert(disconnected && settled && !uncertain);
    current_scan=NULL;close(sockets[0]);close(daemon[0]);joined(child);
}
static void rejected_batch_and_closed_peer(void) {
    /* Unix peer closure is synchronously observable; do not assume TCP FIN/RST
     * has propagated just because the peer called close. TCP is tested above. */
    int sockets[2];assert(!socketpair(AF_UNIX,SOCK_STREAM,0,sockets));
    nonblocking(sockets[0]);close(sockets[1]);int ended=0;
    assert(tcp_control_batch(sockets[0],set_event("TCP_REJECTED",NULL,0,NULL,0,0),&ended)==-1);
    uint8_t byte=0x53;
    assert(tcp_control_batch(sockets[0],set_event("SEND_FRAME",&byte,1,NULL,0,0),&ended)==-1);
    close(sockets[0]);
}
static fe35_bridge_batch detached_step(void *context,int tcp,const uint8_t *bytes,size_t size,int64_t now) {
    (void)tcp;(void)now;int *eof=context;assert(!bytes);memset(&batch,0,sizeof(batch));
    if(size==SIZE_MAX) {(*eof)++;return set_event("TCP_CONTROL_DETACHED",NULL,0,NULL,0,0);}
    assert(size==0);return &batch;
}
static void nearby_eof_retains_original_owner_until_expiry(void) {
    int sockets[2],daemon[2];pair(sockets);assert(!socketpair(AF_UNIX,SOCK_STREAM,0,daemon));
    assert(!shutdown(sockets[1],SHUT_WR));
    int64_t expiry=now_ms()+80;fe35_scan_transport scan={&expiry,1,-1,notify};
    current_scan=&scan;scan_ended=0;int eof=0,disconnected=0,settled=0,uncertain=0;
    fe35_wifi_transport wifi={0};wifi.context=&eof;wifi.tcp_step=detached_step;
    assert(tcp_control_stream(daemon[0],sockets[0],NULL,&wifi,0x2345,&disconnected,&settled,&uncertain)==-1);
    assert(eof==1 && now_ms()>=expiry && !uncertain && !disconnected);
    current_scan=NULL;scan_ended=0;close(sockets[0]);close(sockets[1]);close(daemon[0]);close(daemon[1]);
}
int main(void) {
    alarm(10);assert(signal(SIGPIPE,SIG_DFL)!=SIG_ERR);
    backpressure_and_cancel();settled_fe35_and_ack();rejected_batch_and_closed_peer();
    nearby_eof_retains_original_owner_until_expiry();
    puts("NEARBY_PRODUCTION_TCP_PUMP_OK=4;BOUNDARY=real-loopback-injected-common-batches-not-device");
    return 0;
}
