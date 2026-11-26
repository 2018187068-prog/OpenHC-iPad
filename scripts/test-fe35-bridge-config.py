"""Synthetic-only tests for the local FE35 configuration provider."""
import base64
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('fe35_bridge_config', ROOT / 'scripts/fe35-bridge-config.py')
provider = importlib.util.module_from_spec(spec)
spec.loader.exec_module(provider)
trial_spec = importlib.util.spec_from_file_location('btstack_power_trial', ROOT / 'scripts/btstack-power-trial.py')
trial = importlib.util.module_from_spec(trial_spec)
trial_spec.loader.exec_module(trial)

ROOT_KEY = bytes(range(8))
CONST_A = bytes(range(8, 16))
CONST_B = bytes(range(16, 24))
ADDRESS_TEXT = b'12:34:56:78:9A:BC'
SENSITIVE_MARKERS = ('synthetic-private-root', 'synthetic-private-a', 'synthetic-private-b')


def identity_json():
    return json.dumps({
        'format': 1,
        'host': {'modelId': 'abcdef', 'subModelId': '01', 'brand': 'Fixture', 'deviceName': 'Fixture Host'},
        'nearbyKeys': {
            'rootKey': base64.b64encode(ROOT_KEY).decode('ascii'),
            'constA': base64.b64encode(CONST_A).decode('ascii'),
            'constB': base64.b64encode(CONST_B).decode('ascii'),
        },
        'authService': {'packageName': 'example.synthetic', 'serviceType': 'SYNTHETIC',
                        'envelopeVersion': 'SYNTHETIC'},
    })


def address_pipe(value=ADDRESS_TEXT):
    read_fd, write_fd = os.pipe()
    os.write(write_fd, value)
    os.close(write_fd)
    return read_fd


def expected_id():
    source = bytes.fromhex('ABCDEF01') + bytes.fromhex('123456789ABC')
    return hashlib.sha256(source.hex().upper().encode('ascii')).hexdigest().upper().encode('ascii')


class ProviderTests(unittest.TestCase):
    def test_identity_schema_maps_to_c_input_through_pipe(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp, 'openhc-identity.json')
            path.write_text(identity_json(), encoding='utf-8')
            fd = address_pipe()
            encoded = provider.load_bridge_config(path, fd)
        self.assertEqual(encoded[0], 1)
        id_length = encoded[1]
        self.assertEqual(encoded[2:2 + id_length], expected_id())
        offset = 2 + id_length
        values = []
        for expected in (ROOT_KEY, CONST_A, CONST_B):
            size = encoded[offset]
            offset += 1
            values.append(bytes(encoded[offset:offset + size]))
            offset += size
        self.assertEqual(values, [ROOT_KEY, CONST_A, CONST_B])
        self.assertEqual(offset, len(encoded))

    def test_rejects_invalid_schema_and_address_without_logging_values(self):
        bad = identity_json().replace('"format": 1', '"format": 2')
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            with self.assertRaises(provider.ConfigError) as caught:
                provider.build_bridge_config(bad, bytes.fromhex('123456789abc'))
        self.assertEqual(str(caught.exception), 'IDENTITY_CONFIG_INVALID')
        with self.assertRaises(provider.ConfigError) as address_error:
            provider._bt_address(address_pipe(b'02:00:00:00:00:00'))
        self.assertEqual(str(address_error.exception), 'BLUETOOTH_ADDRESS_UNAVAILABLE')
        self.assertEqual(output.getvalue(), '')
        for marker in SENSITIVE_MARKERS:
            self.assertNotIn(marker, output.getvalue())

    def test_trial_cli_uses_provider_and_never_logs_config_values(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / 'openhc-identity.json'
            path.write_text(identity_json(), encoding='utf-8')
            seen = {}

            class Client:
                def load_host_keys(self, _path): pass
                def set_missing_host_key_policy(self, _policy): pass
                def connect(self, *_args, **_kwargs): pass
                def close(self): pass

            class CapturingTrial:
                def __init__(self, _client, _log): pass
                def run(self, mode, session_evidence, bridge_config, identity_file=None):
                    seen['mode'] = mode
                    seen['config'] = bytes(bridge_config) if bridge_config is not None else None
                    seen['identity_file'] = identity_file
                    return 0

            trial.ROOT = root
            stdout = io.StringIO()
            with mock.patch.object(trial, 'Trial', CapturingTrial), \
                    mock.patch.object(trial.paramiko, 'SSHClient', Client), \
                    mock.patch.object(trial.sys, 'stdin', io.StringIO('synthetic-password\n')), \
                    contextlib.redirect_stdout(stdout):
                result = trial.main(['--execute', '--mode', 'inbound', '--identity-file', str(path)])
        self.assertEqual(result, 0)
        self.assertEqual(seen['mode'], 'inbound')
        self.assertIsNone(seen['config'])
        self.assertEqual(seen['identity_file'], path)
        self.assertNotIn(base64.b64encode(ROOT_KEY).decode('ascii'), stdout.getvalue())
        self.assertNotIn(ADDRESS_TEXT.decode('ascii'), stdout.getvalue())
        self.assertNotIn('synthetic-password', stdout.getvalue())
        for marker in SENSITIVE_MARKERS:
            self.assertNotIn(marker, stdout.getvalue())


if __name__ == '__main__':
    unittest.main(verbosity=2)
