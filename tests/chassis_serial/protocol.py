"""WHEELTEC STM32 serial protocol helpers.

The implementation mirrors the firmware in:

- BALANCE/uartx_callback.c: 11-byte velocity command frame
- BALANCE/data_task.c: 24-byte chassis status frame

All multibyte values use signed, big-endian 16-bit integers. Velocity command
values are represented in 0.001 SI-unit increments.
"""

from __future__ import annotations

from dataclasses import dataclass
import struct
from typing import Iterable, List


FRAME_HEADER = 0x7B
FRAME_TAIL = 0x7D
COMMAND_FRAME_SIZE = 11
STATUS_FRAME_SIZE = 24


def bcc(data: Iterable[int]) -> int:
    """Return the XOR/BCC used by the STM32 firmware."""

    value = 0
    for byte in data:
        value ^= int(byte)
    return value & 0xFF


def _to_milli_s16(value: float, name: str) -> int:
    scaled = int(round(value * 1000.0))
    if not -32768 <= scaled <= 32767:
        raise ValueError(f"{name}={value} is outside signed 16-bit protocol range")
    return scaled


def build_command_frame(
    vx_mps: float,
    vy_mps: float,
    wz_radps: float,
    *,
    mode: int = 0,
    reserved: int = 0,
) -> bytes:
    """Build an 11-byte STM32 velocity command frame."""

    if not 0 <= mode <= 0xFF:
        raise ValueError("mode must fit in one byte")
    if not 0 <= reserved <= 0xFF:
        raise ValueError("reserved must fit in one byte")

    frame = bytearray((FRAME_HEADER, mode, reserved))
    frame.extend(
        struct.pack(
            ">hhh",
            _to_milli_s16(vx_mps, "vx"),
            _to_milli_s16(vy_mps, "vy"),
            _to_milli_s16(wz_radps, "wz"),
        )
    )
    frame.append(bcc(frame))
    frame.append(FRAME_TAIL)
    if len(frame) != COMMAND_FRAME_SIZE:
        raise AssertionError("unexpected command frame length")
    return bytes(frame)


@dataclass(frozen=True)
class StatusFrame:
    flag_stop: int
    vx_mps: float
    vy_mps: float
    wz_radps: float
    accel_x: float
    accel_y: float
    accel_z: float
    gyro_x: float
    gyro_y: float
    gyro_z: float
    battery_v: float


def parse_status_frame(frame: bytes) -> StatusFrame:
    """Validate and decode one 24-byte STM32 status frame."""

    if len(frame) != STATUS_FRAME_SIZE:
        raise ValueError(f"status frame must be {STATUS_FRAME_SIZE} bytes")
    if frame[0] != FRAME_HEADER:
        raise ValueError("invalid status frame header")
    if frame[-1] != FRAME_TAIL:
        raise ValueError("invalid status frame tail")
    if frame[22] != bcc(frame[:22]):
        raise ValueError("invalid status frame BCC")

    values = struct.unpack(">hhhhhhhhhh", frame[2:22])
    scaled = [value / 1000.0 for value in values]
    return StatusFrame(
        flag_stop=frame[1],
        vx_mps=scaled[0],
        vy_mps=scaled[1],
        wz_radps=scaled[2],
        accel_x=scaled[3],
        accel_y=scaled[4],
        accel_z=scaled[5],
        gyro_x=scaled[6],
        gyro_y=scaled[7],
        gyro_z=scaled[8],
        battery_v=scaled[9],
    )


class StatusStreamDecoder:
    """Recover valid 24-byte status frames from an arbitrary byte stream."""

    def __init__(self) -> None:
        self._buffer = bytearray()
        self.discarded_bytes = 0
        self.invalid_candidates = 0

    def feed(self, data: bytes) -> List[StatusFrame]:
        self._buffer.extend(data)
        decoded: List[StatusFrame] = []

        while True:
            try:
                header_index = self._buffer.index(FRAME_HEADER)
            except ValueError:
                self.discarded_bytes += len(self._buffer)
                self._buffer.clear()
                break

            if header_index:
                self.discarded_bytes += header_index
                del self._buffer[:header_index]

            if len(self._buffer) < STATUS_FRAME_SIZE:
                break

            candidate = bytes(self._buffer[:STATUS_FRAME_SIZE])
            try:
                decoded.append(parse_status_frame(candidate))
            except ValueError:
                self.invalid_candidates += 1
                self.discarded_bytes += 1
                del self._buffer[0]
                continue

            del self._buffer[:STATUS_FRAME_SIZE]

        return decoded
