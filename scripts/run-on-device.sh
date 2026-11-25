#!/bin/bash
set -euo pipefail

if [[ $# -lt 1 || $# -gt 2 || ( $# -eq 2 && "$2" != --wifi && "$2" != --auth && "$2" != --version ) ]]; then
    echo "usage: $0 <configured-ssh-alias> [--wifi|--auth|--version]" >&2
    exit 2
fi
host="$1"
if [[ ${2:-} == --auth ]]; then
    ssh "$host" 'uname -m && /var/jb/usr/bin/openhc-bridge-check --auth'
elif [[ ${2:-} == --version ]]; then
    ssh "$host" 'uname -m && /var/jb/usr/bin/openhc-bridge-check --version'
elif [[ ${2:-} == --wifi ]]; then
    ssh "$host" 'uname -m && /var/jb/usr/bin/openhc-bridge-check --wifi'
else
    ssh "$host" 'uname -m && /var/jb/usr/bin/openhc-bridge-check'
fi
