#include "../theos/NearbyWifiListener.h"
#include <stdio.h>
#include <unistd.h>
#define CHECK(c) do { if(!(c)) {fprintf(stderr,"NEARBY_LISTENER_ASSERT_LINE=%d\n",__LINE__);return 1;} } while(0)
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
    int client=socket(AF_INET,SOCK_STREAM,0);CHECK(client>=0);
    struct sockaddr_in a={0};a.sin_family=AF_INET;a.sin_addr.s_addr=loopback;a.sin_port=htons(port);
    CHECK(connect(client,(struct sockaddr *)&a,sizeof(a))==0);
    int accepted=accept(fd,NULL,NULL);CHECK(accepted>=0);CHECK(fcntl(accepted,F_SETFL,O_NONBLOCK)==0);
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
