#!/usr/bin/env bash
set -euo pipefail
if [[ $# -ne 1 ]]; then
  echo "usage: $0 <configured-ssh-alias>" >&2
  exit 2
fi
host=$1
ssh "$host" 'sh -s' <<'REMOTE'
set -eu
echo "OWNERSHIP_MACHINE=$(uname -m 2>/dev/null || echo UNKNOWN)"
echo "OWNERSHIP_OS=$(sw_vers -productVersion 2>/dev/null || uname -s 2>/dev/null || echo UNKNOWN)"
if [ -S /tmp/BTstack ]; then echo "BTSTACK_SOCKET=PRESENT"; else echo "BTSTACK_SOCKET=ABSENT"; fi
if [ -f /var/jb/usr/bin/BTdaemon ]; then echo "BTDAEMON_FILE=PRESENT"; else echo "BTDAEMON_FILE=ABSENT"; fi
if [ -f /var/jb/Library/LaunchDaemons/ch.ringwald.BTstack.plist ]; then echo "BTSTACK_PLIST=PRESENT"; else echo "BTSTACK_PLIST=ABSENT"; fi
echo "BTSTACK_SERVICE_PRINT_BEGIN"
launchctl print system/ch.ringwald.BTstack 2>&1 || true
echo "BTSTACK_SERVICE_PRINT_END"
echo "BLUETOOTH_PROCESS_SNAPSHOT_BEGIN"
ps -axo pid,ppid,state,comm,args 2>/dev/null | awk 'NR == 1 || /BTdaemon|BTServer|bluetoothd|bluetooth/ {print}' || true
echo "BLUETOOTH_PROCESS_SNAPSHOT_END"
echo "OWNERSHIP_SNAPSHOT_DONE"
REMOTE
