"""Synthetic transport check driven by an explicit OpenHC session plan.

This does not parse SDP or HiCar control messages. The caller must map
WirelessReceiverSession actions/events to the plan types below.
"""
import time
from dataclasses import dataclass


FE35_UUID = '0000fe35-0000-1000-8000-00805f9b34fb'
DEFAULT_AUTH_UUID = '0000fe36-0000-1000-8000-00805f9b34fb'
CHANNEL_MIN = 1
CHANNEL_MAX = 30
SYNTHETIC = {
    'control': b'OPENHC-SYNTHETIC-CONTROL-v1',
    'auth': b'OPENHC-SYNTHETIC-AUTH-v1',
}


@dataclass(frozen=True)
class ChannelPlan:
    name: str
    uuid: str
    channel: int
    local_action: str
    channel_owner: str
    source: str


def control_plan(flow, channel):
    if flow == 'phone-initiated':
        return ChannelPlan('control', FE35_UUID, channel, 'listen', 'local', 'local-listen-result')
    if flow == 'vehicle-reconnect':
        return ChannelPlan('control', FE35_UUID, channel, 'connect', 'peer', 'sdp-result')
    raise ValueError('CONTROL_FLOW_UNKNOWN')


def auth_plan(flow, channel, uuid=DEFAULT_AUTH_UUID):
    if not isinstance(uuid, str) or len(uuid) not in (4, 36):
        raise ValueError('AUTH_UUID_SHAPE')
    if flow == 'phone-requested-subchannel':
        return ChannelPlan('auth', uuid, channel, 'listen', 'local', 'control-socket-request')
    if flow == 'vehicle-reconnect-response':
        return ChannelPlan('auth', uuid, channel, 'connect', 'peer', 'control-auth-channel-ready')
    raise ValueError('AUTH_FLOW_UNKNOWN')


def validate_plan(plans):
    if not isinstance(plans, (tuple, list)) or not 1 <= len(plans) <= 2:
        raise ValueError('TRANSPORT_PLAN_SHAPE')
    names = set()
    listening_channels = set()
    for plan in plans:
        if not isinstance(plan, ChannelPlan) or plan.name not in ('control', 'auth'):
            raise ValueError('TRANSPORT_PLAN_ENTRY')
        if plan.name in names:
            raise ValueError('TRANSPORT_PLAN_DUPLICATE_ROLE')
        names.add(plan.name)
        if (type(plan.channel) is not int or not CHANNEL_MIN <= plan.channel <= CHANNEL_MAX or
                plan.local_action not in ('listen', 'connect') or
                plan.channel_owner not in ('local', 'peer')):
            raise ValueError('TRANSPORT_PLAN_RANGE_OR_ROLE')
        if (plan.local_action == 'listen') != (plan.channel_owner == 'local'):
            raise ValueError('TRANSPORT_PLAN_OWNER_MISMATCH')
        if plan.local_action == 'listen':
            if plan.channel in listening_channels:
                raise ValueError('LOCAL_LISTENER_CHANNEL_COLLISION')
            listening_channels.add(plan.channel)
    if 'control' not in names:
        raise ValueError('TRANSPORT_CONTROL_REQUIRED')
    return tuple(plans)


class SyntheticTransportRunner:
    """Exercise a controlled synthetic peer with fixed, non-protocol bytes.

    Adapter contract: open(plan, deadline)->handle; exchange(handle, bytes,
    deadline)->bytes; close(handle, cleanup_deadline); release_power(cleanup_deadline).
    The caller owns the power lease under the existing recovery guard.
    """
    def __init__(self, adapter, plans, deadline_seconds=25):
        if not 1 <= deadline_seconds <= 60:
            raise ValueError('TRANSPORT_DEADLINE_RANGE')
        self.adapter = adapter
        self.plans = validate_plan(plans)
        self.deadline_seconds = deadline_seconds
        self.opened = []

    def run(self, emit=None):
        emit = emit or (lambda _: None)
        deadline = time.monotonic() + self.deadline_seconds
        failure = None
        try:
            for plan in self.plans:
                self.check_deadline(deadline)
                emit('TRANSPORT_CHANNEL=' + plan.name + ':' + plan.uuid + ':' +
                     str(plan.channel) + ':' + plan.local_action + ':' + plan.source)
                handle = self.adapter.open(plan, deadline)
                self.opened.append((plan, handle))
                self.check_deadline(deadline)
            for plan, handle in self.opened:
                self.check_deadline(deadline)
                result = self.adapter.exchange(handle, SYNTHETIC[plan.name], deadline)
                self.check_deadline(deadline)
                if result != SYNTHETIC[plan.name]:
                    raise RuntimeError('SYNTHETIC_ROUNDTRIP_MISMATCH=' + plan.name)
                emit('TRANSPORT_SYNTHETIC_ROUNDTRIP_OK=' + plan.name)
        except Exception as error:
            failure = error

        cleanup_deadline = time.monotonic() + 5
        cleanup_errors = []
        for plan, handle in reversed(self.opened):
            try:
                self.adapter.close(handle, cleanup_deadline)
                emit('TRANSPORT_CHANNEL_CLOSED=' + plan.name)
            except Exception:
                cleanup_errors.append('CHANNEL_CLOSE_FAILED')
        try:
            self.adapter.release_power(cleanup_deadline)
            emit('TRANSPORT_POWER_RELEASED')
        except Exception:
            cleanup_errors.append('POWER_RELEASE_FAILED')
        self.opened.clear()
        if cleanup_errors:
            raise RuntimeError(','.join(cleanup_errors)) from failure
        if failure:
            raise failure
        return True

    @staticmethod
    def check_deadline(deadline):
        if time.monotonic() >= deadline:
            raise TimeoutError('TRANSPORT_DEADLINE')
