"""Capture one bounded, read-only BTstack session metadata snapshot over USB SSH."""
import argparse
import getpass
import json
import pathlib
import sys
import time

try:
    import paramiko
except ModuleNotFoundError:
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'tools/python-ssh'))
    import paramiko

REMOTE_COMMAND = r'''set +e
start=$(/var/jb/usr/bin/date +%s) || exit 21
owner=$(/var/jb/usr/bin/timeout -k 1 2 /var/jb/usr/bin/openhc-bridge-check --session-owner 2>&1); owner_rc=$?
processes=$(/bin/ps -axo pid,ppid,state,comm 2>&1); ps_rc=$?
if [ -e /tmp/showcase_bt_owned ]; then marker=1; else marker=0; fi
/var/jb/usr/bin/timeout -k 1 3 /var/jb/usr/bin/launchctl print system/io.github.gcbond.openhc.stage0-power-recovery >/dev/null 2>&1
guard_rc=$?
end=$(/var/jb/usr/bin/date +%s) || exit 22
printf 'CAPTURE_BEGIN=%s\nOWNER_RC=%s\n' "$start" "$owner_rc"
printf '%s\nPROCESS_RC=%s\n' "$owner" "$ps_rc"
printf 'PROCESS_BEGIN\n%s\nPROCESS_END\nMARKER=%s\nGUARD_RC=%s\nCAPTURE_END=%s\n' "$processes" "$marker" "$guard_rc" "$end"
'''

HELPER_NAMES = {'CarPlay Simulator', 'CarPlay Simulato', 'carplay_services'}
BROKER_NAMES = HELPER_NAMES


def parse_capture(raw):
    """Parse a single bounded capture; incomplete or unrecognized data stays UNKNOWN."""
    try:
        text = raw.decode('utf-8', errors='strict') if isinstance(raw, bytes) else raw
        lines = text.splitlines()
        process_start = lines.index('PROCESS_BEGIN')
        process_end = lines.index('PROCESS_END', process_start + 1)
        owner_line = next(line for line in lines if line.startswith('SESSION_SOCKET_OWNER_PID='))
        owner_pid = int(owner_line.partition('=')[2])
        start = int(_field(lines, 'CAPTURE_BEGIN'))
        end = int(_field(lines, 'CAPTURE_END'))
        owner_rc = int(_field(lines, 'OWNER_RC'))
        ps_rc = int(_field(lines, 'PROCESS_RC'))
        guard_rc = int(_field(lines, 'GUARD_RC'))
        marker = _field(lines, 'MARKER')
        if owner_rc != 0 or ps_rc != 0 or guard_rc not in (0, 113) or marker not in ('0', '1'):
            raise ValueError('CAPTURE_COMPONENT_FAILED')
        if end < start or end - start > 4:
            raise ValueError('CAPTURE_WINDOW_INVALID')
        comm = {}
        helpers = set()
        for line in lines[process_start + 1:process_end]:
            parts = line.strip().split(None, 3)
            if len(parts) != 4 or not parts[0].isdigit():
                continue
            pid, name = int(parts[0]), parts[3].rstrip().rsplit('/', 1)[-1]
            comm[pid] = name
            if name in HELPER_NAMES:
                helpers.add(pid)
        if owner_pid not in comm:
            raise ValueError('OWNER_MISSING_FROM_PROCESS_SNAPSHOT')
        broker_pid = owner_pid if comm[owner_pid] in BROKER_NAMES else None
        return {
            'captured_at_epoch': (start + end) / 2,
            'snapshot_complete': True,
            'shared_helper_pids': sorted(helpers),
            'broker_owner_pid': owner_pid,
            'broker_comm_pid': broker_pid,
            'active_session_pids': [],
            'recovery_active': guard_rc == 0,
            'ownership_marker': marker == '1',
            'capture_window_seconds': end - start,
        }
    except (StopIteration, ValueError, UnicodeError) as error:
        return unknown_snapshot(str(error) or 'CAPTURE_INVALID')


def unknown_snapshot(reason):
    return {
        'captured_at_epoch': 0,
        'snapshot_complete': False,
        'shared_helper_pids': [],
        'broker_owner_pid': None,
        'broker_comm_pid': None,
        'active_session_pids': [],
        'recovery_active': True,
        'ownership_marker': None,
        'capture_error': reason,
    }


def _field(lines, name):
    prefix = name + '='
    return next(line[len(prefix):] for line in lines if line.startswith(prefix))


def capture(client):
    transport = client.get_transport()
    channel = transport.open_session(timeout=4)
    channel.settimeout(8)
    channel.set_combine_stderr(True)
    channel.exec_command(REMOTE_COMMAND)
    output = bytearray()
    deadline = time.monotonic() + 8
    try:
        while not channel.exit_status_ready() or channel.recv_ready():
            if channel.recv_ready():
                output.extend(channel.recv(min(4096, 16385 - len(output))))
                if len(output) > 16384:
                    raise RuntimeError('CAPTURE_OUTPUT_LIMIT')
            elif not channel.exit_status_ready():
                if time.monotonic() >= deadline:
                    raise TimeoutError('CAPTURE_REMOTE_TIMEOUT')
                time.sleep(.02)
        if channel.recv_exit_status() != 0:
            raise RuntimeError('CAPTURE_REMOTE_COMMAND_FAILED')
        return parse_capture(bytes(output))
    finally:
        channel.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', action='store_true', help='Connect through the existing USB SSH tunnel and capture fresh metadata')
    parser.add_argument('--output', type=pathlib.Path, default=pathlib.Path('session-evidence.json'))
    args = parser.parse_args()
    if not args.capture:
        print('NO_DEVICE_ACTION: pass --capture explicitly')
        return 2
    password = getpass.getpass('iPad SSH password: ')
    if not password:
        raise SystemExit('No authentication input')
    client = paramiko.SSHClient()
    client.load_host_keys(str(pathlib.Path.home() / '.ssh/known_hosts'))
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    try:
        client.connect('127.0.0.1', port=2222, username='root', password=password,
                       allow_agent=False, look_for_keys=False, timeout=8,
                       auth_timeout=15, banner_timeout=8)
        password = None
        try:
            evidence = capture(client)
        except Exception as error:
            evidence = unknown_snapshot(type(error).__name__)
    finally:
        password = None
        client.close()
    args.output.write_text(json.dumps(evidence, indent=2) + '\n', encoding='utf-8')
    print('SESSION_EVIDENCE_SNAPSHOT=' + ('COMPLETE' if evidence['snapshot_complete'] else 'UNKNOWN'))
    print('SESSION_EVIDENCE_PATH=' + str(args.output))
    return 0 if evidence['snapshot_complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
