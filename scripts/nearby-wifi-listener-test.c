#define _POSIX_C_SOURCE 200809L
#include "../theos/NearbyWifiListener.h"
#include <errno.h>
#include <poll.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#define CHECK(c) do { if(!(c)) {fprintf(stderr,"NEARBY_LISTENER_ASSERT_LINE=%d\n",__LINE__);return 1;} } while(0)
/* Test-only I/O bounds. Production listener/lease timeouts are unchanged. */
static int64_t now_ms(void) {
    struct timespec t;
    if(clock_gettime(CLOCK_MONOTONIC,&t))return -1;
    return (int64_t)t.tv_sec*1000+t.tv_nsec/1000000;
}
static bool wait_ready(int fd, short events, int64_t deadline) {
    for(;;) {
        int64_t now=now_ms();if(now<0 || now>=deadline)return false;
        struct pollfd p={.fd=fd,.events=events,.revents=0};
        int n=poll(&p,1,(int)(deadline-now));
        if(n<0 && errno==EINTR)continue;
        return n>0 && !(p.revents&POLLNVAL) && (p.revents&(events|POLLHUP|POLLERR));
    }
}
static int accept_ready(int fd, int64_t deadline) {
    while(now_ms()<deadline) {
        int peer=accept(fd,NULL,NULL);if(peer>=0)return peer;
        if(errno==EINTR)continue;
        if((errno!=EAGAIN && errno!=EWOULDBLOCK) || !wait_ready(fd,POLLIN,deadline))return -1;
    }
    return -1;
}
static bool connect_ready(int fd, const struct sockaddr_in *a, int64_t deadline) {
    if(connect(fd,(const struct sockaddr *)a,sizeof(*a))==0)return true;
    if(errno!=EINPROGRESS || !wait_ready(fd,POLLOUT,deadline))return false;
    int error=0;socklen_t size=sizeof(error);
    return !getsockopt(fd,SOL_SOCKET,SO_ERROR,&error,&size) && size==sizeof(error) && !error;
}
static bool send_byte(int fd, char byte, int64_t deadline) {
    while(now_ms()<deadline) {
        ssize_t n=send(fd,&byte,1,0);if(n==1)return true;
        if(n<0 && errno==EINTR)continue;
        if(n>=0 || (errno!=EAGAIN && errno!=EWOULDBLOCK) || !wait_ready(fd,POLLOUT,deadline))return false;
    }
    return false;
}
/* Supply the next byte only after the actual nonblocking recv returns EAGAIN.
 * This forces two partial reads without threads, sleeps or scheduling guesses. */
static bool receive_fragmented(int fd, int sender, char out[2], unsigned *waits) {
    size_t used=0;int64_t start=now_ms();if(start<0)return false;
    int64_t deadline=start+2000;
    while(used<2 && now_ms()<deadline) {
        ssize_t n=recv(fd,out+used,2-used,0);
        if(n>0) {used+=(size_t)n;continue;}
        if(n<0 && errno==EINTR)continue;
        if(n==0 || (errno!=EAGAIN && errno!=EWOULDBLOCK) || *waits>=2)return false;
        char byte="XY"[*waits];++*waits;
        if(!send_byte(sender,byte,deadline) || !wait_ready(fd,POLLIN,deadline))return false;
    }
    return used==2;
}
static int bound(int type, bool nonblocking) {
    int fd=socket(AF_INET,type,0);if(fd<0)return -1;
    struct sockaddr_in a={0};a.sin_family=AF_INET;a.sin_addr.s_addr=htonl(INADDR_LOOPBACK);
    if(bind(fd,(struct sockaddr *)&a,sizeof(a)) ||
       (nonblocking && fcntl(fd,F_SETFL,O_NONBLOCK)<0)) {close(fd);return -1;}
    return fd;
}
int main(void) {
    uint32_t loopback=htonl(INADDR_LOOPBACK);uint16_t port=0;
    int fd=bound(SOCK_STREAM,true);CHECK(fd>=0);CHECK(listen(fd,1)==0);
    CHECK(ohc_nearby_prepare_listener(fd,loopback,&port) && port>0);
    uint16_t original=port;CHECK(ohc_nearby_prepare_listener(fd,loopback,&port) && port==original);
    CHECK(accept(fd,NULL,NULL)<0 && (errno==EAGAIN || errno==EWOULDBLOCK));
    CHECK(accept_ready(fd,now_ms()+10)<0); /* No peer: bounded readiness failure. */
    int client=socket(AF_INET,SOCK_STREAM,0);CHECK(client>=0);
    CHECK(fcntl(client,F_SETFL,O_NONBLOCK)==0);
    struct sockaddr_in a={0};a.sin_family=AF_INET;a.sin_addr.s_addr=loopback;a.sin_port=htons(port);
    CHECK(connect_ready(client,&a,now_ms()+2000));
    int accepted=accept_ready(fd,now_ms()+2000);CHECK(accepted>=0);CHECK(fcntl(accepted,F_SETFL,O_NONBLOCK)==0);
    CHECK(!wait_ready(accepted,POLLIN,now_ms()+10)); /* No data yet. */
    char data[2]={0};unsigned waits=0;
    CHECK(receive_fragmented(accepted,client,data,&waits) && waits==2 && !memcmp(data,"XY",2));
    CHECK(fcntl(fd,F_GETFL)&O_NONBLOCK);CHECK(fcntl(accepted,F_GETFL)&O_NONBLOCK);
    CHECK(ohc_nearby_prepare_listener(fd,loopback,&port) && port==original);
    CHECK(shutdown(client,SHUT_WR)==0);CHECK(wait_ready(accepted,POLLIN,now_ms()+2000));
    CHECK(recv(accepted,data,1,0)==0); /* EOF is distinct from EAGAIN. */
    port=777;CHECK(!ohc_nearby_prepare_listener(accepted,loopback,&port) && port==777);
    CHECK(close(accepted)==0 && close(client)==0 && close(fd)==0);
    fd=bound(SOCK_STREAM,true);CHECK(fd>=0);
    CHECK(!ohc_nearby_prepare_listener(fd,htonl(0xc0000263),&port));CHECK(close(fd)==0);
    fd=bound(SOCK_STREAM,false);CHECK(fd>=0);
    CHECK(!ohc_nearby_prepare_listener(fd,loopback,&port));CHECK(close(fd)==0);
    fd=bound(SOCK_DGRAM,true);CHECK(fd>=0);
    CHECK(!ohc_nearby_prepare_listener(fd,loopback,&port));CHECK(close(fd)==0);
    fd=socket(AF_INET,SOCK_STREAM,0);CHECK(fd>=0);CHECK(fcntl(fd,F_SETFL,O_NONBLOCK)==0);
    CHECK(!ohc_nearby_prepare_listener(fd,loopback,&port));CHECK(close(fd)==0);
    CHECK(!ohc_nearby_prepare_listener(-1,loopback,&port));
    CHECK(!ohc_nearby_prepare_listener(-1,loopback,NULL));
    puts("NEARBY_PRODUCTION_LISTENER_CASES_OK=8;BOUNDARY=host-POSIX-real-loopback-not-device");
    return 0;
}
