"""USB printer-class transport for the QUIN/Phomemo TP88 (and M08F-class kin).

TiMini-Print ships Bluetooth (BLE/SPP) and pyserial transports. The TP88 is plugged
in over USB and exposes a USB printer-class interface bound to the kernel `usblp`
driver as a character device (default /dev/usb/lp0). A print job is just
`ProtocolJob.payload` bytes (see docs/architecture.md), so this connector simply
writes those bytes to the char device in the profile's stream chunks — the same
contract the SerialConnection fulfils, minus pyserial's termios assumptions (which
fail on a usbmisc char device).

This is our project addition; upstream TiMini-Print is Apache-2.0.
"""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Callable

import _bootstrap  # noqa: F401  (puts the TiMini-Print submodule on sys.path)
from timiniprint.devices import PrinterDevice
from timiniprint.protocol import ProtocolJob

DEFAULT_DEVICE_PATH = "/dev/usb/lp0"


class UsblpConnection:
    """Write protocol jobs to a USB printer-class char device (e.g. /dev/usb/lp0)."""

    def __init__(self, device: PrinterDevice, path: str = DEFAULT_DEVICE_PATH) -> None:
        self._device = device
        self._path = path

    # --- optional RuntimeProbeConnection surface: this is a one-way pipe ---------
    async def attach_runtime_controller(self, runtime_controller, *, timeout: float = 1.0) -> None:
        _ = runtime_controller, timeout
        return None

    def can_send_control_packet(self) -> bool:
        return False

    def can_query_control_packet(self) -> bool:
        return False

    def can_wait_for_notification(self) -> bool:
        return False

    def can_send_control_packet_wait_notification(self) -> bool:
        return False

    async def send_control_packet(self, packet: bytes, *, timeout: float = 1.0) -> bool:
        _ = packet, timeout
        return False

    async def query_control_packet(
        self,
        packet: bytes,
        *,
        timeout: float = 1.0,
        reply_complete: Callable[[bytes], bool] | None = None,
    ) -> bytes | None:
        _ = packet, timeout, reply_complete
        return None

    # --- the actual send ---------------------------------------------------------
    async def send(self, job: ProtocolJob) -> None:
        _ = job.runtime_controller
        await self.send_standard_payload(job.payload)

    async def send_standard_payload(self, data: bytes) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            self._write_blocking,
            data,
            self._device.profile.stream.chunk_size,
            self._device.profile.stream.delay_ms,
        )

    async def disconnect(self) -> None:
        return None

    def _write_blocking(self, data: bytes, chunk_size: int, delay_ms: int) -> None:
        delay = max(0.0, delay_ms / 1000.0)
        chunk_size = max(1, int(chunk_size))
        try:
            fd = os.open(self._path, os.O_WRONLY)
        except OSError as exc:
            raise RuntimeError(
                f"Cannot open {self._path} for writing: {exc}. "
                f"Is the printer connected and is your user granted access (udev rule)?"
            ) from exc
        try:
            offset = 0
            while offset < len(data):
                chunk = data[offset : offset + chunk_size]
                written = 0
                while written < len(chunk):
                    written += os.write(fd, chunk[written:])
                offset += len(chunk)
                if delay:
                    time.sleep(delay)
        finally:
            os.close(fd)


class UsblpConnector:
    """Create USB printer-class connections bound to a device path."""

    def __init__(self, path: str = DEFAULT_DEVICE_PATH) -> None:
        self._path = path

    async def connect(self, device: PrinterDevice) -> UsblpConnection:
        return UsblpConnection(device, path=self._path)
