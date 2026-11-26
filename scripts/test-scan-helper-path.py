#!/usr/bin/env python3
"""Keep the helper and UIKit AF_UNIX endpoint on a shared short alias."""
import pathlib
import re


ROOT = pathlib.Path(__file__).resolve().parents[1]
HEADER = ROOT / 'theos/scan-supervisor/ScanHelperPath.h'
SERVER = ROOT / 'theos/scan-supervisor/main.c'
CLIENT = ROOT / 'theos/scan-supervisor/ScanHelperClient.m'


def main():
    header = HEADER.read_text(encoding='utf-8')
    server = SERVER.read_text(encoding='utf-8')
    client = CLIENT.read_text(encoding='utf-8')
    defs = dict(re.findall(r'^#define\s+(OHC_SCAN_HELPER_(?:RUNTIME|SOCKET|LOCK)_PATH)\s+(.+)$',
                           header, re.MULTILINE))
    assert defs.get('OHC_SCAN_HELPER_RUNTIME_PATH') == '"/var/jb/var/run/openhc"'
    assert defs.get('OHC_SCAN_HELPER_SOCKET_PATH') == 'OHC_SCAN_HELPER_RUNTIME_PATH "/scan-ping.sock"'
    assert defs.get('OHC_SCAN_HELPER_LOCK_PATH') == 'OHC_SCAN_HELPER_RUNTIME_PATH "/scan-ping.lock"'
    expected = '/var/jb/var/run/openhc/scan-ping.sock'
    assert len(expected.encode('ascii')) < 104, 'socket path must fit Darwin sun_path[104] with NUL'
    assert '#include "ScanHelperPath.h"' in server
    assert '#import "ScanHelperPath.h"' in client
    assert '#define HELPER_SOCKET_PATH OHC_SCAN_HELPER_SOCKET_PATH' in server
    assert 'lstat(OHC_SCAN_HELPER_RUNTIME_PATH' in server
    assert 'const char *path = OHC_SCAN_HELPER_SOCKET_PATH;' in client
    assert 'ROOT_PATH(' not in server and 'ROOT_PATH(' not in client
    # Keep the runtime rejection: no truncating a too-long path into sun_path.
    assert 'strlen(socketPath) >= sizeof(((struct sockaddr_un *)0)->sun_path)) return 11;' in server
    print('SCAN_HELPER_SHARED_SHORT_PATH_OK bytes=' + str(len(expected)))


if __name__ == '__main__':
    main()
