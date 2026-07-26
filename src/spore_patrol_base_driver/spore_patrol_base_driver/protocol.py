"""WHEELTEC STM32 velocity-command and status-frame protocol."""

from dataclasses import dataclass
import math
import struct
from typing import Iterable, List


FRAME_HEADER = 0x7B
FRAME_TAIL = 0x7D
COMMAND_FRAME_SIZE = 11
STATUS_FRAME_SIZE = 24
GRAVITY_MPS2 = 9.80665
DEFAULT_ACCEL_LSB_PER_G = 16384.0
DEFAULT_GYRO_LSB_PER_DEG_S = 65.5


def bcc(data: Iterable[int]) -> int:
    """Return the XOR/BCC byte used by the STM32 firmware."""

    value = 0
    for byte in data:
        value ^= int(byte)
    return value & 0xFF


def _to_milli_s16(value: float, name: str) -> int:
    scaled = int(round(value * 1000.0))
    if not -32768 <= scaled <= 32767:
        raise ValueError(f"{name}={value} is outside signed 16-bit range")
    return scaled


def accel_raw_to_mps2(
    value: int,
    lsb_per_g: float = DEFAULT_ACCEL_LSB_PER_G,
) -> float:
    """Convert one signed accelerometer count to m/s^2."""

    if lsb_per_g <= 0.0:
        raise ValueError("lsb_per_g must be positive")
    return float(value) * GRAVITY_MPS2 / lsb_per_g


def gyro_raw_to_radps(
    value: int,
    lsb_per_deg_s: float = DEFAULT_GYRO_LSB_PER_DEG_S,
) -> float:
    """Convert one signed gyroscope count to rad/s."""

    if lsb_per_deg_s <= 0.0:
        raise ValueError("lsb_per_deg_s must be positive")
    return float(value) * math.pi / 180.0 / lsb_per_deg_s


def build_command_frame(
    vx_mps: float,
    vy_mps: float,
    wz_radps: float,
    *,
    mode: int = 0,
    reserved: int = 0,
) -> bytes:
    """Build one 11-byte body-velocity command frame."""

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
    return bytes(frame)


@dataclass(frozen=True)
class StatusFrame:
    """Decoded 24-byte chassis feedback frame.

    Velocity and voltage fields are converted to SI units. Acceleration and
    gyroscope fields remain signed sensor counts because the STM32 firmware
    sends raw IMU values.
    """

    flag_stop: int
    vx_mps: float
    vy_mps: float
    wz_radps: float
    accel_x_raw: int
    accel_y_raw: int
    accel_z_raw: int
    gyro_x_raw: int
    gyro_y_raw: int
    gyro_z_raw: int
    battery_v: float


def parse_status_frame(frame: bytes) -> StatusFrame:
    """Validate and decode one 24-byte status frame."""

    if len(frame) != STATUS_FRAME_SIZE:
        raise ValueError(f"status frame must be {STATUS_FRAME_SIZE} bytes")
    if frame[0] != FRAME_HEADER:
        raise ValueError("invalid status frame header")
    if frame[-1] != FRAME_TAIL:
        raise ValueError("invalid status frame tail")
    if frame[22] != bcc(frame[:22]):
        raise ValueError("invalid status frame BCC")

    values = struct.unpack(">hhhhhhhhhh", frame[2:22])
    return StatusFrame(
        flag_stop=frame[1],
        vx_mps=values[0] / 1000.0,
        vy_mps=values[1] / 1000.0,
        wz_radps=values[2] / 1000.0,
        accel_x_raw=values[3],
        accel_y_raw=values[4],
        accel_z_raw=values[5],
        gyro_x_raw=values[6],
        gyro_y_raw=values[7],
        gyro_z_raw=values[8],
        battery_v=values[9] / 1000.0,
    )


class StatusStreamDecoder:
    """Recover valid status frames from an arbitrary serial byte stream."""

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
