/* Actual worker socket helpers, real POSIX loopback. No phone or device claim. */
#include "../theos/NearbyReceiverSockets.h"
#include <assert.h>
#include <stdio.h>
#include <poll.h>

static int connect_port(int port) {
    int fd=socket(AF_INET,SOCK_STREAM,0);assert(fd>=0);
    struct sockaddr_in a={0};a.sin_family=AF_INET;a.sin_addr.s_addr=htonl(INADDR_LOOPBACK);a.sin_port=htons((uint16_t)port);
    assert(!connect(fd,(struct sockaddr *)&a,sizeof(a)));return fd;
}
static void setup(ohc_receiver_sockets *s) {
    ohc_receiver_init(s);s->local=s->peer=htonl(INADDR_LOOPBACK);
}
int main(void) {
    alarm(10);
    ohc_receiver_sockets s;setup(&s);int ports[2],peers[2];
    for(int endpoint=1;endpoint<=2;endpoint++) {
        ports[endpoint-1]=ohc_receiver_listen(&s,endpoint);assert(ports[endpoint-1]>0);
        assert(ohc_receiver_accept(&s,endpoint)==0);
        peers[endpoint-1]=connect_port(ports[endpoint-1]);assert(ohc_receiver_accept(&s,endpoint)==1);
        assert(fcntl(s.connection[endpoint-1],F_GETFL)&O_NONBLOCK);
    }
    assert(ports[0]!=ports[1]);
    uint8_t bytes[65536];memset(bytes,0x53,sizeof(bytes));
    int small=1024;assert(!setsockopt(s.connection[0],SOL_SOCKET,SO_SNDBUF,&small,sizeof(small)));
    size_t prefill=0;
    for(;;) {
        int flags=0;
#ifdef MSG_NOSIGNAL
        flags=MSG_NOSIGNAL;
#endif
        ssize_t n=send(s.connection[0],bytes,sizeof(bytes),flags);
        if(n<0) {assert(errno==EAGAIN || errno==EWOULDBLOCK);break;}
        assert(n>0);prefill+=(size_t)n;
    }
    assert(prefill>0);
    assert(ohc_receiver_queue(&s,1,bytes,sizeof(bytes)));assert(ohc_receiver_queue(&s,1,bytes,sizeof(bytes)));
    assert(!ohc_receiver_queue(&s,1,bytes,sizeof(bytes)));
    assert(ohc_receiver_prepare(peers[0]));size_t got=0;
    for(int rounds=0;got<prefill+131072 && rounds<100000;rounds++) {
        assert(ohc_receiver_flush(&s,1));
        ssize_t n=recv(peers[0],bytes,sizeof(bytes),0);
        if(n<0) {
            assert(errno==EAGAIN || errno==EWOULDBLOCK || errno==EINTR);
            struct pollfd wait={peers[0],POLLIN,0};assert(poll(&wait,1,10)>=0);continue;
        }
        assert(n>0);for(ssize_t i=0;i<n;i++)assert(bytes[i]==0x53);got+=(size_t)n;
    }
    assert(got==prefill+131072 && s.count[0]==0);
    int duplicate=connect_port(ports[0]);assert(ohc_receiver_accept(&s,1)==-1);close(duplicate);
    assert(ohc_receiver_close(&s));for(int i=0;i<2;i++)close(peers[i]);
    assert(ohc_receiver_close(&s));
    setup(&s);s.peer=inet_addr("192.0.2.99");int port=ohc_receiver_listen(&s,1);assert(port>0);
    int wrong=connect_port(port);assert(ohc_receiver_accept(&s,1)==-1);assert(s.connection[0]==-1);close(wrong);assert(ohc_receiver_close(&s));
    setup(&s);port=ohc_receiver_listen(&s,1);assert(port>0);
    assert(!close(s.listener[0]));assert(!ohc_receiver_close(&s));assert(!ohc_receiver_close(&s));
    setup(&s);s.local=inet_addr("192.0.2.99");assert(ohc_receiver_listen(&s,1)==-1);assert(ohc_receiver_close(&s));
    puts("NEARBY_RECEIVER_REAL_SOCKET_CASES_OK=6;BOUNDARY=host-POSIX-no-device");return 0;
}
