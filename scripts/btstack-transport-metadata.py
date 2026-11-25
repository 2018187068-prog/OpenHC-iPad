"""Metadata reader for a future guarded transport probe; no live entry point.

Wire evidence: read-only Showcase ce9d1d5, btstack_defines.h RFCOMM events
and platform/daemon/src/daemon.c. No commands, connection setup, power lease,
SDP queries, acceptance, or data I/O are implemented here. RFCOMM payloads and
non-allowlisted HCI parameters are refused before they are read.
"""
import socket
import struct
import time


class MetadataReader:
    # Full event sizes including event code and parameter length.
    SIZES = {0x60: (3,), 0x80: (16, 17), 0x81: (4,), 0x82: (11,),
             0x84: (5,), 0x85: (4,), 0x89: (4,), 0x90: (7,)}

    def __init__(self, stream):
        self.stream = stream
        self.frames = 0

    def exact(self, size, deadline):
        data = bytearray()
        while len(data) < size:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('METADATA_DEADLINE')
            self.stream.settimeout(min(remaining, 1))
            try:
                part = self.stream.recv(size - len(data))
            except socket.timeout:
                continue
            if not part:
                raise ValueError('METADATA_EOF')
            data.extend(part)
        return bytes(data)

    def receive(self, deadline):
        self.frames += 1
        if self.frames > 256:
            raise ValueError('METADATA_EVENT_LIMIT')
        kind, channel, size = struct.unpack('<HHH', self.exact(6, deadline))
        # Crucial: never receive an RFCOMM payload for an unverified peer.
        if kind != 4 or channel != 0 or not 2 <= size <= 17:
            raise ValueError('DISALLOWED_METADATA_FRAME')
        code, length = self.exact(2, deadline)
        if code not in self.SIZES:
            raise ValueError('DISALLOWED_EVENT_PARAMETERS_NOT_READ')
        if size not in self.SIZES[code] or length != size - 2:
            raise ValueError('METADATA_EVENT_SHAPE')
        body = bytes([code, length]) + self.exact(size - 2, deadline)
        if code == 0x60:
            if body[2] > 4:
                raise ValueError('METADATA_STATE_RANGE')
            return {'event': code, 'state': body[2]}
        if code == 0x80:
            # Skip address and ACL handle. These are not returned or logged.
            return self.opened(body)
        if code == 0x82:
            server, cid = body[8], struct.unpack_from('<H', body, 9)[0]
            if not 1 <= server <= 30 or not cid:
                raise ValueError('METADATA_INCOMING_RANGE')
            return {'event': code, 'server_channel': server, 'cid': cid}
        if code in (0x81, 0x89, 0x84):
            cid = struct.unpack_from('<H', body, 2)[0]
            if not cid:
                raise ValueError('METADATA_CID_RANGE')
            result = {'event': code, 'cid': cid}
            if code == 0x84:
                result['credits'] = body[4]
            return result
        if code == 0x85:
            if not 1 <= body[3] <= 30:
                raise ValueError('METADATA_SERVER_RANGE')
            return {'event': code, 'status': body[2], 'server_channel': body[3]}
        return {'event': code, 'status': body[2],
                'sdp_handle': struct.unpack_from('<I', body, 3)[0]}

    @staticmethod
    def opened(body):
        server = body[11]
        cid, mtu = struct.unpack_from('<HH', body, 12)
        # daemon's immediate create failure is 16 bytes and omits incoming;
        # rfcomm.c's normal opened event is 17. Never invent that direction.
        incoming = body[16] if len(body) == 17 else None
        if (not 1 <= server <= 30 or
                (not body[2] and (not cid or not mtu or incoming is None)) or
                (incoming is not None and incoming > 1)):
            raise ValueError('METADATA_OPEN_RANGE')
        return {'event': 0x80, 'status': body[2], 'server_channel': server,
                'cid': cid, 'mtu': mtu, 'incoming': incoming}
