"""DeviceAdapter protocol — hardware ingress contract."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from golfmate_algo.types import ImuPacket


@runtime_checkable
class DeviceAdapter(Protocol):
    """Convert a device-native batch into an ``ImuPacket``.

    Implementations live at the client edge (Swift Watch kit, glove BLE
    bridge, or bench loaders). The algo package ships only specs + fakes.
    """

    device_id: str

    def to_packet(self, *args: Any, **kwargs: Any) -> ImuPacket:
        """Return a fixed-rate packet in the *device mount* frame (not yet canonical)."""
        ...
