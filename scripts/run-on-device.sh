#!/bin/bash
set -euo pipefail

if [[ $# -lt 1 || $# -gt 2 || ( $# -eq 2 && "$2" != --wifi && "$2" != --auth && "$2" != --version && "$2" != --platform && "$2" != --btstack && "$2" != --btstack-services && "$2" != --btstack-ownership ) ]]; then
    echo "usage: $0 <configured-ssh-alias> [--wifi|--auth|--platform|--btstack|--btstack-services|--btstack-ownership|--version]" >&2
    exit 2
fi
host="$1"
if [[ ${2:-} == --btstack-ownership ]]; then
    "$(dirname "$0")/inspect-btstack-ownership.sh" "$host"
elif [[ ${2:-} == --btstack-services ]]; then
    ssh "$host" 'uname -m && /var/jb/usr/bin/openhc-bridge-check --btstack-services'
elif [[ ${2:-} == --btstack ]]; then
    ssh "$host" 'uname -m && /var/jb/usr/bin/openhc-bridge-check --btstack'
elif [[ ${2:-} == --platform ]]; then
    ssh "$host" 'uname -m && /var/jb/usr/bin/openhc-bridge-check --platform'
elif [[ ${2:-} == --auth ]]; then
    ssh "$host" 'uname -m && /var/jb/usr/bin/openhc-bridge-check --auth'
elif [[ ${2:-} == --version ]]; then
    ssh "$host" 'uname -m && /var/jb/usr/bin/openhc-bridge-check --version'
elif [[ ${2:-} == --wifi ]]; then
    ssh "$host" 'uname -m && /var/jb/usr/bin/openhc-bridge-check --wifi'
else
    ssh "$host" 'uname -m && /var/jb/usr/bin/openhc-bridge-check'
fi
