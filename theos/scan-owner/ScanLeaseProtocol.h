#ifndef OHC_SCAN_LEASE_PROTOCOL_H
#define OHC_SCAN_LEASE_PROTOCOL_H
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
/* Internal broker/guard protocol, NOT a caller admission API. No strings, paths,
 * commands, service names, identities or authority claims fit this grammar. */
#define OHC_LEASE_FRAME_SIZE 40
#define OHC_LEASE_MAX_MS 240000
#define OHC_LEASE_HEARTBEAT_MS 6000
enum { OHC_L_ARM=1, OHC_L_TAKEOVER, OHC_L_BEAT, OHC_L_COMPLETE,
       OHC_L_RESTORE, OHC_L_DELEGATE, OHC_L_OK=128, OHC_L_DENIED=255 };
enum { OHC_L_RETURNED=1, OHC_L_CLEANUP=2, OHC_L_EXITED=4 };
typedef struct {
    uint8_t op;
    uint64_t generation, sequence;
    int64_t deadline;
    uint32_t flags;
    int32_t status;
} ohc_lease_frame;
typedef struct {
    uint64_t generation, sequence;
    int64_t deadline, heartbeat;
    bool armed, working, completed, safe, delegated, restored;
} ohc_lease_guard;
void ohc_lease_encode(uint8_t[OHC_LEASE_FRAME_SIZE], const ohc_lease_frame *);
bool ohc_lease_decode(ohc_lease_frame *, const uint8_t[OHC_LEASE_FRAME_SIZE]);
/* Pure bounded state: platform effects and independent exit knowledge are not
 * supplied by a peer frame. A COMPLETE is owner evidence, never guard recovery. */
bool ohc_lease_step(ohc_lease_guard *, const ohc_lease_frame *, int64_t now);
bool ohc_lease_overdue(const ohc_lease_guard *, int64_t now);
/* Deliberately unavailable in EVERY deployment build, irrespective of UID,
 * inherited descriptors, argv/environment, marker files or peer values. */
bool ohc_lease_production_available(void);
#endif
