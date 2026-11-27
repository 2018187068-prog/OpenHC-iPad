/* Inert deployment executable. Test builds exercise actual POSIX descriptors,
 * flock/fence files, fork/exec lifetime and bounded I/O. They NEVER control a
 * service/radio. The platform Trial recovery adapter is deliberately absent. */
#if defined(__linux__) && !defined(_POSIX_C_SOURCE)
#define _POSIX_C_SOURCE 200809L
#endif
#include "ScanLeaseChannel.h"
#include <stdio.h>
#ifdef OPENHC_SCAN_OWNER_PROCESS_TEST
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <signal.h>
#include <string.h>
#include <sys/file.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <unistd.h>
static bool note(int dir,const char *name,const char *text,int flags) {
    int fd=openat(dir,name,O_WRONLY|O_CREAT|O_NOFOLLOW|O_CLOEXEC|flags,0600);
    if(fd<0) { return false; }
    struct stat s; size_t n=strlen(text);
    bool ok=!fstat(fd,&s)&&S_ISREG(s.st_mode)&&s.st_uid==geteuid()&&
        (s.st_mode&0777)==0600&&s.st_nlink==1&&write(fd,text,n)==(ssize_t)n&&!fsync(fd);
    close(fd); return ok;
}
static void delegate(int dir,bool *once) {
    if(!*once) { *once=true; (void)note(dir,"events","DELEGATE_ONCE\n",O_APPEND); }
}
static bool recover(int dir,ohc_lease_guard *s,int finalization) {
    /* Test-only independent recovery effect: no OFF/launchctl or controller.
     * The exclusive file demonstrates idempotence across process boundaries. */
    if(!note(dir,"restore.once","INERT_RECOVERY_VERIFIED\n",O_EXCL)) { return false; }
    if(!note(dir,"events","INERT_RESTORE_ONCE\n",O_APPEND)) { return false; }
    /* Effect evidence is NOT completion. These test-build-only fault gates
     * make the pre-unlink observation window deterministic, without sleeps in
     * the observer or any deployment/environment-controlled recovery mode. */
    if(finalization==1) {
        if(!note(dir,"events","TEST_FINALIZATION_WAIT\n",O_APPEND)) { return false; }
        int64_t until=ohc_lease_now()+3000;
        for(;;) {
            int gate=openat(dir,"finalize.release",O_RDONLY|O_NOFOLLOW|O_CLOEXEC);
            if(gate>=0) {
                struct stat st; char byte=0;
                bool ok=!fstat(gate,&st)&&S_ISREG(st.st_mode)&&st.st_uid==geteuid()&&
                    (st.st_mode&0777)==0600&&st.st_nlink==1&&st.st_size==1&&read(gate,&byte,1)==1&&byte=='1';
                close(gate); if(!ok) { return false; } break;
            }
            if(errno!=ENOENT||ohc_lease_now()>=until) { return false; }
            (void)poll(NULL,0,20);
        }
    } else if(finalization==2) {
        (void)note(dir,"events","TEST_FINALIZATION_FAILED\n",O_APPEND); return false;
    }
    if(unlinkat(dir,"fence",0) || fsync(dir)) { return false; }
    /* Only this later record may be observed as final completion: the effect
     * and required fence removal/directory sync have already succeeded. */
    if(!note(dir,"events","INERT_RECOVERY_COMPLETED\n",O_APPEND)) { return false; }
    s->restored=true; return true;
}
static int run_guard(bool missingReady,int finalization) {
    const int channel=3,dir=4;
    pid_t originalParent=getppid();
    if(originalParent<=1) { return 78; }
    /* Broker allowlist survives exec: no extra file/socket capability leaks.
     * 0..2 are diagnostic streams in this fixture, never deployment grants. */
    long maximum=sysconf(_SC_OPEN_MAX);
    if(maximum<0 || maximum>1048576) { return 78; }
    for(int fd=5;fd<maximum;++fd) { close(fd); }
    struct stat d,s; struct sockaddr_un peer; socklen_t n=sizeof(peer);
    if(fstat(dir,&d)||!S_ISDIR(d.st_mode)||d.st_uid!=geteuid()||(d.st_mode&0777)!=0700||
       fstat(channel,&s)||!S_ISSOCK(s.st_mode)||getpeername(channel,(struct sockaddr *)&peer,&n)||
       peer.sun_family!=AF_UNIX||fcntl(channel,F_SETFD,FD_CLOEXEC)||fcntl(dir,F_SETFD,FD_CLOEXEC)||
       fcntl(channel,F_SETFL,O_NONBLOCK)) { return 78; }
#ifdef __APPLE__
    int one=1;
    if(setsockopt(channel,SOL_SOCKET,SO_NOSIGPIPE,&one,sizeof(one))) { return 78; }
#endif
    int lock=openat(dir,"active.lock",O_RDWR|O_CREAT|O_NOFOLLOW|O_CLOEXEC,0600);
    if(lock<0||fstat(lock,&s)||!S_ISREG(s.st_mode)||s.st_uid!=geteuid()||
       (s.st_mode&0777)!=0600||s.st_nlink!=1||flock(lock,LOCK_EX|LOCK_NB)||
       !note(dir,"fence","UNRESOLVED_OWNER\n",O_EXCL)||fsync(dir)) { return 78; }
    if(!note(dir,"events","GUARD_LOCKED_PRIVATE_FDS\n",O_APPEND)) { return 78; }
    ohc_lease_guard state={0}; bool delegated=false, connected=true;
    int64_t bootstrap=ohc_lease_now()+3000;
    for(;;) {
        int64_t now=ohc_lease_now();
        /* Parent relationship is kernel-maintained. No claimed PID, kill(pid,0)
         * or last_pid token is used as process-incarnation/exit authority. */
        if(getppid()!=originalParent) {
            delegate(dir,&delegated);
            (void)note(dir,"events","PARENT_EXIT_OBSERVED\n",O_APPEND);
            return recover(dir,&state,finalization)?0:79;
        }
        if((!state.armed&&now>=bootstrap)||ohc_lease_overdue(&state,now)) {
            delegate(dir,&delegated); state.delegated=true;
            if(!state.armed||now>=state.deadline) {
                (void)note(dir,"events","UNRESOLVED_FENCE_RETAINED\n",O_APPEND); return 79;
            }
        }
        struct pollfd p={connected?channel:-1,POLLIN,0};
        int r=poll(&p,1,20);
        if(r<0 && errno==EINTR) { continue; }
        if(r<0) { delegate(dir,&delegated); return 79; }
        if(!r) { continue; }
        ohc_lease_frame frame;
        if(!ohc_lease_read(channel,&frame,1000)) {
            delegate(dir,&delegated); state.delegated=true;
            close(channel); connected=false; continue;
        }
        bool accepted=ohc_lease_step(&state,&frame,ohc_lease_now());
        if(accepted&&frame.op==OHC_L_ARM) {
            (void)note(dir,"events","ARM_IMMUTABLE\n",O_APPEND);
            if(missingReady) { continue; }
        }
        if(accepted&&frame.op==OHC_L_TAKEOVER) {
            accepted=note(dir,"events","INERT_TAKEOVER\n",O_APPEND);
        }
        if(accepted&&frame.op==OHC_L_COMPLETE) {
            (void)note(dir,"events",state.safe?"RETURN_CLEAN_EXITED\n":"RETURN_UNCERTAIN\n",O_APPEND);
        }
        if(accepted&&frame.op==OHC_L_RESTORE) { accepted=recover(dir,&state,finalization); }
        if(!accepted||frame.op==OHC_L_DELEGATE) { delegate(dir,&delegated); state.delegated=true; }
        frame.op=accepted?OHC_L_OK:OHC_L_DENIED; frame.flags=0; frame.status=0;
        if(!ohc_lease_write(channel,&frame,1000)) {
            delegate(dir,&delegated); state.delegated=true; close(channel); connected=false;
        }
        if(state.restored) { close(lock); return 0; }
    }
}
#endif
int main(int argc,char **argv) {
#ifdef OPENHC_SCAN_OWNER_PROCESS_TEST
    if(argc==1) { return run_guard(false,0); }
    if(argc==2&&!strcmp(argv[1],"--test-missing-ready")) { return run_guard(true,0); }
    if(argc==2&&!strcmp(argv[1],"--test-finalize-hold")) { return run_guard(false,1); }
    if(argc==2&&!strcmp(argv[1],"--test-finalize-fail")) { return run_guard(false,2); }
#else
    (void)argc; (void)argv;
#endif
    fputs("SCAN_GUARD_UNAVAILABLE_DEPLOYMENT_DENY_ALL\n",stderr); return 78;
}
