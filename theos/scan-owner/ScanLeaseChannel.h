#ifndef OHC_SCAN_LEASE_CHANNEL_H
#define OHC_SCAN_LEASE_CHANNEL_H
#include "ScanLeaseProtocol.h"
typedef struct { int fd; uint64_t generation, sequence; int64_t deadline; bool failed; } ohc_lease_channel;
int64_t ohc_lease_now(void);
/* Finite I/O deadline includes fragmented reads/writes; no unbounded retries. */
bool ohc_lease_read(int fd, ohc_lease_frame *, int timeout_ms);
bool ohc_lease_write(int fd,const ohc_lease_frame *,int timeout_ms);
bool ohc_lease_exchange(ohc_lease_channel *,uint8_t op,uint32_t flags,int status);
void ohc_lease_close(ohc_lease_channel *);
/* Only the compile-time fixture can adopt a test broker descriptor. Production
 * must first acquire a verified root-controlled launch grant: not implemented. */
bool ohc_lease_adopt(ohc_lease_channel *,int fd,uint64_t generation,int64_t deadline);
#endif
