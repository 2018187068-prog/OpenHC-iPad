"""One guarded power trial over existing USB SSH; no peer operations.

Inbound mode accepts either a bounded bridge config FD or an existing OpenHC
identity file. In the WORKING callback it reads local BD_ADDR through BTstack
HCI Read BD_ADDR, then builds the bounded bridge config. Password input is read
from stdin, never stored in artifacts.
The independent device guard owns restoration, including on host/SSH failure.
"""
import argparse
import datetime
import getpass
import importlib.util
import json
import os
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
_gate_spec = importlib.util.spec_from_file_location(
    'btstack_session_gate', ROOT / 'scripts/btstack-session-gate.py')
session_gate = importlib.util.module_from_spec(_gate_spec)
_gate_spec.loader.exec_module(session_gate)
_config_spec = importlib.util.spec_from_file_location(
    'fe35_bridge_config', ROOT / 'scripts/fe35-bridge-config.py')
fe35_config = importlib.util.module_from_spec(_config_spec)
_config_spec.loader.exec_module(fe35_config)
REMOTE_BASE = '/var/root/Library/OpenHCStage0Power'
LABEL = 'io.github.gcbond.openhc.stage0-power-recovery'
INBOUND_RUN_SECONDS = 45
GUARD_BUDGET_SECONDS = 240
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

    def run(self, on_working=None):
        """Run one guarded lease; on_working runs inside its WORKING window.

        The callback must be bounded and must not own/refresh the recovery
        guard. This protocol remains the sole owner of power release.
        """
        self.command(1)
        if self.state(time.monotonic() + 4) != 0:
            raise RuntimeError('INITIAL_STATE_NOT_OFF')
        requested = False
        lease_uncertain = False
        try:
            requested = True
            self.command(2, 1)
            self.wait_state(2, 25)
            self.emit('BTSTACK_POWER_WORKING')
            if on_working is not None:
                on_working()
        except LeaseUncertain:
            lease_uncertain = True
            raise
        finally:
            if requested and not lease_uncertain:
                self.command(2, 0)
                self.wait_state(0, 15)
                self.emit('BTSTACK_POWER_OFF_OBSERVED')


class LeaseUncertain(RuntimeError):
    """Remote transport may still run; only the independent guard may recover."""


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
        self.heartbeat_failed = threading.Event()
        self.guard_owns_recovery = False
        self.session_evidence = None

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
            self.heartbeat_failed.set()
            self.emit('HEARTBEAT_CHANNEL_FAILED_GUARD_WILL_RESTORE')

    def read_local_bluetooth_address(self):
        if self.heartbeat_failed.is_set():
            raise LeaseUncertain('HEARTBEAT_FAILED_BEFORE_ADDRESS_QUERY')
        command = shlex.join([TIMER, '-k', '2', '6',
                              '/var/jb/usr/bin/openhc-bridge-check',
                              '--btstack-local-address', self.state])
        channel = None
        data = bytearray()
        deadline = time.monotonic() + 8
        try:
            channel = self.client.get_transport().open_session(timeout=4)
            channel.settimeout(.5)
            channel.exec_command(command)
            while not channel.exit_status_ready():
                if channel.recv_ready():
                    data.extend(channel.recv(7 - len(data)))
                    if len(data) > 6:
                        raise RuntimeError('LOCAL_ADDRESS_RESPONSE_INVALID')
                if time.monotonic() >= deadline:
                    raise RuntimeError('LOCAL_ADDRESS_QUERY_TIMEOUT')
                time.sleep(.02)
            while channel.recv_ready():
                data.extend(channel.recv(7 - len(data)))
            status = channel.recv_exit_status()
            if status or len(data) != 6:
                raise RuntimeError('LOCAL_ADDRESS_QUERY_FAILED')
            if self.heartbeat_failed.is_set():
                raise LeaseUncertain('HEARTBEAT_FAILED_AFTER_ADDRESS_QUERY')
            return bytearray(data)
        except (LeaseUncertain, RuntimeError):
            raise
        except BaseException as error:
            if isinstance(error, (KeyboardInterrupt, SystemExit)):
                raise
            raise RuntimeError('LOCAL_ADDRESS_QUERY_FAILED') from None
        finally:
            for index in range(len(data)):
                data[index] = 0
            if channel is not None:
                try:
                    channel.close()
                except Exception:
                    pass

    def run_inbound_transport(self, bridge_config):
        """Run only the fixed rootless inbound adapter in its own SSH channel."""
        if self.heartbeat_failed.is_set():
            raise LeaseUncertain('HEARTBEAT_FAILED_BEFORE_TRANSPORT')
        if not isinstance(bridge_config, bytearray) or not 1 <= len(bridge_config) <= 327:
            raise RuntimeError('BOUNDED_BRIDGE_INPUT_REQUIRED')
        command = shlex.join([TIMER, '-k', '2', str(INBOUND_RUN_SECONDS),
                              '/var/jb/usr/bin/openhc-bridge-check',
                              '--btstack-control-inbound', self.state])
        channel = None
        output = bytearray()
        deadline = time.monotonic() + INBOUND_RUN_SECONDS + 5
        try:
            channel = self.client.get_transport().open_session(timeout=4)
            channel.settimeout(1)
            channel.set_combine_stderr(True)
            channel.exec_command(command)
            channel.sendall(bridge_config)
            channel.shutdown_write()
            bridge_config[:] = bytes(len(bridge_config))
            while True:
                if channel.recv_ready():
                    chunk = channel.recv(min(4096, 65537 - len(output)))
                    output.extend(chunk)
                    if len(output) > 65536:
                        raise LeaseUncertain('INBOUND_OUTPUT_LIMIT_REMOTE_EXIT_UNKNOWN')
                if channel.exit_status_ready():
                    while channel.recv_ready():
                        chunk = channel.recv(min(4096, 65537 - len(output)))
                        output.extend(chunk)
                        if len(output) > 65536:
                            raise RuntimeError('INBOUND_OUTPUT_LIMIT')
                    status = channel.recv_exit_status()
                    text = output.decode('utf-8', errors='replace').strip()
                    if text:
                        self.emit('INBOUND_TRANSPORT_OUTPUT_BEGIN\n' + text + '\nINBOUND_TRANSPORT_OUTPUT_END')
                    self.emit('TRANSPORT_EXIT_CONFIRMED=' + str(status))
                    if self.heartbeat_failed.is_set():
                        raise LeaseUncertain('HEARTBEAT_FAILED_GUARD_STATE_UNCERTAIN')
                    if status != 0:
                        raise RuntimeError('INBOUND_TRANSPORT_EXIT=' + str(status))
                    return
                if time.monotonic() >= deadline:
                    raise LeaseUncertain('INBOUND_REMOTE_EXIT_UNCONFIRMED_TIMEOUT')
                time.sleep(.05)
        except LeaseUncertain:
            raise
        except BaseException as error:
            raise LeaseUncertain('INBOUND_REMOTE_EXIT_UNCONFIRMED_' + type(error).__name__) from error
        finally:
            if channel is not None:
                try:
                    channel.close()
                except Exception:
                    pass

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
        shared = []
        for line in lines:
            fields = line.split(None, 3)
            if len(fields) == 4 and any(fields[3].rstrip().rsplit('/', 1)[-1] == name
                    for name in ('CarPlay Simulator', 'CarPlay Simulato', 'carplay_services')):
                try:
                    shared.append(int(fields[0]))
                except ValueError:
                    raise RuntimeError('SESSION_METADATA_UNKNOWN=INVALID_PROCESS_PID')
        if shared:
            evidence = self.session_evidence
            if not isinstance(evidence, dict):
                raise RuntimeError('SESSION_METADATA_UNKNOWN=FRESH_EVIDENCE_REQUIRED')
            try:
                captured = evidence['captured_at_epoch']
                if isinstance(captured, bool) or not isinstance(captured, (int, float)) or abs(time.time() - captured) > 60:
                    raise ValueError('STALE')
                if evidence['snapshot_complete'] is not True:
                    raise ValueError('INCOMPLETE_SNAPSHOT')
                if type(evidence['recovery_active']) is not bool:
                    raise ValueError('INVALID_RECOVERY_STATE')
                if evidence['ownership_marker'] not in (True, False, None):
                    raise ValueError('INVALID_OWNERSHIP_MARKER')
                for key in ('shared_helper_pids', 'active_session_pids'):
                    values = evidence.get(key, [])
                    if not isinstance(values, list) or any(type(pid) is not int or pid < 1 for pid in values):
                        raise ValueError('INVALID_' + key.upper())
                for key in ('broker_owner_pid', 'broker_comm_pid'):
                    value = evidence.get(key)
                    if value is not None and (type(value) is not int or value < 1):
                        raise ValueError('INVALID_' + key.upper())
                if sorted(set(evidence['shared_helper_pids'])) != sorted(set(shared)):
                    raise ValueError('PROCESS_SET_MISMATCH')
                verdict = session_gate.classify(
                    snapshot_complete=evidence['snapshot_complete'],
                    broker_owner_pid=evidence.get('broker_owner_pid'),
                    broker_comm_pid=evidence.get('broker_comm_pid'),
                    shared_helper_pids=tuple(shared),
                    active_session_pids=tuple(evidence.get('active_session_pids', ())),
                    recovery_active=evidence['recovery_active'],
                    ownership_marker=evidence['ownership_marker'])
            except (KeyError, TypeError, ValueError) as error:
                raise RuntimeError('SESSION_METADATA_UNKNOWN=' + str(error)) from error
            if verdict != 'BROKER':
                raise RuntimeError('SESSION_METADATA_BLOCKED=' + verdict)
            self.emit('SESSION_METADATA_CLASSIFICATION=BROKER')
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
        self.execute('now=$(' + DATE + ' +%s); echo "$now" > ' + self.state + '/heartbeat; echo $((now + ' + str(GUARD_BUDGET_SECONDS) + ')) > ' + self.state + '/deadline')
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

    def run(self, mode='power-only', session_evidence=None, bridge_config=None,
            identity_file=None):
        if mode not in ('power-only', 'inbound'):
            raise ValueError('INVALID_MODE')
        if mode == 'inbound' and bridge_config is None and identity_file is None:
            raise ValueError('IDENTITY_CONFIG_REQUIRED')
        if mode == 'inbound' and bridge_config is not None and (
                not isinstance(bridge_config, bytearray) or not 1 <= len(bridge_config) <= 327):
            raise ValueError('BOUNDED_BRIDGE_INPUT_REQUIRED')
        self.session_evidence = session_evidence
        powered = False
        restored = False
        transport = 'NOT_RUN'
        try:
            self.preflight()
            self.arm()
            self.takeover()
            channel = self.client.get_transport().open_channel('direct-streamlocal@openssh.com', timeout=4)
            try:
                if mode == 'inbound' and bridge_config is None:
                    def callback():
                        address = self.read_local_bluetooth_address()
                        address_read, address_write = os.pipe()
                        try:
                            encoded_address = ':'.join('%02X' % b for b in address).encode('ascii')
                            offset = 0
                            while offset < len(encoded_address):
                                offset += os.write(address_write, encoded_address[offset:])
                            os.close(address_write)
                            address_write = -1
                            config = fe35_config.load_bridge_config(identity_file, address_read)
                            address_read = -1
                            try:
                                self.run_inbound_transport(config)
                            finally:
                                config[:] = bytes(len(config))
                        finally:
                            for index in range(len(address)):
                                address[index] = 0
                            encoded_address = b''
                            if address_write >= 0: os.close(address_write)
                            if address_read >= 0: os.close(address_read)
                else:
                    callback = (lambda: self.run_inbound_transport(bridge_config)) if mode == 'inbound' else None
                try:
                    PowerProtocol(channel, self.emit).run(on_working=callback)
                    transport = 'PASSED' if mode == 'inbound' else 'NOT_APPLICABLE'
                except LeaseUncertain:
                    self.guard_owns_recovery = True
                    transport = 'EXIT_UNCONFIRMED'
                    raise
                except Exception:
                    transport = 'FAILED'
                    raise
                powered = True
            finally:
                channel.close()
        except Exception as error:
            self.emit('POWER_TRIAL_FAILED=' + type(error).__name__ + ':' + str(error))
        finally:
            if isinstance(bridge_config, bytearray):
                bridge_config[:] = bytes(len(bridge_config))
            self.stop_heartbeat.set()
            if self.heartbeat_thread:
                self.heartbeat_thread.join(timeout=3)
            if self.guard_owns_recovery:
                self.emit('RESTORATION_DELEGATED_TO_GUARD=1')
            else:
                try:
                    restored = self.restore()
                except Exception as error:
                    self.emit('RESTORE_OBSERVATION_FAILED=' + type(error).__name__ + ':' + str(error))
            self.emit('REMOTE_RUN_DIRECTORY=' + self.state)
        self.emit('TRANSPORT_RESULT=' + transport)
        self.emit('POWER_TRIAL_PASSED=' + str(int(powered)))
        self.emit('RESTORATION_PASSED=' + str(int(restored)))
        restoration = 'DELEGATED_TO_GUARD' if self.guard_owns_recovery else ('VERIFIED' if restored else 'NOT_VERIFIED')
        self.emit('RESTORATION_RESULT=' + restoration)
        return 0 if powered and restored else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true', help='Perform exactly one guarded device trial')
    parser.add_argument('--mode', choices=('power-only', 'inbound'), default='power-only')
    parser.add_argument('--bridge-config-fd', type=int,
                        help='Read the already encoded bounded bridge input from an inherited file descriptor')
    parser.add_argument('--identity-file', type=pathlib.Path,
                        help='Read the existing openhc-identity.json schema; otherwise OPENHC_IDENTITY_DIR is used')
    parser.add_argument('--session-evidence', type=pathlib.Path,
                        help='Fresh JSON metadata snapshot required when shared helpers are present')
    args = parser.parse_args(argv)
    if not args.execute:
        print('NO_DEVICE_ACTION: pass --execute explicitly')
        return 2
    bridge_config = None
    if args.mode == 'inbound':
        if args.bridge_config_fd is not None:
            if args.bridge_config_fd <= 2:
                parser.error('--bridge-config-fd must be an inherited FD greater than 2')
            if args.identity_file is not None:
                parser.error('choose one inbound config source')
            try:
                bridge_config = _read_bounded_input_fd(args.bridge_config_fd, 327, 'BRIDGE_CONFIG')
            except ValueError as error:
                parser.error(str(error))
        else:
            identity_file = args.identity_file
            if identity_file is None:
                identity_dir = os.environ.get('OPENHC_IDENTITY_DIR')
                identity_file = pathlib.Path(identity_dir) / 'openhc-identity.json' if identity_dir else None
            if identity_file is None:
                parser.error('IDENTITY_CONFIG_UNAVAILABLE')
            try:
                if not identity_file.is_file():
                    parser.error('IDENTITY_CONFIG_UNAVAILABLE')
            except fe35_config.ConfigError as error:
                parser.error(str(error))
    try:
        return _run_trial(args, bridge_config, identity_file if args.mode == 'inbound' and args.bridge_config_fd is None else None)
    finally:
        if isinstance(bridge_config, bytearray):
            bridge_config[:] = bytes(len(bridge_config))


def _run_trial(args, bridge_config, identity_file=None):
    evidence = None
    if args.session_evidence:
        evidence = json.loads(args.session_evidence.read_text(encoding='utf-8'))
        captured = evidence.get('captured_at_epoch')
        if not isinstance(captured, (int, float)) or abs(time.time() - captured) > 60:
            parser.error('--session-evidence must be a complete metadata snapshot captured within 60 seconds')
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
            result = Trial(client, log).run(mode=args.mode, session_evidence=evidence,
                                           bridge_config=bridge_config, identity_file=identity_file)
        print('LOG_PATH=' + str(logfile), flush=True)
        return result
    finally:
        password = None
        client.close()


def _read_bounded_input_fd(fd, maximum, error_prefix):
    result = bytearray()
    try:
        deadline = time.monotonic() + 3
        while len(result) <= maximum:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not fe35_config.wait_readable(fd, remaining):
                raise ValueError(error_prefix + '_FD_TIMEOUT')
            chunk = os.read(fd, maximum + 1 - len(result))
            if not chunk:
                break
            result.extend(chunk)
        if not 1 <= len(result) <= maximum:
            raise ValueError(error_prefix + '_SIZE_INVALID')
        return result
    except OSError:
        result[:] = bytes(len(result))
        raise ValueError(error_prefix + '_FD_INVALID') from None
    except ValueError:
        result[:] = bytes(len(result))
        raise
    finally:
        try:
            os.close(fd)
        except OSError:
            pass


if __name__ == '__main__':
    raise SystemExit(main())
