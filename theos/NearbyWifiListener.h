#ifndef OPENHC_NEARBY_WIFI_LISTENER_H
#define OPENHC_NEARBY_WIFI_LISTENER_H
#include <arpa/inet.h>
#include <fcntl.h>
#include <stdbool.h>
#include <stdint.h>
#include <sys/socket.h>

/* The trusted provider retains ownership. Only reassert the bounded one-peer
 * listen after validating its bound IPv4 stream and nonblocking state. Darwin
 * defines SO_ACCEPTCONN but does not implement its getsockopt getter. */
static inline bool ohc_nearby_prepare_listener(int fd, uint32_t address, uint16_t *port) {
    struct sockaddr_in local={0};socklen_t size=sizeof(local);
    int type=0;socklen_t typeSize=sizeof(type);
    int flags=fd>=0?fcntl(fd,F_GETFL):-1;
    if(!port || fd<0 || getsockname(fd,(struct sockaddr *)&local,&size) ||
       size!=sizeof(local) || local.sin_family!=AF_INET || !ntohs(local.sin_port) ||
       local.sin_addr.s_addr!=address ||
       getsockopt(fd,SOL_SOCKET,SO_TYPE,&type,&typeSize) ||
       typeSize!=sizeof(type) || type!=SOCK_STREAM || flags<0 || !(flags&O_NONBLOCK)) return false;
    /* listen is idempotent on the provider's listener and rejects a connected
     * socket. No socket, connection, lease or authorization is created here. */
    if(listen(fd,1)) return false;
    *port=ntohs(local.sin_port);return true;
}
#endif
