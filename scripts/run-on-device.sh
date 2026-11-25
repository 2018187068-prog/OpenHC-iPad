#!/bin/bash
set -euo pipefail

if [[ $# -lt 1 || $# -gt 2 || ( $# -eq 2 && "$2" != --wifi ) ]]; then
    echo "usage: $0 <configured-ssh-alias> [--wifi]" >&2
    exit 2
fi
host="$1"
if [[ ${2:-} == --wifi ]]; then
    ssh "$host" 'uname -m && /var/jb/usr/bin/openhc-bridge-check --wifi'
else
    ssh "$host" 'uname -m && /var/jb/usr/bin/openhc-bridge-check'
fi
