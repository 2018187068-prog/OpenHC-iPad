#!/usr/bin/env bash
set -euo pipefail
if [[ $# -ne 1 ]]; then
  echo "usage: $0 <configured-ssh-alias>" >&2
  exit 2
fi
host=$1
ssh "$host" 'sh -s' <<'REMOTE'
set -eu
export PATH=/var/jb/usr/bin:/var/jb/bin:/var/jb/usr/sbin:/var/jb/sbin:/usr/bin:/bin:/usr/sbin:/sbin
if [ "$(id -u)" != 0 ]; then
  echo "OWNERSHIP_ROOT_REQUIRED"
  exit 1
fi
command -v launchctl >/dev/null 2>&1 || { echo "OWNERSHIP_LAUNCHCTL_UNAVAILABLE"; exit 1; }
command -v ps >/dev/null 2>&1 || { echo "OWNERSHIP_PS_UNAVAILABLE"; exit 1; }
echo "OWNERSHIP_MACHINE=$(uname -m 2>/dev/null || echo UNKNOWN)"
echo "OWNERSHIP_OS=$(sw_vers -productVersion 2>/dev/null || uname -s 2>/dev/null || echo UNKNOWN)"
if [ -S /tmp/BTstack ]; then echo "BTSTACK_SOCKET=PRESENT"; else echo "BTSTACK_SOCKET=ABSENT"; fi
if [ -f /var/jb/usr/bin/BTdaemon ]; then echo "BTDAEMON_FILE=PRESENT"; else echo "BTDAEMON_FILE=ABSENT"; fi
if [ -f /var/jb/Library/LaunchDaemons/ch.ringwald.BTstack.plist ]; then echo "BTSTACK_PLIST=PRESENT"; else echo "BTSTACK_PLIST=ABSENT"; fi
for label in ch.ringwald.BTstack com.apple.bluetoothd com.apple.BlueTool com.apple.BTServer.le com.apple.BTServer.avrcp com.apple.BTServer.map com.apple.BTServer.pbap com.reng.showcase.bluetooth-recovery; do
  printf 'OWNERSHIP_SERVICE_PRINT_BEGIN=%s\n' "$label"
  service_status=0
  launchctl print "system/$label" 2>&1 || service_status=$?
  printf 'OWNERSHIP_SERVICE_PRINT_EXIT=%s\n' "$service_status"
  printf 'OWNERSHIP_SERVICE_PRINT_END=%s\n' "$label"
done
echo "BLUETOOTH_PROCESS_SNAPSHOT_BEGIN"
if process_snapshot=$(ps -axo pid,ppid,state,comm 2>&1); then
  printf '%s\n' "$process_snapshot" | while IFS= read -r line; do
    case "$line" in
      *PID*|*BTdaemon*|*BTServer*|*BTLEServer*|*BTAvrcp*|*BTMap*|*BTPbap*|*bluetoothd*|*BlueTool*|*CarDisplaySim*|*Showcase*) printf '%s\n' "$line" ;;
    esac
  done
else
  printf '%s\n' "$process_snapshot"
  echo "OWNERSHIP_PS_FAILED"
  exit 1
fi
echo "BLUETOOTH_PROCESS_SNAPSHOT_END"
for file in /var/root/Library/ShowcaseBluetooth/ready /var/root/Library/ShowcaseBluetooth/recovery.plist /tmp/showcase_bt_owned /tmp/showcase_bt_ready; do
  if [ -e "$file" ]; then
    printf 'OWNERSHIP_MARKER_PRESENT=%s\n' "$file"
  else
    printf 'OWNERSHIP_MARKER_ABSENT=%s\n' "$file"
  fi
done
echo "OWNERSHIP_CAPTURE_ONLY=1"
echo "OWNERSHIP_SNAPSHOT_DONE"
REMOTE
