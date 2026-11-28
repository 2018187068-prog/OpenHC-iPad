#ifndef OPENHC_NEARBY_RECEIVER_SOCKETS_H
#define OPENHC_NEARBY_RECEIVER_SOCKETS_H
#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>

/* Worker-owned DMSDP session/control sockets. Caller must authorize each I/O
 * under the original owner lease; these helpers create no authority or timer. */
typedef struct {
    int listener[2], connection[2];
    bool opened[2], connected[2], cleanup_ok;
    uint32_t local, peer;
    uint8_t pending[2][131076];
    size_t at[2], count[2];
} ohc_receiver_sockets;
static inline void ohc_receiver_init(ohc_receiver_sockets *s) {
    memset(s,0,sizeof(*s));s->cleanup_ok=true;
    for(int i=0;i<2;i++) s->listener[i]=s->connection[i]=-1;
}
static inline bool ohc_receiver_close_fd(ohc_receiver_sockets *s,int *fd) {
    if(*fd<0) return true;
    int value=*fd;*fd=-1;
    if(close(value)) {s->cleanup_ok=false;return false;}
    return true;
}
static inline bool ohc_receiver_prepare(int fd) {
    int f=fcntl(fd,F_GETFL);
    if(f<0 || fcntl(fd,F_SETFL,f|O_NONBLOCK) || fcntl(fd,F_SETFD,FD_CLOEXEC)) return false;
#ifdef SO_NOSIGPIPE
    int yes=1;if(setsockopt(fd,SOL_SOCKET,SO_NOSIGPIPE,&yes,sizeof(yes))) return false;
#endif
    return true;
}
static inline int ohc_receiver_listen(ohc_receiver_sockets *s,int endpoint) {
    int i=endpoint-1;if(i<0 || i>1 || s->opened[i] || !s->local || !s->peer) return -1;
    s->opened[i]=true;s->listener[i]=socket(AF_INET,SOCK_STREAM,0);
    struct sockaddr_in address={0};address.sin_family=AF_INET;address.sin_addr.s_addr=s->local;
    socklen_t size=sizeof(address);
    if(s->listener[i]<0 || !ohc_receiver_prepare(s->listener[i]) ||
       bind(s->listener[i],(struct sockaddr *)&address,sizeof(address)) || listen(s->listener[i],1) ||
       getsockname(s->listener[i],(struct sockaddr *)&address,&size) || size!=sizeof(address)) {
        ohc_receiver_close_fd(s,&s->listener[i]);return -1;
    }
    return ntohs(address.sin_port);
}
/* 1=accepted, 0=not ready, -1=wrong peer/duplicate/error. A listener never
 * reopens or silently replaces a connection after an endpoint incarnation. */
static inline int ohc_receiver_accept(ohc_receiver_sockets *s,int endpoint) {
    int i=endpoint-1;if(i<0 || i>1) return -1;
    if(s->listener[i]<0) return 0;
    struct sockaddr_in peer={0};socklen_t size=sizeof(peer);
    int fd=accept(s->listener[i],(struct sockaddr *)&peer,&size);
    if(fd<0) return errno==EAGAIN || errno==EWOULDBLOCK || errno==EINTR ? 0 : -1;
    if(s->connected[i] || size!=sizeof(peer) || peer.sin_family!=AF_INET ||
       peer.sin_addr.s_addr!=s->peer || !ohc_receiver_prepare(fd)) {
        ohc_receiver_close_fd(s,&fd);return -1;
    }
    s->connected[i]=true;s->connection[i]=fd;return 1;
}
static inline bool ohc_receiver_queue(ohc_receiver_sockets *s,int endpoint,const uint8_t *bytes,size_t count) {
    int i=endpoint-1;if(i<0 || i>1 || s->connection[i]<0 || !bytes || !count) return false;
    size_t live=s->count[i]-s->at[i];
    if(count>sizeof(s->pending[i])-live) return false;
    if(s->at[i]) memmove(s->pending[i],s->pending[i]+s->at[i],live);
    memcpy(s->pending[i]+live,bytes,count);s->at[i]=0;s->count[i]=live+count;return true;
}
static inline bool ohc_receiver_flush(ohc_receiver_sockets *s,int endpoint) {
    int i=endpoint-1;if(i<0 || i>1) return false;
    if(s->at[i]==s->count[i]) return true;
    int flags=0;
#ifdef MSG_NOSIGNAL
    flags=MSG_NOSIGNAL;
#endif
    ssize_t n=send(s->connection[i],s->pending[i]+s->at[i],s->count[i]-s->at[i],flags);
    if(n<0 && (errno==EINTR || errno==EAGAIN || errno==EWOULDBLOCK)) return true;
    if(n<=0) return false;
    memset(s->pending[i]+s->at[i],0,(size_t)n);s->at[i]+=(size_t)n;
    if(s->at[i]==s->count[i]) s->at[i]=s->count[i]=0;
    return true;
}
static inline bool ohc_receiver_close(ohc_receiver_sockets *s) {
    for(int i=1;i>=0;i--) {
        ohc_receiver_close_fd(s,&s->connection[i]);ohc_receiver_close_fd(s,&s->listener[i]);
        memset(s->pending[i],0,sizeof(s->pending[i]));s->at[i]=s->count[i]=0;
    }
    return s->cleanup_ok;
}
#endif
