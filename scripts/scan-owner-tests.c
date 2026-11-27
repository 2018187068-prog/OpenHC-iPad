#include "../theos/scan-owner/ScanOwner.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static int checks;
#define CHECK(x) do { ++checks; if (!(x)) { fprintf(stderr,"FAIL line=%d: %s\n",__LINE__,#x); exit(1); } } while (0)
typedef struct { int n[OHC_RELEASED+1]; int order[128]; int used; int64_t deadline; } logbook;
static void emit(void *p, ohc_owner_effect e, uint64_t g, int64_t d) {
    logbook *l=p; CHECK(g>0); CHECK(l->used<128); l->n[e]++; l->order[l->used++]=e;
    if (!l->deadline) {
        l->deadline=d;
    }
    CHECK(l->deadline==d);
}
static ohc_owner_peer peer(void) {
    ohc_owner_peer p={0}; p.token[1]=501; p.token[2]=501; p.token[5]=123; p.token[7]=10;
    p.connection=1; p.policy_epoch=5; p.endpoint_device=1; p.endpoint_inode=20;
    p.kernel_verified=p.endpoint_verified=true; return p;
}
#ifdef OPENHC_SCAN_OWNER_TEST
static bool allow(const ohc_owner_peer *p) { return p->token[7]==10; }
#endif
static void init(ohc_owner *o,logbook *l) {
    memset(l,0,sizeof(*l)); ohc_owner_init(o,emit,l);
#ifdef OPENHC_SCAN_OWNER_TEST
    o->test_admit=allow;
#endif
}
static bool frame(ohc_owner *o,ohc_owner_connection *c,ohc_owner_peer *p,const char *s,int64_t t) {
    return ohc_owner_feed(o,c,p,s,strlen(s),t);
}
#ifdef OPENHC_SCAN_OWNER_TEST
static void running(ohc_owner *o,ohc_owner_connection *c,logbook *l,ohc_owner_peer *p) {
    init(o,l); CHECK(ohc_owner_open(c,p)); CHECK(frame(o,c,p,"STA",100));
    CHECK(o->state==OHC_IDLE); CHECK(frame(o,c,p,"RT\n",100));
    CHECK(o->state==OHC_ARMING); ohc_owner_guard_ready(o,o->generation,true,101);
    CHECK(o->state==OHC_TAKING); ohc_owner_working(o,o->generation,true,102);
    CHECK(o->state==OHC_RUNNING); CHECK(l->n[OHC_RUN_WORKER]==1);
}
#endif
int main(void) {
    ohc_owner o; ohc_owner_connection c; logbook l; ohc_owner_peer p=peer();
    init(&o,&l); CHECK(ohc_owner_open(&c,&p));
#ifndef OPENHC_SCAN_OWNER_TEST
    CHECK(!frame(&o,&c,&p,"START\n",100)); CHECK(o.state==OHC_IDLE); CHECK(!l.used);
    puts("SCAN_OWNER_PRODUCTION_DENY_ALL_OK");
#else
    /* Same account is insufficient, even with an injected test policy. */
    ohc_owner_peer denied=p; denied.token[7]++;
    CHECK(ohc_owner_open(&c,&denied)); CHECK(!frame(&o,&c,&denied,"START\n",100)); CHECK(!l.used);
    const char *forged[]={"role=root\n","guard=1\n","/tmp/run\n","PONG\n","START x\n","START\r\n"};
    for (unsigned i=0;i<sizeof(forged)/sizeof(*forged);++i) {
        init(&o,&l); CHECK(ohc_owner_open(&c,&p)); CHECK(!frame(&o,&c,&p,forged[i],100)); CHECK(!l.used);
    }
    /* Connection, process incarnation, complete token and endpoint policy freshness. */
    for (int i=0;i<6;i++) {
        running(&o,&c,&l,&p); ohc_owner_peer fresh=p;
        if (i==0) {
            fresh.token[7]++;
        }
        if (i==1) {
            fresh.token[5]++;
        }
        if (i==2) {
            fresh.endpoint_inode++;
        }
        if (i==3) {
            fresh.policy_epoch++;
        }
        if (i==4) {
            fresh.connection++;
        }
        if (i==5) {
            fresh.kernel_verified=false;
        }
        CHECK(!ohc_owner_feed(&o,&c,&fresh,NULL,0,103));
        CHECK(o.revoked && l.n[OHC_CANCEL_WORKER]==1);
        CHECK(l.order[l.used-2]==OHC_CLEAR && l.order[l.used-1]==OHC_CANCEL_WORKER);
    }
    running(&o,&c,&l,&p);
    ohc_owner_connection other; ohc_owner_peer q=p; q.connection++;
    CHECK(ohc_owner_open(&other,&q)); CHECK(!frame(&o,&other,&q,"START\n",103));
    CHECK(o.state==OHC_RUNNING && !o.revoked);
    CHECK(ohc_owner_transport_event(&o,o.generation,"PONG",103)); CHECK(!ohc_owner_pairing(&o,o.generation));
    CHECK(ohc_owner_transport_event(&o,o.generation,"RFCOMM_READY",104));
    CHECK(!ohc_owner_pairing(&o,o.generation));
    CHECK(!ohc_owner_transport_event(&o,o.generation-1,"SDP_READY",104));
    CHECK(ohc_owner_transport_event(&o,o.generation,"SDP_READY",105));
    CHECK(ohc_owner_pairing(&o,o.generation)); CHECK(!ohc_owner_pairing(&o,o.generation));
    CHECK(ohc_owner_transport_event(&o,o.generation,"ACCEPTED",106)); CHECK(o.revoked);
    CHECK(ohc_owner_handoff(&o,o.generation)); CHECK(!ohc_owner_handoff(&o,o.generation));
    CHECK(ohc_owner_transport_event(&o,o.generation,"TICK",107));
    CHECK(!l.n[OHC_REQUEST_RESTORE]);
    ohc_owner_completed(&o,o.generation,(fe35_scan_completion){true,true,1},true,108);
    CHECK(o.state==OHC_RESTORING && l.n[OHC_REQUEST_RESTORE]==1 && !l.n[OHC_DELEGATE_GUARD]);
    CHECK(!l.n[OHC_RELEASED]); ohc_owner_recovered(&o,o.generation-1,true); CHECK(!l.n[OHC_RELEASED]);
    ohc_owner_recovered(&o,o.generation,true); CHECK(o.state==OHC_IDLE && l.n[OHC_RELEASED]==1);
    /* CLEANED is before return and cannot recover; failed cleanup delegates once. */
    running(&o,&c,&l,&p); CHECK(ohc_owner_transport_event(&o,o.generation,"CLEANED",103));
    CHECK(!l.n[OHC_REQUEST_RESTORE] && !l.n[OHC_DELEGATE_GUARD]);
    ohc_owner_completed(&o,o.generation,(fe35_scan_completion){true,false,1},true,104);
    CHECK(o.state==OHC_DELEGATED && l.n[OHC_DELEGATE_GUARD]==1 && !l.n[OHC_REQUEST_RESTORE]);
    /* Unrecognized status cannot request restoration, even with claimed cleanup. */
    running(&o,&c,&l,&p);
    ohc_owner_completed(&o,o.generation,(fe35_scan_completion){true,true,90},true,104);
    CHECK(o.state==OHC_DELEGATED && l.n[OHC_DELEGATE_GUARD]==1 && !l.n[OHC_REQUEST_RESTORE]);
    ohc_owner_tick(&o,5000); ohc_owner_recovered(&o,o.generation,false);
    CHECK(l.n[OHC_DELEGATE_GUARD]==1 && !l.n[OHC_RELEASED]);
    /* Unknown execution and late final callback keep fence; guard may not release live worker. */
    running(&o,&c,&l,&p); ohc_owner_disconnect(&o,&c,103); ohc_owner_tick(&o,1103);
    CHECK(o.state==OHC_DELEGATED); ohc_owner_recovered(&o,o.generation,true);
    CHECK(!l.n[OHC_RELEASED]); CHECK(ohc_owner_open(&other,&q)); CHECK(!frame(&o,&other,&q,"START\n",1104));
    ohc_owner_completed(&o,o.generation,(fe35_scan_completion){true,true,1},true,1105);
    CHECK(l.n[OHC_RELEASED]==1 && !l.n[OHC_REQUEST_RESTORE] && l.n[OHC_DELEGATE_GUARD]==1);
    running(&o,&c,&l,&p);
    ohc_owner_completed(&o,o.generation,(fe35_scan_completion){true,true,0},false,103);
    CHECK(o.state==OHC_DELEGATED && !l.n[OHC_REQUEST_RESTORE]);
    ohc_owner_recovered(&o,o.generation,true); CHECK(!l.n[OHC_RELEASED]);
    ohc_owner_execution_exited(&o,o.generation-1,true); CHECK(!l.n[OHC_RELEASED]);
    ohc_owner_execution_exited(&o,o.generation,true); CHECK(l.n[OHC_RELEASED]==1);
    /* Slow/idle framing cannot hold the endpoint indefinitely. */
    init(&o,&l); CHECK(ohc_owner_open(&c,&p)); CHECK(frame(&o,&c,&p,"STA",100));
    CHECK(!ohc_owner_feed(&o,&c,&p,NULL,0,1100)); CHECK(!l.used);
    init(&o,&l); CHECK(ohc_owner_open(&c,&p)); CHECK(ohc_owner_feed(&o,&c,&p,NULL,0,100));
    CHECK(!ohc_owner_feed(&o,&c,&p,NULL,0,2100)); CHECK(!l.used);
    /* Guard readiness failure / no reply: no worker, takeover or heartbeat. */
    for(int i=0;i<2;i++) {
        init(&o,&l); CHECK(ohc_owner_open(&c,&p)); CHECK(frame(&o,&c,&p,"START\n",100));
        if (i) {
            ohc_owner_tick(&o,3100);
        } else {
            ohc_owner_guard_ready(&o,o.generation,false,101);
        }
        CHECK(o.state==OHC_DELEGATED && !l.n[OHC_RUN_WORKER] && !l.n[OHC_TAKEOVER] && !l.n[OHC_HEARTBEAT]);
    }
    running(&o,&c,&l,&p); int64_t absolute=o.deadline;
    ohc_owner_tick(&o,2101); ohc_owner_tick(&o,2101); CHECK(l.n[OHC_HEARTBEAT]==2);
    CHECK(frame(&o,&c,&p,"BACKGROUND\n",2102)); CHECK(o.deadline==absolute);
    CHECK(l.n[OHC_CLEAR]==1 && l.n[OHC_CANCEL_WORKER]==1);
    CHECK(frame(&o,&c,&p,"STOP\n",2103)); CHECK(l.n[OHC_CLEAR]==1 && l.n[OHC_CANCEL_WORKER]==1);
    ohc_owner_tick(&o,3102); ohc_owner_tick(&o,absolute); CHECK(l.n[OHC_DELEGATE_GUARD]==1);
    CHECK(o.deadline==absolute && l.n[OHC_STOP_HEARTBEAT]==1);
    running(&o,&c,&l,&p); ohc_owner_tick(&o,o.deadline);
    CHECK(o.revoked && o.cancelled && !ohc_owner_pairing(&o,o.generation));
    ohc_owner_tick(&o,o.deadline+1000); CHECK(o.state==OHC_DELEGATED);
    /* Cancel before guard readiness: stale acknowledgements cannot take over. */
    init(&o,&l); CHECK(ohc_owner_open(&c,&p)); CHECK(frame(&o,&c,&p,"START\n",100));
    CHECK(frame(&o,&c,&p,"STOP\n",101));
    ohc_owner_guard_ready(&o,o.generation,true,102);
    CHECK(!l.n[OHC_TAKEOVER] && !l.n[OHC_RUN_WORKER]);
    ohc_owner_tick(&o,1101); CHECK(l.n[OHC_DELEGATE_GUARD]==1);
    /* A new admission after verified recovery has a fresh fence. Prior worker
     * completion/guard/readiness callbacks cannot change its state or clock. */
    running(&o,&c,&l,&p); uint64_t old=o.generation;
    ohc_owner_completed(&o,old,(fe35_scan_completion){true,true,1},true,103);
    ohc_owner_recovered(&o,old,true);l.deadline=0;
    CHECK(ohc_owner_open(&other,&q));CHECK(frame(&o,&other,&q,"START\n",200));
    CHECK(o.generation==old+1 && o.state==OHC_ARMING);
    ohc_owner_guard_ready(&o,old,true,0);ohc_owner_working(&o,old,true,0);
    ohc_owner_completed(&o,old,(fe35_scan_completion){true,true,0},true,0);
    ohc_owner_recovered(&o,old,true);
    CHECK(!ohc_owner_transport_event(&o,old,"SDP_READY",0));
    CHECK(o.state==OHC_ARMING && o.last_now==200 && !o.sdp && !o.worker_returned);
    printf("SCAN_OWNER_TEST_ADAPTER_CHECKS=%d\n",checks);
    const int terminal_checks=checks;
    /* Reproduce the old deadline gap: common expires well before the immutable
     * 240-second owner lease, so a native TICK alone cannot revoke the owner.
     * Exercise the actual common-event adapter at startup, ready and accepted. */
    for (int stage=0;stage<3;stage++) {
        running(&o,&c,&l,&p);
        const uint64_t generation=o.generation;
        const int64_t lease_deadline=o.deadline;
        if (stage) {
            CHECK(ohc_owner_transport_event(&o,generation,"RFCOMM_READY",103));
            CHECK(ohc_owner_transport_event(&o,generation,"SDP_READY",104));
            CHECK(ohc_owner_pairing(&o,generation));
        }
        if (stage==2) {
            CHECK(ohc_owner_transport_event(&o,generation,"ACCEPTED",105));
            ohc_owner_common_event(&o,generation,"CLEAR_PAIRING",105);
            CHECK(o.accepted && !o.cancelled && o.state==OHC_RUNNING);
        }
        CHECK(ohc_owner_transport_event(&o,generation,"TICK",2102));
        CHECK(o.revoked==(stage==2) && !o.cancelled);
        const int used=l.used;
        ohc_owner_common_event(&o,generation-1,"CLOSE_CONTROL_TRANSPORT",0);
        ohc_owner_common_event(&o,generation,"CLEAR_PAIRING",2102);
        ohc_owner_common_event(&o,generation,"CLEANED",2102);
        CHECK(l.used==used && o.state==OHC_RUNNING && o.last_now==2102);
        ohc_owner_common_event(&o,generation,"CLOSE_CONTROL_TRANSPORT",2102);
        CHECK(o.revoked && o.cancelled && o.state==OHC_STOPPING);
        CHECK(l.n[OHC_CLEAR]==1 && l.n[OHC_CANCEL_WORKER]==1);
        CHECK(l.order[l.used-1]==OHC_CANCEL_WORKER);
        CHECK(o.deadline==lease_deadline && !l.n[OHC_REQUEST_RESTORE] && !l.n[OHC_DELEGATE_GUARD]);
        CHECK(!ohc_owner_handoff(&o,generation));
        const int stopped=l.used;
        ohc_owner_common_event(&o,generation,"CLOSE_CONTROL_TRANSPORT",2103);
        CHECK(l.used==stopped && o.deadline==lease_deadline);
    }
    printf("SCAN_OWNER_COMMON_TERMINAL_CHECKS=%d\n",checks-terminal_checks);
#endif
    return 0;
}
