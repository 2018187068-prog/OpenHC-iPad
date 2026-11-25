"""One guarded power-only trial over existing USB SSH; no peer operations.

Requires Paramiko. Password input is read from stdin, never stored in artifacts.
The independent device guard owns restoration, including on host/SSH failure.
"""
import argparse
import datetime
import getpass
import pathlib
import plistlib
import shlex
import socket
import struct
import sys
import threading
import time
import uuid

try:
    import paramiko
except ModuleNotFoundError:
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'tools/python-ssh'))
    import paramiko

ROOT = pathlib.Path(__file__).resolve().parents[1]
REMOTE_BASE = '/var/root/Library/OpenHCStage0Power'
LABEL = 'io.github.gcbond.openhc.stage0-power-recovery'
CTL = '/var/jb/usr/bin/launchctl'
TIMER = '/var/jb/usr/bin/timeout'
PS = '/bin/ps'
DATE = '/var/jb/usr/bin/date'
SLEEP = '/var/jb/usr/bin/sleep'
BTSTACK = '/var/jb/Library/LaunchDaemons/ch.ringwald.BTstack.plist'
BLUETOOL = '/System/Library/LaunchDaemons/com.apple.BlueTool.plist'
BLUETOOTHD = '/System/Library/LaunchDaemons/com.apple.bluetoothd.plist'
SOCKET = '/tmp/BTstack'


class FixedStreamlocalTransport(paramiko.Transport):
    """Add OpenSSH PROTOCOL section 2.4 fields to this one fixed endpoint.

    Paramiko constructs/owns the channel and handles its window/lifetime.
    This narrow hook only appends the extension's otherwise missing fields.
    """
    def _send_user_message(self, message):
        raw = message.asbytes()
        if raw[:1] == b'\x5a':
            kind = paramiko.Message(raw[1:]).get_text()
            if kind == 'direct-streamlocal@openssh.com':
                message.add_string(SOCKET)
                message.add_string('')
                message.add_int(0)
        return super()._send_user_message(message)


class PowerProtocol:
    def __init__(self, channel, emit=print):
        self.channel = channel
        self.emit = emit
        self.frames = 0

    def exact(self, size, deadline):
        result = bytearray()
        while len(result) < size:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('PROTOCOL_DEADLINE')
            self.channel.settimeout(min(remaining, 1))
            try:
                part = self.channel.recv(size - len(result))
            except socket.timeout:
                continue
            if not part:
                raise RuntimeError('PROTOCOL_EOF')
            result.extend(part)
        return bytes(result)

    def command(self, ocf, value=None):
        # No generic opcode interface: only state and this client's power lease.
        if ocf not in (1, 2) or (ocf == 2 and value not in (0, 1)) or (ocf == 1 and value is not None):
            raise ValueError('DISALLOWED_POWER_COMMAND')
        params = b'' if value is None else bytes([value])
        body = struct.pack('<HB', 0xf400 | ocf, len(params)) + params
        self.channel.settimeout(4)
        self.channel.sendall(struct.pack('<HHH', 1, 0, len(body)) + body)

    def state(self, deadline):
        while time.monotonic() < deadline:
            self.frames += 1
            if self.frames > 512:
                raise RuntimeError('PROTOCOL_EVENT_LIMIT')
            packet_type, channel, size = struct.unpack('<HHH', self.exact(6, deadline))
            if size > 1024:
                raise RuntimeError('PROTOCOL_OVERSIZE')
            body = self.exact(size, deadline)
            if packet_type != 4:
                raise RuntimeError('PROTOCOL_UNEXPECTED_PACKET_TYPE')
            if channel != 0 or size < 2 or body[1] != size - 2:
                raise RuntimeError('PROTOCOL_EVENT_SHAPE')
            if body[0] == 0x62:
                raise RuntimeError('CONTROLLER_POWERON_FAILED')
            if body[0] == 0x60:
                if size != 3 or body[2] > 4:
                    raise RuntimeError('PROTOCOL_STATE_SHAPE')
                self.emit('BTSTACK_OBSERVED_STATE=' + str(body[2]))
                return body[2]
            if body[0] in (0x16, 0x17, 0x18, 0x31, 0x32, 0x33, 0x34, 0x35, 0x36):
                raise RuntimeError('UNEXPECTED_PEER_SECURITY_EVENT')
        raise TimeoutError('PROTOCOL_DEADLINE')

    def wait_state(self, expected, seconds):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if self.state(deadline) == expected:
                return
        raise TimeoutError('EXPECTED_STATE_TIMEOUT')

    def run(self):
        self.command(1)
        if self.state(time.monotonic() + 4) != 0:
            raise RuntimeError('INITIAL_STATE_NOT_OFF')
        requested = False
        try:
            requested = True
            self.command(2, 1)
            self.wait_state(2, 25)
            self.emit('BTSTACK_POWER_WORKING')
        finally:
            if requested:
                self.command(2, 0)
                self.wait_state(0, 15)
                self.emit('BTSTACK_POWER_OFF_OBSERVED')


class Trial:
    def __init__(self, client, log):
        self.client = client
        self.log = log
        self.run_id = datetime.datetime.now().strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:8]
        self.state = REMOTE_BASE + '/' + self.run_id
        self.stop_heartbeat = threading.Event()
        self.heartbeat_thread = None
        self.guard_loaded = False
        self.locked = False

    def emit(self, text):
        print(text, flush=True)
        self.log.write(text + '\n')
        self.log.flush()

    def execute(self, command, allowed=(0,), seconds=12, record=True):
        channel = self.client.get_transport().open_session(timeout=4)
        channel.settimeout(seconds)
        channel.set_combine_stderr(True)
        channel.exec_command(command)
        output = bytearray()
        deadline = time.monotonic() + seconds
        try:
            while not channel.exit_status_ready() or channel.recv_ready():
                if time.monotonic() >= deadline:
                    raise TimeoutError('REMOTE_COMMAND_DEADLINE')
                if channel.recv_ready():
                    output.extend(channel.recv(65536))
                    if len(output) > 65536:
                        raise RuntimeError('REMOTE_OUTPUT_LIMIT')
                else:
                    time.sleep(.05)
            status = channel.recv_exit_status()
        finally:
            channel.close()
        text = output.decode('utf-8', errors='replace')
        if record and text.strip():
            self.emit(text.rstrip())
        if status not in allowed:
            raise RuntimeError('REMOTE_COMMAND_EXIT=' + str(status))
        return status, text

    def control(self, verb, target, allowed=(0,)):
        command = shlex.join([TIMER, '-k', '2', '8', CTL, verb, target])
        return self.execute(command, allowed=allowed)

    def service(self, label):
        status, output = self.control('print', 'system/' + label, (0, 113))
        return None if status == 113 else output

    def processes(self):
        _, output = self.execute(PS + ' -axo pid,ppid,state,comm', record=False)
        return [line for line in output.splitlines() if any(name in line for name in
            ('BTdaemon', 'bluetoothd', 'BlueTool', 'BTLEServer', 'CarDisplaySim', 'CarPlay Simulat', 'carplay_bt', 'carplay_services', 'Showcase'))]

    @staticmethod
    def named(lines, name):
        for line in lines:
            fields = line.split(None, 3)
            if len(fields) == 4 and fields[3].rstrip().rsplit('/', 1)[-1] == name:
                return True
        return False

    def upload(self, path, content):
        channel = self.client.get_transport().open_session(timeout=4)
        channel.settimeout(10)
        channel.exec_command('umask 077; cat > ' + shlex.quote(path))
        channel.sendall(content)
        channel.shutdown_write()
        status = channel.recv_exit_status()
        channel.close()
        if status:
            raise RuntimeError('UPLOAD_FAILED')

    def heartbeat(self):
        try:
            while not self.stop_heartbeat.wait(2):
                self.execute(DATE + ' +%s > ' + shlex.quote(self.state + '/heartbeat'), record=False)
        except Exception:
            self.emit('HEARTBEAT_CHANNEL_FAILED_GUARD_WILL_RESTORE')

    def preflight(self):
        self.execute("test \"$(id -u)\" = 0 && test \"$(uname -m)\" = iPad5,1")
        for path in (CTL, TIMER, PS, DATE, SLEEP):
            self.execute('test -x ' + shlex.quote(path), record=False)
        if self.service(LABEL) is not None:
            raise RuntimeError('EXISTING_RECOVERY_JOB_REQUIRES_REVIEW')
        for label in ('ch.ringwald.BTstack', 'com.apple.bluetoothd', 'com.apple.BlueTool', 'com.apple.BTServer.le'):
            if self.service(label) is None:
                raise RuntimeError('BASELINE_JOB_MISSING=' + label)
        lines = self.processes()
        for name in ('CarPlay Simulator', 'CarPlay Simulato', 'carplay_services'):
            if self.named(lines, name):
                # This executable also hosts a persistent BAA broker. Its name
                # alone cannot establish an active session or BTstack client.
                raise RuntimeError('SHARED_HELPER_ROLE_UNVERIFIED=' + name)
        for name in ('CarDisplaySim', 'carplay_bt'):
            if self.named(lines, name):
                raise RuntimeError('COMPETING_HELPER=' + name)
        if self.service('com.reng.showcase.bluetooth-recovery') is not None:
            raise RuntimeError('COMPETING_SHOWCASE_RECOVERY')
        self.execute('test ! -e /tmp/showcase_bt_owned')
        if not self.named(lines, 'bluetoothd'):
            raise RuntimeError('BASELINE_BLUETOOTHD_NOT_RUNNING')
        self.emit('BASELINE_PROCESSES_BEGIN\n' + '\n'.join(lines) + '\nBASELINE_PROCESSES_END')
        # This observes current pre-trial state, not a repeat version/query test.
        channel = self.client.get_transport().open_channel('direct-streamlocal@openssh.com', timeout=4)
        try:
            protocol = PowerProtocol(channel, self.emit)
            protocol.command(1)
            if protocol.state(time.monotonic() + 4) != 0:
                raise RuntimeError('BASELINE_BTSTACK_NOT_OFF')
        finally:
            channel.close()
        self.emit('POWER_PREFLIGHT_OK')

    def arm(self):
        self.execute('umask 077; mkdir -p ' + REMOTE_BASE + '; test ! -L ' + REMOTE_BASE +
                     '; mkdir ' + REMOTE_BASE + '/active')
        self.locked = True
        self.execute('umask 077; mkdir ' + shlex.quote(self.state))
        guard_path = self.state + '/recovery.sh'
        self.upload(guard_path, (ROOT / 'scripts/btstack-power-recovery.sh').read_bytes().replace(b'\r\n', b'\n'))
        self.execute('now=$(' + DATE + ' +%s); echo "$now" > ' + self.state + '/heartbeat; echo $((now + 120)) > ' + self.state + '/deadline')
        job = {'Label': LABEL, 'ProgramArguments': ['/var/jb/bin/sh', guard_path, self.state, CTL, TIMER, PS, DATE, SLEEP, BTSTACK, BLUETOOL, BLUETOOTHD],
               'RunAtLoad': True, 'KeepAlive': {'SuccessfulExit': False}, 'ThrottleInterval': 5,
               'StandardOutPath': self.state + '/recovery.log', 'StandardErrorPath': self.state + '/recovery.log',
               'EnvironmentVariables': {'PATH': '/var/jb/usr/bin:/var/jb/bin:/usr/bin:/bin:/usr/sbin:/sbin'}}
        self.upload(self.state + '/recovery.plist', plistlib.dumps(job))
        self.guard_loaded = True
        self.control('load', self.state + '/recovery.plist')
        for _ in range(20):
            _, ready = self.execute('if [ -f ' + self.state + '/ready ]; then cat ' + self.state + '/ready; fi', record=False)
            if ready.strip() == 'READY':
                if self.service(LABEL) is None:
                    raise RuntimeError('GUARD_NOT_REGISTERED')
                self.heartbeat_thread = threading.Thread(target=self.heartbeat, daemon=True)
                self.heartbeat_thread.start()
                self.emit('INDEPENDENT_RECOVERY_READY')
                return
            time.sleep(.25)
        raise RuntimeError('RECOVERY_READY_TIMEOUT')

    def assert_guard(self):
        _, result = self.execute('if [ -f ' + self.state + '/restoring ]; then echo RESTORING; fi; '
                                 'if [ -f ' + self.state + '/result ]; then cat ' + self.state + '/result; fi; '
                                 'now=$(' + DATE + ' +%s); read deadline < ' + self.state + '/deadline; '
                                 'test $((deadline - now)) -ge 65', record=False)
        if result.strip() or self.service(LABEL) is None:
            raise RuntimeError('GUARD_ALREADY_RESTORING_OR_FINISHED')

    def takeover(self):
        self.assert_guard()
        self.control('unload', BLUETOOTHD)
        self.control('unload', BLUETOOL)
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            lines = self.processes()
            if not self.named(lines, 'bluetoothd') and not self.named(lines, 'BlueTool'):
                break
            time.sleep(.2)
        else:
            raise RuntimeError('APPLE_PROCESSES_DID_NOT_EXIT')
        for label in ('com.apple.bluetoothd', 'com.apple.BlueTool'):
            if self.service(label) is not None:
                raise RuntimeError('APPLE_JOB_STILL_REGISTERED=' + label)
        self.emit('APPLE_REQUIRED_SERVICES_RELEASED')
        self.assert_guard()
        self.control('unload', BTSTACK)
        if self.named(self.processes(), 'BTdaemon') or self.service('ch.ringwald.BTstack') is not None:
            raise RuntimeError('OLD_BTSTACK_DID_NOT_EXIT')
        self.execute('if [ -S /tmp/BTstack ]; then rm -f /tmp/BTstack; fi')
        self.control('load', BTSTACK)
        if self.service('ch.ringwald.BTstack') is None:
            raise RuntimeError('NEW_BTSTACK_NOT_REGISTERED')
        self.execute('test -S /tmp/BTstack')
        self.assert_guard()

    def restore(self):
        if not self.guard_loaded:
            return False
        self.execute('touch ' + self.state + '/restore-request', record=False)
        deadline = time.monotonic() + 65
        result = ''
        while time.monotonic() < deadline:
            _, result = self.execute('if [ -f ' + self.state + '/result ]; then cat ' + self.state + '/result; fi', record=False)
            if result.strip() in ('RESTORED', 'FAILED'):
                break
            time.sleep(1)
        self.execute('cat ' + self.state + '/recovery.log')
        if result.strip() != 'RESTORED':
            self.emit('RESTORATION_NOT_PASSED_GUARD_REMAINS_ARMED')
            return False
        for label in ('com.apple.BlueTool', 'com.apple.bluetoothd', 'com.apple.BTServer.le', 'ch.ringwald.BTstack'):
            if self.service(label) is None:
                raise RuntimeError('RESTORED_JOB_NOT_OBSERVED=' + label)
        lines = self.processes()
        if not self.named(lines, 'bluetoothd'):
            raise RuntimeError('RESTORED_BLUETOOTHD_NOT_RUNNING')
        if any(self.named(lines, name) for name in ('CarDisplaySim', 'carplay_bt')):
            raise RuntimeError('UNEXPECTED_HELPER_AFTER_RESTORE')
        self.execute('test -S /tmp/BTstack')
        channel = self.client.get_transport().open_channel('direct-streamlocal@openssh.com', timeout=4)
        try:
            protocol = PowerProtocol(channel, self.emit)
            protocol.command(1)
            if protocol.state(time.monotonic() + 4) != 0:
                raise RuntimeError('RESTORED_BTSTACK_NOT_OFF')
        finally:
            channel.close()
        self.emit('RESTORED_PROCESSES_BEGIN\n' + '\n'.join(lines) + '\nRESTORED_PROCESSES_END')
        self.control('unload', self.state + '/recovery.plist')
        if self.service(LABEL) is not None:
            raise RuntimeError('GUARD_DISARM_FAILED')
        self.execute('rmdir ' + REMOTE_BASE + '/active')
        self.locked = False
        self.emit('RESTORATION_VERIFIED_GUARD_DISARMED')
        return True

    def run(self):
        powered = False
        restored = False
        try:
            self.preflight()
            self.arm()
            self.takeover()
            channel = self.client.get_transport().open_channel('direct-streamlocal@openssh.com', timeout=4)
            try:
                PowerProtocol(channel, self.emit).run()
                powered = True
            finally:
                channel.close()
        except Exception as error:
            self.emit('POWER_TRIAL_FAILED=' + type(error).__name__ + ':' + str(error))
        finally:
            try:
                restored = self.restore()
            except Exception as error:
                self.emit('RESTORE_OBSERVATION_FAILED=' + type(error).__name__ + ':' + str(error))
            self.stop_heartbeat.set()
            if self.heartbeat_thread:
                self.heartbeat_thread.join(timeout=3)
            self.emit('REMOTE_RUN_DIRECTORY=' + self.state)
        self.emit('POWER_TRIAL_PASSED=' + str(int(powered)))
        self.emit('RESTORATION_PASSED=' + str(int(restored)))
        return 0 if powered and restored else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true', help='Perform exactly one guarded power-only device trial')
    args = parser.parse_args()
    if not args.execute:
        parser.error('--execute is required; no device action performed')
    password = getpass.getpass('iPad SSH password: ') if sys.stdin.isatty() else sys.stdin.readline().rstrip('\r\n')
    if not password:
        raise SystemExit('No authentication input')
    directory = ROOT / 'artifacts/device-validation-20261126'
    directory.mkdir(parents=True, exist_ok=True)
    logfile = directory / ('power-trial-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S') + '.log')
    client = paramiko.SSHClient()
    client.load_host_keys(str(pathlib.Path.home() / '.ssh/known_hosts'))
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    try:
        client.connect('127.0.0.1', port=2222, username='root', password=password,
                       allow_agent=False, look_for_keys=False, timeout=15,
                       auth_timeout=30, banner_timeout=15, transport_factory=FixedStreamlocalTransport)
        password = None
        with logfile.open('w', encoding='utf-8') as log:
            result = Trial(client, log).run()
        print('LOG_PATH=' + str(logfile), flush=True)
        return result
    finally:
        password = None
        client.close()


if __name__ == '__main__':
    raise SystemExit(main())
