#!/usr/bin/env python3
"""Install only the reviewed scan demo and fixed PING/PONG helper on iPad5,1.

This utility deliberately has no Trial, power, Bluetooth, pairing, or identity
imports or commands. It validates the pinned local packages before prompting
for SSH authentication. Use --execute explicitly; password input is never
stored, logged, or passed in a command line/environment variable.
"""
import argparse
import getpass
import hashlib
import io
import importlib.util
import pathlib
import secrets
import shlex
import socket
import sys
import tarfile
import time

try:
    import paramiko
except ModuleNotFoundError:
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'tools/python-ssh'))
    import paramiko


# Pinned from successful demo package stages in CI run 45870558171,
# commit 7a4ae95f555447d35519b014d65380c1ce1e203a (artifact 15143686295).
APP_PACKAGE = pathlib.Path(
    r'C:\Users\quesi\AppData\Local\Temp\openhc-run-45870558171\scan-ui') / \
    'com.gcbond.openhc-scan-demo_0.1.0_iphoneos-arm64.deb'
HELPER_PACKAGE = pathlib.Path(
    r'C:\Users\quesi\AppData\Local\Temp\openhc-run-45870558171\scan-supervisor') / \
    'com.gcbond.openhc-scan-ping-helper_0.1.0_iphoneos-arm64.deb'
APP_SHA256 = '6237cce77faa3cc73a1721e5a664c4c7821a8d8cd690830307dbad5f3fb94684'
HELPER_SHA256 = 'e9d8e690eca8920e96908b07a24d7659c33cca80b67cf23d2a5a615a308b40d8'
APP_EXECUTABLE_SHA256 = '7abf8242eb13da7feac880bc4887a1bf4aff2aeb7e72198a583959c85f465345'
HELPER_EXECUTABLE_SHA256 = '34a3c3ca5d85d4e3863ff7631acec6dce8c636423be68b49edfe356810a6fc55'
APP_NAME = 'com.gcbond.openhc-scan-demo'
HELPER_NAME = 'com.gcbond.openhc-scan-ping-helper'
APP_BINARY = '/var/jb/Applications/OpenHCScanDemo.app/OpenHCScanDemo'
HELPER_BINARY = '/var/jb/usr/libexec/openhc-scan-ping-helper'
JOB = 'system/com.gcbond.openhc-scan-ping-helper'
RUNTIME = '/var/jb/var/run/openhc'
SOCKET = RUNTIME + '/scan-ping.sock'
PLIST = '/var/jb/Library/LaunchDaemons/com.gcbond.openhc-scan-ping-helper.plist'
KNOWN_HOSTS = pathlib.Path.home() / '.ssh' / 'known_hosts'


class InstallError(RuntimeError):
    pass


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def validate_archives():
    checker_path = pathlib.Path(__file__).with_name('check-scan-demo-archive.py')
    spec = importlib.util.spec_from_file_location('scan_demo_archive_checker', checker_path)
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    for path, expected, package in (
            (APP_PACKAGE, APP_SHA256, APP_NAME),
            (HELPER_PACKAGE, HELPER_SHA256, HELPER_NAME)):
        if not path.is_file() or sha256_file(path) != expected:
            raise InstallError('PINNED_LOCAL_PACKAGE_MISMATCH')
        if checker.check(path.read_bytes(), require_xz=True) != package:
            raise InstallError('LOCAL_ARCHIVE_POLICY_MISMATCH')
    # The exact executable hashes are also pinned independently of the DEB hash.
    for path, member_name, expected in (
            (APP_PACKAGE, checker.APP + '/OpenHCScanDemo', APP_EXECUTABLE_SHA256),
            (HELPER_PACKAGE, checker.HELPER, HELPER_EXECUTABLE_SHA256)):
        _, data_archive = checker.read_deb(path.read_bytes())
        with tarfile.open(fileobj=io.BytesIO(data_archive), mode='r:*') as archive:
            member = archive.extractfile('./' + member_name)
            if member is None or hashlib.sha256(member.read()).hexdigest() != expected:
                raise InstallError('PINNED_EXECUTABLE_MISMATCH')
            binary = archive.extractfile('./' + member_name).read()
            if (SOCKET.encode('ascii') + b'\x00') not in binary:
                raise InstallError('PINNED_SHORT_SOCKET_PATH_MISSING')


class BoundedSSH:
    def __init__(self, client):
        self.client = client

    def run(self, command, timeout=8, output_limit=4096):
        # Every call site supplies a fixed command or a shell-quoted private path.
        command = ('PATH=/var/jb/usr/bin:/var/jb/bin:/var/jb/usr/sbin:/var/jb/sbin:/usr/bin:/bin:/usr/sbin:/sbin; export PATH; ' + command)
        _, stdout, stderr = self.client.exec_command(command, timeout=timeout, get_pty=False)
        channel = stdout.channel
        deadline = time.monotonic() + timeout
        out = bytearray()
        err = bytearray()
        while time.monotonic() < deadline:
            while channel.recv_ready() and len(out) <= output_limit:
                out.extend(channel.recv(max(1, min(1024, output_limit + 1 - len(out)))))
            while channel.recv_stderr_ready() and len(err) <= output_limit:
                err.extend(channel.recv_stderr(max(1, min(1024, output_limit + 1 - len(err)))))
            if len(out) > output_limit or len(err) > output_limit:
                channel.close()
                raise InstallError('REMOTE_OUTPUT_LIMIT')
            if channel.exit_status_ready() and not channel.recv_ready() and not channel.recv_stderr_ready():
                status = channel.recv_exit_status()
                return status, out.decode('utf-8', 'replace').strip(), err.decode('utf-8', 'replace').strip()
            time.sleep(0.05)
        channel.close()
        raise InstallError('REMOTE_COMMAND_TIMEOUT')

    def require(self, command, label, timeout=8):
        status, output, _ = self.run(command, timeout=timeout)
        if status != 0:
            raise InstallError(label)
        return output


def quote(path):
    return shlex.quote(str(path))


def connect(password):
    if not KNOWN_HOSTS.is_file():
        raise InstallError('KNOWN_HOSTS_MISSING')
    client = paramiko.SSHClient()
    client.load_host_keys(str(KNOWN_HOSTS))
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    client.connect('127.0.0.1', port=2222, username='root', password=password,
                   allow_agent=False, look_for_keys=False, timeout=8,
                   auth_timeout=12, banner_timeout=8)
    return client


def verify_target(ssh):
    # Read-only platform and privilege gate; no other device properties are read.
    if ssh.require('sysctl -n hw.machine', 'TARGET_MODEL_CHECK_FAILED') != 'iPad5,1':
        raise InstallError('WRONG_DEVICE_MODEL')
    if ssh.require('uname -s', 'OS_CHECK_FAILED') != 'Darwin':
        raise InstallError('WRONG_DEVICE_OS')
    if ssh.require('id -u', 'ROOT_CHECK_FAILED') != '0':
        raise InstallError('ROOT_REQUIRED')
    # /var/jb may be a bootstrap-managed symlink; only require the alias to resolve.
    ssh.require('test -d /var/jb', 'ROOTLESS_PREFIX_CHECK_FAILED')


def device_install(ssh, start_helper=False, app_only=False):
    if app_only and start_helper:
        raise InstallError('APP_ONLY_MUST_NOT_START_HELPER')
    app_version = ssh.run("/var/jb/usr/bin/dpkg-query -W -f='${Version}' " + APP_NAME, timeout=6)[1]
    helper_version = ssh.run("/var/jb/usr/bin/dpkg-query -W -f='${Version}' " + HELPER_NAME, timeout=6)[1]
    def matches(version, path, expected):
        if version != '0.1.0':
            return False
        status, output, _ = ssh.run('/var/jb/usr/bin/sha256sum ' + quote(path), timeout=6)
        return status == 0 and output.split()[:1] == [expected]

    app_current = matches(app_version, APP_BINARY, APP_EXECUTABLE_SHA256)
    helper_current = matches(helper_version, HELPER_BINARY, HELPER_EXECUTABLE_SHA256)
    if app_only and not helper_current:
        raise InstallError('APP_ONLY_REQUIRES_PINNED_INSTALLED_HELPER')
    pending = []
    if not app_current:
        pending.append((APP_PACKAGE, APP_SHA256, 'app.deb'))
    if not helper_current and not app_only:
        pending.append((HELPER_PACKAGE, HELPER_SHA256, 'helper.deb'))
    uploaded_dir = None
    try:
        if pending:
            token = secrets.token_hex(12)
            uploaded_dir = '/var/tmp/openhc-scan-demo-' + token
            ssh.require('umask 077; mkdir -m 700 ' + quote(uploaded_dir), 'PRIVATE_UPLOAD_DIR_FAILED')
            sftp = ssh.client.open_sftp()
            try:
                for local, _, name in pending:
                    sftp.put(str(local), uploaded_dir + '/' + name)
            finally:
                sftp.close()
            for _, expected, name in pending:
                remote = uploaded_dir + '/' + name
                actual = ssh.require('/var/jb/usr/bin/sha256sum ' + quote(remote),
                                     'REMOTE_PACKAGE_HASH_FAILED')
                if actual.split()[0].lower() != expected:
                    raise InstallError('REMOTE_PACKAGE_HASH_MISMATCH')
            ssh.require('/var/jb/usr/bin/dpkg -i ' + ' '.join(quote(uploaded_dir + '/' + name) for _, _, name in pending),
                        'DEMO_PACKAGE_INSTALL_FAILED', timeout=30)

        if ssh.require("/var/jb/usr/bin/dpkg-query -W -f='${Version}' " + APP_NAME,
                       'APP_PACKAGE_VERSION_FAILED') != '0.1.0':
            raise InstallError('APP_PACKAGE_VERSION_MISMATCH')
        if ssh.require("/var/jb/usr/bin/dpkg-query -W -f='${Version}' " + HELPER_NAME,
                       'HELPER_PACKAGE_VERSION_FAILED') != '0.1.0':
            raise InstallError('HELPER_PACKAGE_VERSION_MISMATCH')
        for path, expected, label in (
                (APP_BINARY, APP_EXECUTABLE_SHA256, 'APP_EXECUTABLE_HASH_MISMATCH'),
                (HELPER_BINARY, HELPER_EXECUTABLE_SHA256, 'HELPER_EXECUTABLE_HASH_MISMATCH')):
            actual = ssh.require('/var/jb/usr/bin/sha256sum ' + quote(path), label)
            if actual.split()[0].lower() != expected:
                raise InstallError(label)

        # Runtime directory must remain root-owned and not group/world writable.
        directory_stat = ssh.require('/var/jb/usr/bin/stat -c %u:%g:%a ' + quote(RUNTIME), 'RUNTIME_STAT_FAILED')
        if directory_stat != '0:0:755':
            raise InstallError('RUNTIME_DIRECTORY_POLICY_MISMATCH')

        status, _, _ = ssh.run('/var/jb/usr/bin/launchctl print ' + JOB, timeout=8)
        if status != 0 and start_helper:
            ssh.require('/var/jb/usr/bin/launchctl bootstrap system ' + quote(PLIST),
                        'FIXED_HELPER_BOOTSTRAP_FAILED', timeout=12)
            status = 0
        if status != 0:
            # Installation must not launch or reload the helper implicitly.
            print('HELPER_JOB_REMAINS_UNLOADED')
            return False

        # RunAtLoad creates the socket; bounded observations only, no kickstart/restart.
        deadline = time.monotonic() + 4
        socket_stat = None
        while time.monotonic() < deadline:
            status, output, _ = ssh.run('/var/jb/usr/bin/stat -c %U:%G:%a ' + quote(SOCKET), timeout=3)
            if status == 0:
                socket_stat = output
                break
            time.sleep(0.2)
        if socket_stat != 'root:mobile:660':
            if socket_stat is not None and len(socket_stat) < 100 and all(c.isalnum() or c in ':_-' for c in socket_stat):
                print('HELPER_SOCKET_OBSERVED=' + socket_stat)
            else:
                print('HELPER_SOCKET_OBSERVED=UNAVAILABLE')
            raise InstallError('HELPER_SOCKET_POLICY_MISMATCH')
        return True
    finally:
        if uploaded_dir:
            # Remove only the uniquely created private directory and its two files.
            cleanup = ('rm -f -- ' + quote(uploaded_dir + '/app.deb') + ' ' +
                       quote(uploaded_dir + '/helper.deb') + ' && rmdir -- ' + quote(uploaded_dir))
            status, _, _ = ssh.run(cleanup, timeout=5, output_limit=512)
            if status != 0:
                raise InstallError('REMOTE_TEMP_CLEANUP_FAILED')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true', help='perform the narrowly scoped installation')
    parser.add_argument('--app-only', action='store_true', help='update App only; require pinned installed helper and never start it')
    action = parser.add_mutually_exclusive_group()
    action.add_argument('--diagnose', action='store_true', help='read fixed helper status only')
    action.add_argument('--stop-helper', action='store_true', help='unload only the failing demo helper')
    action.add_argument('--start-helper', action='store_true', help='after package verification bootstrap only the fixed helper')
    args = parser.parse_args()
    if args.app_only and (args.start_helper or args.stop_helper or args.diagnose):
        parser.error('--app-only cannot change helper lifecycle or diagnose')
    if not args.execute:
        parser.error('pass --execute to enable the fixed install flow')
    validate_archives()
    # On a terminal getpass disables echo; on a pipe read one line from stdin.
    password = getpass.getpass('Authorized iPad SSH password: ') if sys.stdin.isatty() else sys.stdin.readline().rstrip('\r\n')
    if not password:
        raise SystemExit('AUTH_INPUT_REQUIRED')
    client = None
    try:
        client = connect(password)
        password = None
        ssh = BoundedSSH(client)
        # This gate must precede even diagnose/bootout branches.
        verify_target(ssh)
        if args.stop_helper:
            status, _, _ = ssh.run('/var/jb/usr/bin/launchctl print ' + JOB, timeout=8)
            if status == 0:
                ssh.require('/var/jb/usr/bin/launchctl bootout ' + JOB,
                            'FIXED_HELPER_BOOTOUT_FAILED')
                print('FAILING_DEMO_HELPER_UNLOADED')
            else:
                print('FAILING_DEMO_HELPER_ALREADY_UNLOADED')
            return 0
        if args.diagnose:
            for label, command in (
                    ('JOB', '/var/jb/usr/bin/launchctl print ' + JOB),
                    ('SOCKET_STAT', '/var/jb/usr/bin/stat -c %F:%u:%g:%a ' + quote(SOCKET)),
                    ('RUNTIME_STAT', '/var/jb/usr/bin/stat -c %F:%u:%g:%a ' + quote(RUNTIME)),
                    ):
                status, output, _ = ssh.run(command, output_limit=12000)
                print(label + '_EXIT=' + str(status))
                if label == 'JOB':
                    for line in output.splitlines():
                        line = line.strip()
                        if line.startswith(('state =', 'pid =', 'runs =', 'last exit code =', 'last terminating signal =')):
                            print('HELPER_' + line)
                else:
                    print(label + '=' + output[:200])
            return 0
        helper_loaded = device_install(ssh, start_helper=args.start_helper, app_only=args.app_only)
        print('DEVICE_READONLY_GATES_OK')
        print('DEMO_PACKAGES_INSTALLED_OR_MATCHED version=0.1.0')
        if helper_loaded:
            print('HELPER_JOB_AND_SOCKET_POLICY_OK')
        else:
            print('HELPER_JOB_NOT_STARTED_BY_INSTALLER')
        if helper_loaded:
            print('APP=OpenHCScanDemo NEXT=Tap existing Start action and verify fixed helper PONG')
        else:
            print('APP=OpenHCScanDemo NEXT=Coordinator must explicitly bootstrap the fixed verified helper before UIKit Start')
    except InstallError as error:
        print('INSTALL_CHECK_FAILED=' + str(error), file=sys.stderr)
        return 2
    except (OSError, paramiko.SSHException, socket.timeout):
        print('INSTALL_CHECK_FAILED=SSH_OR_LOCAL_IO', file=sys.stderr)
        return 2
    finally:
        password = None
        if client is not None:
            client.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
