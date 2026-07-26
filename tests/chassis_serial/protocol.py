"""Compatibility import for the shared, dependency-free STM32 protocol.

The canonical implementation lives in ``src/spore_patrol_base_driver`` so the
field-test CLI and the ROS 2 node cannot silently disagree about units.
"""

from pathlib import Path
import sys


WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
BASE_DRIVER_SOURCE = WORKSPACE_ROOT / "src" / "spore_patrol_base_driver"
source_text = str(BASE_DRIVER_SOURCE)
if source_text not in sys.path:
    sys.path.insert(0, source_text)

from spore_patrol_base_driver.protocol import (  # noqa: E402,F401
    COMMAND_FRAME_SIZE,
    DEFAULT_ACCEL_LSB_PER_G,
    DEFAULT_GYRO_LSB_PER_DEG_S,
    FRAME_HEADER,
    FRAME_TAIL,
    STATUS_FRAME_SIZE,
    StatusFrame,
    StatusStreamDecoder,
    accel_raw_to_mps2,
    bcc,
    build_command_frame,
    gyro_raw_to_radps,
    parse_status_frame,
)


__all__ = [
    "COMMAND_FRAME_SIZE",
    "DEFAULT_ACCEL_LSB_PER_G",
    "DEFAULT_GYRO_LSB_PER_DEG_S",
    "FRAME_HEADER",
    "FRAME_TAIL",
    "STATUS_FRAME_SIZE",
    "StatusFrame",
    "StatusStreamDecoder",
    "accel_raw_to_mps2",
    "bcc",
    "build_command_frame",
    "gyro_raw_to_radps",
    "parse_status_frame",
]
