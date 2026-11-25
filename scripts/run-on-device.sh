#!/bin/bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
    echo "usage: $0 <configured-ssh-alias>" >&2
    exit 2
fi
host="$1"
ssh "$host" 'uname -m; /usr/bin/openhc-bridge-check'
