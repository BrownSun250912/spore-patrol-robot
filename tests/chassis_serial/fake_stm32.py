#!/usr/bin/env python3
"""Pseudo-terminal STM32 simulator for rehearsing the field-test CLI."""

from __future__ import annotations

import os
import pty
import select
import struct
import termios
import time
import tty

try:
    from protocol import FRAME_HEADER, FRAME_TAIL, bcc
except ImportError:
    from tests.chassis_serial.protocol import FRAME_HEADER, FRAME_TAIL, bcc


COMMAND_SIZE = 11
FEEDBACK_PERIOD_S = 0.05
SIMULATED_COMMAND_TIMEOUT_S = 1.0


def build_status(vx: float, vy: float, wz: float) -> bytes:
    values = (
        int(round(vx * 1000)),
        int(round(vy * 1000)),
        int(round(wz * 1000)),
        0,
        0,
        9800,
        0,
        0,
        int(round(wz * 1000)),
        24500,
    )
    frame = bytearray((FRAME_HEADER, 0))
    frame.extend(struct.pack(">hhhhhhhhhh", *values))
    frame.append(bcc(frame))
    frame.append(FRAME_TAIL)
    return bytes(frame)


def decode_commands(buffer: bytearray) -> list[tuple[float, float, float]]:
    commands = []
    while True:
        try:
            header = buffer.index(FRAME_HEADER)
        except ValueError:
            buffer.clear()
            return commands

        if header:
            del buffer[:header]
        if len(buffer) < COMMAND_SIZE:
            return commands

        candidate = bytes(buffer[:COMMAND_SIZE])
        if (
            candidate[-1] == FRAME_TAIL
            and candidate[9] == bcc(candidate[:9])
            and candidate[1] == 0
        ):
            vx, vy, wz = struct.unpack(">hhh", candidate[3:9])
            commands.append((vx / 1000.0, vy / 1000.0, wz / 1000.0))
            del buffer[:COMMAND_SIZE]
        else:
            del buffer[0]


def main() -> int:
    master_fd, slave_fd = pty.openpty()
    tty.setraw(slave_fd)
    slave_name = os.ttyname(slave_fd)
    print(f"Fake STM32 ready on: {slave_name}", flush=True)
    print("Press Ctrl+C to stop.", flush=True)

    rx_buffer = bytearray()
    velocity = (0.0, 0.0, 0.0)
    last_command = time.monotonic()
    next_feedback = time.monotonic()

    try:
        while True:
            now = time.monotonic()
            readable, _, _ = select.select([master_fd], [], [], 0.01)
            if readable:
                data = os.read(master_fd, 4096)
                rx_buffer.extend(data)
                for velocity in decode_commands(rx_buffer):
                    last_command = now
                    print(
                        f"command vx={velocity[0]:+.3f} "
                        f"vy={velocity[1]:+.3f} wz={velocity[2]:+.3f}",
                        flush=True,
                    )

            if now - last_command > SIMULATED_COMMAND_TIMEOUT_S:
                velocity = (0.0, 0.0, 0.0)

            if now >= next_feedback:
                os.write(master_fd, build_status(*velocity))
                next_feedback += FEEDBACK_PERIOD_S
    except KeyboardInterrupt:
        print("\nFake STM32 stopped.")
    finally:
        termios.tcflush(master_fd, termios.TCIOFLUSH)
        os.close(master_fd)
        os.close(slave_fd)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
