"""Build the bounded FE35 bridge input from an existing OpenHC identity asset."""
import base64
import ctypes
import hashlib
import json
import os
import re
import select
import time

MAX_IDENTITY_BYTES = 64 * 1024
MAX_KEY_BYTES = 64
MIN_KEY_BYTES = 5
MAX_BRIDGE_BYTES = 327


class ConfigError(ValueError):
    pass


def wait_readable(fd, timeout):
    if os.name != 'nt':
        return bool(select.select([fd], [], [], timeout)[0])
    import msvcrt
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    wait = kernel.WaitForSingleObject
    wait.argtypes = (ctypes.c_void_p, ctypes.c_uint32)
    wait.restype = ctypes.c_uint32
    handle = msvcrt.get_osfhandle(fd)
    return wait(handle, max(0, int(timeout * 1000))) == 0


def _object(value):
    if not isinstance(value, dict):
        raise ConfigError('IDENTITY_CONFIG_INVALID')
    return value


def _string(obj, key):
    value = obj.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError('IDENTITY_CONFIG_INVALID')
    return value


def _bt_address(fd):
    result = bytearray()
    deadline = time.monotonic() + 3
    try:
        while len(result) <= 32:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not wait_readable(fd, remaining):
                raise ConfigError('BLUETOOTH_ADDRESS_FD_TIMEOUT')
            chunk = os.read(fd, 33 - len(result))
            if not chunk:
                break
            result.extend(chunk)
    finally:
        try:
            os.close(fd)
        except OSError:
            pass

    try:
        text = result.decode('ascii').strip()
    except UnicodeDecodeError:
        raise ConfigError('BLUETOOTH_ADDRESS_INVALID') from None
    finally:
        result[:] = bytes(len(result))

    if len(text) == 12 and re.fullmatch(r'[0-9A-Fa-f]{12}', text):
        text = ':'.join(text[i:i + 2] for i in range(0, 12, 2))
    if not re.fullmatch(r'(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}', text):
        raise ConfigError('BLUETOOTH_ADDRESS_INVALID')
    address = bytes.fromhex(text.replace(':', ''))
    if address in (bytes(6), bytes([0xff]) * 6, bytes.fromhex('020000000000')):
        raise ConfigError('BLUETOOTH_ADDRESS_UNAVAILABLE')
    return address


def _key_material(keys, name):
    text = _string(keys, name)
    try:
        value = base64.b64decode(text.encode('ascii'), validate=True)
    except (UnicodeEncodeError, ValueError):
        raise ConfigError('IDENTITY_CONFIG_INVALID') from None
    if not MIN_KEY_BYTES <= len(value) <= MAX_KEY_BYTES:
        raise ConfigError('IDENTITY_CONFIG_INVALID')
    return value


def build_bridge_config(identity_json, bluetooth_address):
    try:
        if not isinstance(bluetooth_address, bytes) or len(bluetooth_address) != 6:
            raise ConfigError('BLUETOOTH_ADDRESS_INVALID')
        if bluetooth_address in (bytes(6), bytes([0xff]) * 6, bytes.fromhex('020000000000')):
            raise ConfigError('BLUETOOTH_ADDRESS_UNAVAILABLE')
        root = _object(json.loads(identity_json))
        if type(root.get('format')) is not int or root['format'] != 1:
            raise ConfigError('IDENTITY_CONFIG_INVALID')
        host = _object(root.get('host'))
        model_id = _string(host, 'modelId').upper()
        sub_model_id = _string(host, 'subModelId').upper()
        if not re.fullmatch(r'[0-9A-F]{6}', model_id) or not re.fullmatch(r'[0-9A-F]{2}', sub_model_id):
            raise ConfigError('IDENTITY_CONFIG_INVALID')
        _string(host, 'brand')
        _string(host, 'deviceName')
        auth = _object(root.get('authService'))
        _string(auth, 'packageName')
        _string(auth, 'serviceType')
        _string(auth, 'envelopeVersion')
        keys = _object(root.get('nearbyKeys'))
        material = [_key_material(keys, name) for name in ('rootKey', 'constA', 'constB')]
        if len({len(value) for value in material}) != 1:
            raise ConfigError('IDENTITY_CONFIG_INVALID')
        identity_bytes = bytes.fromhex(model_id + sub_model_id) + bluetooth_address
        device_id = hashlib.sha256(identity_bytes.hex().upper().encode('ascii')).hexdigest().upper().encode('ascii')
        encoded = bytearray((1, len(device_id)))
        encoded.extend(device_id)
        for value in material:
            encoded.append(len(value))
            encoded.extend(value)
        if len(encoded) > MAX_BRIDGE_BYTES:
            encoded[:] = bytes(len(encoded))
            raise ConfigError('IDENTITY_CONFIG_INVALID')
        return encoded
    except ConfigError:
        raise
    except Exception:
        # JSON parser diagnostics can contain source text; expose only a stable code.
        raise ConfigError('IDENTITY_CONFIG_INVALID') from None


def _read_pipe(fd):
    result = bytearray()
    try:
        while len(result) <= MAX_BRIDGE_BYTES:
            chunk = os.read(fd, MAX_BRIDGE_BYTES + 1 - len(result))
            if not chunk:
                break
            result.extend(chunk)
    finally:
        os.close(fd)
    if not 1 <= len(result) <= MAX_BRIDGE_BYTES:
        result[:] = bytes(len(result))
        raise ConfigError('IDENTITY_CONFIG_INVALID')
    return result


def load_bridge_config(identity_path, bluetooth_address_fd):
    """Read existing identity schema, then relay its FE35 subset through a pipe."""
    bridge = bytearray()
    try:
        with open(identity_path, 'rb') as source:
            raw = source.read(MAX_IDENTITY_BYTES + 1)
        if not raw or len(raw) > MAX_IDENTITY_BYTES:
            raise ConfigError('IDENTITY_CONFIG_INVALID')
        try:
            identity_json = raw.decode('utf-8-sig')
        except UnicodeDecodeError:
            raise ConfigError('IDENTITY_CONFIG_INVALID') from None
        address = _bt_address(bluetooth_address_fd)
        bridge = build_bridge_config(identity_json, address)
        read_fd, write_fd = os.pipe()
        try:
            offset = 0
            while offset < len(bridge):
                offset += os.write(write_fd, bridge[offset:])
            os.close(write_fd)
            write_fd = -1
            relayed = _read_pipe(read_fd)
            read_fd = -1
            return relayed
        finally:
            if write_fd >= 0:
                os.close(write_fd)
            if read_fd >= 0:
                os.close(read_fd)
    except ConfigError:
        raise
    except OSError:
        raise ConfigError('IDENTITY_CONFIG_UNAVAILABLE') from None
    finally:
        bridge[:] = bytes(len(bridge))
        if 'raw' in locals():
            raw = bytes(len(raw))
        if 'identity_json' in locals():
            identity_json = ''
        try:
            os.close(bluetooth_address_fd)
        except OSError:
            pass
