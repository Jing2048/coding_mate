"""Device adapters: Watch / glove-card / bench → canonical ImuPacket.

Canonical algorithm frame
------------------------
After ``normalize_packet``, every stream is expressed as:

* ``handedness = RIGHT``
* ``wrist = LEAD``
* ``mount_extrinsic = identity``
* ``is_canonical = True``

Anatomical axes (right-handed triad, lead wrist of a right-handed golfer):

* +X — distal along the forearm (toward the hand)
* +Y — ulnar → radial (lateral in the anatomical sense; mirrored for lefties)
* +Z — completes the right-handed triad (palmar/dorsal sense)

Clients (Watch / glove firmware) must fill ``SensorFrame`` in the *device*
mount frame and set ``handedness`` / ``wrist`` honestly. The algo owns
normalization; adapters must not pre-mirror.
"""

from __future__ import annotations

from golfmate_algo.devices.glove_spec import GloveCardSpec, make_glove_packet
from golfmate_algo.devices.normalize import NormalizationInfo, normalize_packet
from golfmate_algo.devices.packed_capture_v2 import (
    PackedCaptureV2,
    decode_packed_capture_v2,
    encode_packed_capture_v2,
    is_packed_capture_v2,
    load_packed_capture_v2,
)
from golfmate_algo.devices.protocol import DeviceAdapter
from golfmate_algo.devices.watch_capture import WatchCapture, load_watch_capture
from golfmate_algo.devices.watch_spec import WatchSpec, make_watch_batch_packet

__all__ = [
    "DeviceAdapter",
    "GloveCardSpec",
    "NormalizationInfo",
    "PackedCaptureV2",
    "WatchCapture",
    "WatchSpec",
    "decode_packed_capture_v2",
    "encode_packed_capture_v2",
    "is_packed_capture_v2",
    "load_packed_capture_v2",
    "load_watch_capture",
    "make_glove_packet",
    "make_watch_batch_packet",
    "normalize_packet",
]
