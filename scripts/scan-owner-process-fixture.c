/* Explicit TEST BROKER. Never packaged. Only admission + Trial service effects
 * and native worker completion are injected here; production owner core, binary
 * channel, separate guard exec, filesystem/lock and exit relation are real.
 * The Simulator relay additionally executes the real common/native runtime. */
#if defined(__linux__) && !defined(_POSIX_C_SOURCE)
#define _POSIX_C_SOURCE 200809L
#endif
#include "../theos/scan-owner/ScanOwner.h"
#include "../theos/scan-owner/ScanLeaseChannel.h"
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>
#if !defined(OPENHC_SCAN_OWNER_TEST) || !defined(OPENHC_SCAN_OWNER_PROCESS_TEST)
#error Test broker must never compile as deployment source
#endif
#define CHECK(x) do { if(!(x)) { fprintf(stderr,"PROCESS_ASSERT=%s line=%d\n",#x,__LINE__); exit(90); } } while(0)
static void pause_ms(int ms) { (void)poll(NULL,0,ms); }
static pid_t spawn_guard(const char *exe,int dir,int *client,bool missing) {
    int pair[2]; CHECK(!socketpair(AF_UNIX,SOCK_STREAM,0,pair));
    int leakage[2]; CHECK(!pipe(leakage));
    int childSocket=fcntl(pair[1],F_DUPFD_CLOEXEC,10);
    int childDir=fcntl(dir,F_DUPFD_CLOEXEC,10);
    CHECK(childSocket>=10&&childDir>=10);
    pid_t pid=fork(); CHECK(pid>=0);
    if(!pid) {
        CHECK(setsid()>=0);
        CHECK(dup2(childSocket,3)==3&&dup2(childDir,4)==4);
        int nullfd=open("/dev/null",O_RDWR); CHECK(nullfd>=0);
        CHECK(dup2(nullfd,0)==0&&dup2(nullfd,1)==1&&dup2(nullfd,2)==2);
        long maximum=sysconf(_SC_OPEN_MAX); CHECK(maximum>0&&maximum<=1048576);
        for(int fd=5;fd<maximum;++fd) { close(fd); }
        char *const args[]={(char *)exe,missing?"--test-missing-ready":NULL,NULL};
        char *const env[]={NULL};
        execve(exe,args,env); _exit(91);
    }
    close(childSocket); close(childDir); close(pair[1]);
    close(leakage[1]);
    struct pollfd evidence={leakage[0],POLLIN,0};
    CHECK(poll(&evidence,1,3000)>0);
    char byte; CHECK(read(leakage[0],&byte,1)==0); close(leakage[0]);
    puts("INHERITED_FD_ALLOWLIST_EOF"); fflush(stdout);
    *client=pair[0]; return pid;
}
typedef struct {
    ohc_owner owner; ohc_owner_connection connection; ohc_owner_peer peer;
    ohc_lease_channel lease;
    ohc_owner_effect queue[64]; int used,head,work,clear,cancel,delegated,released;
    int dir;
} fixture;
static bool admit(const ohc_owner_peer *p) { return p->policy_epoch==0x54455354; }
static void effect(void *p,ohc_owner_effect e,uint64_t g,int64_t deadline) {
    fixture *f=p; (void)g; (void)deadline; CHECK(f->used<64); f->queue[f->used++]=e;
    if(e==OHC_CLEAR) { f->clear++; puts("OWNER_CLEAR"); }
    if(e==OHC_CANCEL_WORKER) { CHECK(f->clear==1); f->cancel++; puts("WORKER_CANCEL"); }
}
static void drain(fixture *f) {
    while(f->head<f->used) {
        ohc_owner_effect e=f->queue[f->head++]; bool ok;
        switch(e) {
        case OHC_ARM_GUARD:
            f->lease.generation=f->owner.generation; f->lease.deadline=f->owner.deadline;
            ok=ohc_lease_exchange(&f->lease,OHC_L_ARM,0,0);
            ohc_owner_guard_ready(&f->owner,f->owner.generation,ok,ohc_lease_now()); break;
        case OHC_TAKEOVER:
            ok=ohc_lease_exchange(&f->lease,OHC_L_TAKEOVER,0,0);
            ohc_owner_working(&f->owner,f->owner.generation,ok,ohc_lease_now()); break;
        case OHC_RUN_WORKER: f->work++; puts("OWNER_WORK_AFTER_GUARD_READY"); break;
        case OHC_HEARTBEAT: (void)ohc_lease_exchange(&f->lease,OHC_L_BEAT,0,0); break;
        case OHC_REQUEST_RESTORE:
            ok=ohc_lease_exchange(&f->lease,OHC_L_RESTORE,0,0);
            ohc_owner_recovered(&f->owner,f->owner.generation,ok); break;
        case OHC_DELEGATE_GUARD:
            f->delegated++; (void)ohc_lease_exchange(&f->lease,OHC_L_DELEGATE,0,0); break;
        case OHC_RELEASED: f->released++; break;
        default: break;
        }
    }
}
static void completed(fixture *f,bool clean,bool exited) {
    fe35_scan_completion c={true,clean,1};
    (void)ohc_lease_exchange(&f->lease,OHC_L_COMPLETE,OHC_L_RETURNED|
        (clean?OHC_L_CLEANUP:0)|(exited?OHC_L_EXITED:0),1);
    ohc_owner_completed(&f->owner,f->owner.generation,c,exited,ohc_lease_now()); drain(f);
}
static int owner_case(const char *which,int dir,int channel,pid_t guard) {
    fixture f={0}; f.dir=dir;
    CHECK(ohc_lease_adopt(&f.lease,channel,1,ohc_lease_now()+240000));
    ohc_owner_init(&f.owner,effect,&f); f.owner.test_admit=admit;
    f.peer=(ohc_owner_peer){.connection=1,.endpoint_device=1,.endpoint_inode=2,
        .policy_epoch=0x54455354,.kernel_verified=true,.endpoint_verified=true};
    f.peer.token[1]=f.peer.token[2]=(uint32_t)geteuid(); f.peer.token[5]=(uint32_t)getpid(); f.peer.token[7]=1;
    CHECK(ohc_owner_open(&f.connection,&f.peer));
    CHECK(ohc_owner_feed(&f.owner,&f.connection,&f.peer,"STA",3,ohc_lease_now()));
    CHECK(!f.work);
    CHECK(ohc_owner_feed(&f.owner,&f.connection,&f.peer,"RT\n",3,ohc_lease_now())); drain(&f);
    printf("GUARD_PID=%ld\n",(long)guard); fflush(stdout);
    if(!strcmp(which,"missing_ready")) { CHECK(!f.work&&f.delegated==1); return 0; }
    CHECK(f.work==1&&f.owner.state==OHC_RUNNING);
    if(!strcmp(which,"owner_death")) { _exit(0); }
    if(!strcmp(which,"lost_heartbeat")) {
        pause_ms(OHC_LEASE_HEARTBEAT_MS+200);
        CHECK(faccessat(dir,"restore.once",F_OK,0));
        CHECK(!faccessat(dir,"fence",F_OK,0)); puts("LIVE_UNKNOWN_NO_RESTORE"); return 0;
    }
    if(!strcmp(which,"guard_crash")) {
        CHECK(!kill(guard,SIGKILL)); int status; CHECK(waitpid(guard,&status,0)==guard&&WIFSIGNALED(status));
        CHECK(!ohc_lease_exchange(&f.lease,OHC_L_BEAT,0,0));
        (void)ohc_owner_transport_event(&f.owner,1,"STOP",ohc_lease_now());
        ohc_owner_execution_exited(&f.owner,1,false); drain(&f);
        CHECK(f.clear==1&&f.cancel==1&&f.delegated==1&&!f.released); return 0;
    }
    CHECK(ohc_owner_transport_event(&f.owner,1,"PONG",ohc_lease_now()));
    CHECK(!ohc_owner_pairing(&f.owner,1));
    CHECK(ohc_owner_transport_event(&f.owner,1,"RFCOMM_READY",ohc_lease_now()));
    CHECK(!ohc_owner_pairing(&f.owner,1));
    CHECK(ohc_owner_transport_event(&f.owner,1,"SDP_READY",ohc_lease_now()));
    CHECK(ohc_owner_pairing(&f.owner,1));
    CHECK(!ohc_owner_transport_event(&f.owner,2,"STOP",ohc_lease_now()));
    if(!strcmp(which,"disconnect")) { ohc_owner_disconnect(&f.owner,&f.connection,ohc_lease_now()); }
    else { CHECK(ohc_owner_feed(&f.owner,&f.connection,&f.peer,"STOP\n",5,ohc_lease_now())); }
    drain(&f); CHECK(f.clear==1&&f.cancel==1);
    (void)ohc_owner_transport_event(&f.owner,1,"CLEANED",ohc_lease_now());
    CHECK(!f.owner.worker_returned&&!f.owner.recovery_verified&&!f.released);
    CHECK(!faccessat(dir,"fence",F_OK,0));
    bool clean=strcmp(which,"cleanup_unknown")!=0, exited=strcmp(which,"exit_unknown")!=0;
    completed(&f,clean,exited);
    if(clean&&exited) {
        CHECK(f.released==1&&!f.delegated);
        int status; CHECK(waitpid(guard,&status,0)==guard&&WIFEXITED(status)&&WEXITSTATUS(status)==0);
    } else {
        CHECK(!f.released&&f.delegated==1);
        /* Late completion must neither undo delegation nor cause two restores. */
        ohc_owner_completed(&f.owner,1,(fe35_scan_completion){true,true,0},true,ohc_lease_now()); drain(&f);
        CHECK(!f.released&&f.delegated==1&&faccessat(dir,"restore.once",F_OK,0));
        puts("LIVE_UNKNOWN_NO_RESTORE");
    }
    ohc_lease_close(&f.lease); return 0;
}
int main(int argc,char **argv) {
    if(argc==2&&!strcmp(argv[1],"clock")) { printf("%lld\n",(long long)ohc_lease_now()); return 0; }
    /* Harness-owned arguments, no deployment entry uses this parser. */
    CHECK(argc==5); const char *mode=argv[1],*guardExe=argv[2],*directory=argv[3],*which=argv[4];
    int dir=open(directory,O_RDONLY|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW); CHECK(dir>=0);
    int channel;
    if(!strcmp(mode,"owner")) {
        pid_t guard=spawn_guard(guardExe,dir,&channel,!strcmp(which,"missing_ready"));
        return owner_case(which,dir,channel,guard);
    }
    CHECK(!strcmp(mode,"relay"));
    /* Relay test-only inherited stdin (Python-created AF_UNIX socket or loopback
     * listener). Guard remains private child of this broker. It never considers
     * a Simulator/loopback connection authenticated deployment provenance. */
    int input=STDIN_FILENO; int listening=0; socklen_t n=sizeof(listening);
    CHECK(!getsockopt(input,SOL_SOCKET,SO_ACCEPTCONN,&listening,&n));
    if(listening) {
        struct pollfd p={input,POLLIN,0}; CHECK(poll(&p,1,45000)==1);
        input=accept(STDIN_FILENO,NULL,NULL); CHECK(input>=0); close(STDIN_FILENO);
    }
    (void)spawn_guard(guardExe,dir,&channel,!strcmp(which,"missing_ready"));
#ifdef __APPLE__
    int one=1; CHECK(!setsockopt(input,SOL_SOCKET,SO_NOSIGPIPE,&one,sizeof(one)));
    CHECK(!setsockopt(channel,SOL_SOCKET,SO_NOSIGPIPE,&one,sizeof(one)));
#endif
    CHECK(!fcntl(input,F_SETFL,O_NONBLOCK)); CHECK(!fcntl(channel,F_SETFL,O_NONBLOCK));
    for(;;) {
        struct pollfd p={input,POLLIN,0};
        if(poll(&p,1,15000)!=1) { break; }
        ohc_lease_frame frame;
        if(!ohc_lease_read(input,&frame,1000)) { break; }
        if(!ohc_lease_write(channel,&frame,1000)||!ohc_lease_read(channel,&frame,1500)||
           !ohc_lease_write(input,&frame,1000)) { break; }
        if(frame.op!=OHC_L_OK) { break; }
    }
    close(input); close(channel);
    /* Parent exits: guard independently observes the kernel relationship change
     * and performs only its injected inert recovery. No force-kill/release. */
    return 0;
}
