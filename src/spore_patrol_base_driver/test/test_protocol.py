import math
import struct

import pytest

from spore_patrol_base_driver.protocol import (
    FRAME_HEADER,
    FRAME_TAIL,
    StatusStreamDecoder,
    accel_raw_to_mps2,
    bcc,
    build_command_frame,
    gyro_raw_to_radps,
    parse_status_frame,
)


def make_status_frame(values, flag_stop=0):
    frame = bytearray((FRAME_HEADER, flag_stop))
    frame.extend(struct.pack(">hhhhhhhhhh", *values))
    frame.append(bcc(frame))
    frame.append(FRAME_TAIL)
    return bytes(frame)


def test_command_frame_signed_values():
    frame = build_command_frame(0.05, 0.0, -0.15)
    assert len(frame) == 11
    assert frame[0] == FRAME_HEADER
    assert frame[-1] == FRAME_TAIL
    assert struct.unpack(">hhh", frame[3:9]) == (50, 0, -150)
    assert frame[9] == bcc(frame[:9])


def test_status_preserves_raw_imu_counts():
    raw = make_status_frame(
        (50, 0, -150, 100, -200, 16384, 10, -20, 30, 24150),
        flag_stop=1,
    )
    status = parse_status_frame(raw)
    assert status.flag_stop == 1
    assert status.vx_mps == pytest.approx(0.05)
    assert status.wz_radps == pytest.approx(-0.15)
    assert status.accel_z_raw == 16384
    assert status.gyro_y_raw == -20
    assert status.battery_v == pytest.approx(24.15)


def test_imu_counts_convert_to_si_units():
    assert accel_raw_to_mps2(16384) == pytest.approx(9.80665)
    expected = math.radians(1.0)
    assert gyro_raw_to_radps(65.5) == pytest.approx(expected)


def test_stream_recovers_after_noise_and_fragmentation():
    raw = make_status_frame((1, 2, 3, 4, 5, 6, 7, 8, 9, 24000))
    decoder = StatusStreamDecoder()
    assert decoder.feed(b"\x00\x01" + raw[:8]) == []
    frames = decoder.feed(raw[8:] + raw)
    assert len(frames) == 2
    assert decoder.discarded_bytes == 2


def test_invalid_bcc_is_rejected():
    raw = bytearray(make_status_frame((0,) * 10))
    raw[22] ^= 0x01
    with pytest.raises(ValueError, match="BCC"):
        parse_status_frame(bytes(raw))
