"""Offline unit tests for the STM32 serial protocol."""

from __future__ import annotations

import os
import pty
import struct
import unittest

from tests.chassis_serial.chassis_serial_test import (
    LinuxSerialPort,
    require_safe_distance,
    require_safe_rotation,
)
from tests.chassis_serial.protocol import (
    FRAME_HEADER,
    FRAME_TAIL,
    StatusStreamDecoder,
    bcc,
    build_command_frame,
    parse_status_frame,
)


def make_status_frame(values: tuple[int, ...], flag_stop: int = 0) -> bytes:
    frame = bytearray((FRAME_HEADER, flag_stop))
    frame.extend(struct.pack(">hhhhhhhhhh", *values))
    frame.append(bcc(frame))
    frame.append(FRAME_TAIL)
    return bytes(frame)


class ProtocolTest(unittest.TestCase):
    def test_zero_command(self) -> None:
        frame = build_command_frame(0.0, 0.0, 0.0)
        self.assertEqual(len(frame), 11)
        self.assertEqual(frame[0], FRAME_HEADER)
        self.assertEqual(frame[-1], FRAME_TAIL)
        self.assertEqual(frame[9], bcc(frame[:9]))

    def test_signed_command_values(self) -> None:
        frame = build_command_frame(0.05, -0.02, 0.15)
        self.assertEqual(struct.unpack(">hhh", frame[3:9]), (50, -20, 150))

    def test_parse_status(self) -> None:
        raw = make_status_frame(
            (50, 0, -150, 100, -200, 9800, 10, -20, 30, 24500),
            flag_stop=1,
        )
        status = parse_status_frame(raw)
        self.assertEqual(status.flag_stop, 1)
        self.assertAlmostEqual(status.vx_mps, 0.05)
        self.assertAlmostEqual(status.wz_radps, -0.15)
        self.assertAlmostEqual(status.battery_v, 24.5)

    def test_stream_decoder_recovers_after_noise_and_fragmentation(self) -> None:
        raw = make_status_frame((1, 2, 3, 4, 5, 6, 7, 8, 9, 24000))
        decoder = StatusStreamDecoder()
        self.assertEqual(decoder.feed(b"\x00\x01" + raw[:7]), [])
        frames = decoder.feed(raw[7:] + raw)
        self.assertEqual(len(frames), 2)
        self.assertAlmostEqual(frames[0].battery_v, 24.0)
        self.assertEqual(decoder.discarded_bytes, 2)

    def test_bad_bcc_is_rejected(self) -> None:
        raw = bytearray(make_status_frame((0,) * 10))
        raw[22] ^= 0x01
        with self.assertRaisesRegex(ValueError, "BCC"):
            parse_status_frame(bytes(raw))

    def test_linux_serial_port_round_trip_over_pty(self) -> None:
        master_fd, slave_fd = pty.openpty()
        slave_name = os.ttyname(slave_fd)
        command = build_command_frame(0.05, 0.0, 0.15)
        feedback = make_status_frame((50, 0, 150, 0, 0, 9800, 0, 0, 150, 24500))
        try:
            with LinuxSerialPort(slave_name, 115200) as port:
                port.write(command)
                self.assertEqual(os.read(master_fd, len(command)), command)

                os.write(master_fd, feedback)
                received = port.read(timeout=0.2)
                status = parse_status_frame(received)
                self.assertAlmostEqual(status.vx_mps, 0.05)
                self.assertAlmostEqual(status.battery_v, 24.5)
        finally:
            os.close(master_fd)
            os.close(slave_fd)

    def test_distance_test_safety_limits(self) -> None:
        require_safe_distance(3.0, 0.10)
        with self.assertRaises(ValueError):
            require_safe_distance(3.01, 0.10)
        with self.assertRaises(ValueError):
            require_safe_distance(3.0, 0.11)

    def test_rotation_test_safety_limits(self) -> None:
        require_safe_rotation(360.0, 0.15)
        with self.assertRaises(ValueError):
            require_safe_rotation(360.1, 0.15)
        with self.assertRaises(ValueError):
            require_safe_rotation(360.0, 0.30)


if __name__ == "__main__":
    unittest.main()
