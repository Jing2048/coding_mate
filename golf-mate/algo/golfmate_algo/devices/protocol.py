"""DeviceAdapter protocol — hardware ingress contract."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from golfmate_algo.types import ImuPacket


@runtime_checkable
class DeviceAdapter(Protocol):
    """Convert a device-native batch into an ``ImuPacket``.

    Implementations live at the client edge (Swift Watch kit under
    ``golf-mate/apple``, glove BLE bridge, or bench loaders). The Python edge
    adapter for Watch capture files is ``devices.watch_capture``.
    """

    device_id: str

    def to_packet(self, *args: Any, **kwargs: Any) -> ImuPacket:
        """Return a fixed-rate packet in the *device mount* frame (not yet canonical)."""
        ...
