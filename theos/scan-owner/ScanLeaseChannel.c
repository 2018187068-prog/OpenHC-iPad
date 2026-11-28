#if defined(__linux__) && !defined(_POSIX_C_SOURCE)
#define _POSIX_C_SOURCE 200809L
#endif
#include "ScanLeaseChannel.h"
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <poll.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>
#include <string.h>
#ifdef OPENHC_SCAN_OWNER_PROCESS_TEST
#include <stdio.h>
#define LEASE_NOTE(stage,op,g,seq,d,ok,error) \
    fprintf(stderr,"LEASE_IO stage=%s op=%u generation=%llu sequence=%llu now=%lld deadline=%lld ok=%d errno=%d\n", \
        stage,(unsigned)(op),(unsigned long long)(g),(unsigned long long)(seq), \
        (long long)ohc_lease_now(),(long long)(d),(int)(ok),(error))
#else
#define LEASE_NOTE(stage,op,g,seq,d,ok,error) ((void)0)
#endif
int64_t ohc_lease_now(void) {
    struct timespec t;
    if(clock_gettime(CLOCK_MONOTONIC,&t)) { return -1; }
    return (int64_t)t.tv_sec*1000+t.tv_nsec/1000000;
}
static bool transfer(int fd,uint8_t *b,size_t count,bool writing,int timeout) {
    if(timeout<=0 || timeout>3000) { return false; }
    int64_t start=ohc_lease_now();
    if(start<0||start>INT64_MAX-timeout) { return false; }
    int64_t end=start+timeout;
    while(count) {
        int64_t current=ohc_lease_now();
        if(current<start) { return false; }
        int64_t left=end-current;
        if(left<=0) { return false; }
        struct pollfd p={fd,writing?POLLOUT:POLLIN,0};
        int r=poll(&p,1,(int)left);
        if(r<0 && errno==EINTR) { continue; }
        if(r<=0) { return false; }
        ssize_t n;
#if defined(__linux__)
        if(writing) { n=send(fd,b,count,MSG_NOSIGNAL); } else { n=recv(fd,b,count,0); }
#elif defined(__APPLE__)
        if(writing) { n=send(fd,b,count,0); } else { n=recv(fd,b,count,0); }
#else
#error Unsupported private-channel SIGPIPE platform
#endif
        if(n<0 && (errno==EINTR||errno==EAGAIN||errno==EWOULDBLOCK)) { continue; }
        if(n<=0) { return false; }
        b+=n; count-=(size_t)n;
    }
    return true;
}
bool ohc_lease_read(int fd,ohc_lease_frame *f,int timeout) {
    uint8_t b[OHC_LEASE_FRAME_SIZE];
    return transfer(fd,b,sizeof(b),false,timeout)&&ohc_lease_decode(f,b);
}
bool ohc_lease_write(int fd,const ohc_lease_frame *f,int timeout) {
    uint8_t b[OHC_LEASE_FRAME_SIZE]; ohc_lease_encode(b,f);
    return transfer(fd,b,sizeof(b),true,timeout);
}
bool ohc_lease_adopt(ohc_lease_channel *c,int fd,uint64_t generation,int64_t deadline) {
    *c=(ohc_lease_channel){.fd=-1};
#ifndef OPENHC_SCAN_OWNER_PROCESS_TEST
    (void)fd; (void)generation; (void)deadline; return false;
#else
    struct stat s; int kind=0; socklen_t n=sizeof(kind);
    if(!generation || deadline<=ohc_lease_now() || fstat(fd,&s) || !S_ISSOCK(s.st_mode) ||
       getsockopt(fd,SOL_SOCKET,SO_TYPE,&kind,&n) || kind!=SOCK_STREAM ||
       fcntl(fd,F_SETFD,FD_CLOEXEC) || fcntl(fd,F_SETFL,O_NONBLOCK)) { return false; }
#ifdef __APPLE__
    int one=1;
    if(setsockopt(fd,SOL_SOCKET,SO_NOSIGPIPE,&one,sizeof(one))) { return false; }
#endif
    *c=(ohc_lease_channel){fd,generation,0,deadline,false}; return true;
#endif
}
bool ohc_lease_exchange(ohc_lease_channel *c,uint8_t op,uint32_t flags,int status) {
    if(c->failed || c->fd<0 || c->sequence==UINT64_MAX) { return false; }
    ohc_lease_frame f={op,c->generation,++c->sequence,c->deadline,flags,status},reply;
    LEASE_NOTE("request",op,f.generation,f.sequence,f.deadline,true,0);
    errno=0; bool wrote=ohc_lease_write(c->fd,&f,1000);
    LEASE_NOTE("write",op,f.generation,f.sequence,f.deadline,wrote,errno);
    errno=0; bool read=wrote&&ohc_lease_read(c->fd,&reply,1000);
    LEASE_NOTE("read",op,f.generation,f.sequence,f.deadline,read,errno);
    bool ok=read&&
        reply.op==OHC_L_OK && reply.generation==f.generation && reply.sequence==f.sequence &&
        reply.deadline==f.deadline && !reply.flags && !reply.status;
    LEASE_NOTE("validated-ack",op,f.generation,f.sequence,f.deadline,ok,0);
#ifdef OPENHC_SCAN_OWNER_PROCESS_TEST
    if(read&&!ok) fprintf(stderr,"LEASE_ACK_REJECT op_ok=%d generation_ok=%d sequence_ok=%d deadline_ok=%d flags_ok=%d status_ok=%d\n",
        reply.op==OHC_L_OK,reply.generation==f.generation,reply.sequence==f.sequence,
        reply.deadline==f.deadline,!reply.flags,!reply.status);
#endif
    if(!ok) { ohc_lease_close(c); }
    return ok;
}
void ohc_lease_close(ohc_lease_channel *c) {
    if(c->fd>=0) { close(c->fd); }
    c->fd=-1; c->failed=true;
}
