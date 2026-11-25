#!/bin/sh
# Independent launchd recovery guard. Never signals Bluetooth processes directly.
# Arguments are fixed by the root-only host driver; mock tools are used in tests.
set -u
state=$1 ctl=$2 timer=$3 ps_tool=$4 clock=$5 sleeper=$6
btstack=$7 bluetool=$8 bluetoothd=$9
socket_path=${10:-/tmp/BTstack}
export PATH=/var/jb/usr/bin:/var/jb/bin:/usr/bin:/bin:/usr/sbin:/sbin
umask 077
log() { printf '%s\n' "$*"; }
bounded() { "$timer" -k 2 8 "$@"; }
registered() { bounded "$ctl" print "system/$1" >/dev/null 2>&1; }
process_absent() {
    snapshot=$(bounded "$ps_tool" -axo pid,ppid,state,comm 2>/dev/null) || return 2
    while read -r pid ppid procstate comm; do
        case "$comm" in "$1"|*"/$1") return 1 ;; esac
    done <<EOF
$snapshot
EOF
    return 0
}
restore() {
    echo RESTORING > "$state/restoring"
    log RECOVERY_RESTORE_BEGIN
    # The host never restores concurrently. This guard is the sole recovery actor.
    bounded "$ctl" unload "$btstack"
    unload_rc=$?
    log "RECOVERY_BTSTACK_UNLOAD_EXIT=$unload_rc"
    n=0
    while [ "$n" -lt 5 ]; do
        if process_absent BTdaemon; then break; fi
        n=$((n + 1)); "$sleeper" 1
    done
    if ! process_absent BTdaemon; then
        log RECOVERY_FAILED_BTDAEMON_STILL_PRESENT_OR_UNKNOWN
        echo FAILED > "$state/result"
        return 1
    fi
    bounded "$ctl" print system/ch.ringwald.BTstack >/dev/null 2>&1
    job_rc=$?
    if [ "$job_rc" -ne 113 ]; then
        log "RECOVERY_FAILED_BTSTACK_ABSENCE_NOT_PROVEN=$job_rc"
        echo FAILED > "$state/result"
        return 1
    fi
    # Only this known launchd socket, after daemon and registration are absent.
    if [ -S "$socket_path" ]; then rm -f "$socket_path"; fi
    bounded "$ctl" load "$bluetool"
    tool_rc=$?
    log "RECOVERY_BLUETOOL_LOAD_EXIT=$tool_rc"
    bounded "$ctl" load "$bluetoothd"
    daemon_rc=$?
    log "RECOVERY_BLUETOOTHD_LOAD_EXIT=$daemon_rc"
    restored=0
    n=0
    while [ "$n" -lt 10 ]; do
        if registered com.apple.BlueTool && registered com.apple.bluetoothd &&
           registered com.apple.BTServer.le && ! process_absent bluetoothd; then
            # A process query error must not satisfy the running condition.
            process_absent bluetoothd
            process_rc=$?
            if [ "$process_rc" -eq 1 ]; then restored=1; break; fi
        fi
        n=$((n + 1)); "$sleeper" 1
    done
    if [ "$restored" -ne 1 ]; then
        log RECOVERY_FAILED_APPLE_STATE
        echo FAILED > "$state/result"
        return 1
    fi
    bounded "$ctl" load "$btstack"
    stack_rc=$?
    log "RECOVERY_BASELINE_BTSTACK_LOAD_EXIT=$stack_rc"
    if ! registered ch.ringwald.BTstack; then
        log RECOVERY_FAILED_BASELINE_REGISTRATION
        echo FAILED > "$state/result"
        return 1
    fi
    log RECOVERY_APPLE_AND_BASELINE_RESTORED
    echo RESTORED > "$state/result"
    return 0
}
if [ -f "$state/result" ]; then
    read -r previous < "$state/result"
    [ "$previous" != RESTORED ] || exit 0
fi
read -r deadline < "$state/deadline" || exit 1
case "$deadline" in ''|*[!0-9]*) exit 1 ;; esac
echo READY > "$state/ready" || exit 1
log RECOVERY_GUARD_READY
while :; do
    now=$(bounded "$clock" +%s) || exit 1
    heartbeat=0
    if [ -f "$state/heartbeat" ]; then read -r heartbeat < "$state/heartbeat" || heartbeat=0; fi
    case "$heartbeat" in ''|*[!0-9]*) heartbeat=0 ;; esac
    if [ -f "$state/restore-request" ]; then log RECOVERY_TRIGGER_REQUEST; break; fi
    if [ "$now" -ge "$deadline" ]; then log RECOVERY_TRIGGER_DEADLINE; break; fi
    if [ $((now - heartbeat)) -gt 20 ]; then log RECOVERY_TRIGGER_HEARTBEAT; break; fi
    "$sleeper" 1
done
restore
