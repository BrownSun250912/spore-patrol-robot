#!/usr/bin/env python3
"""Safe, dependency-free field test CLI for the WHEELTEC STM32 chassis."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
import glob
import json
import os
from pathlib import Path
import select
import sys
import termios
import time
from typing import Callable, Iterable, Optional

try:
    from protocol import StatusFrame, StatusStreamDecoder, build_command_frame
except ImportError:
    from tests.chassis_serial.protocol import (
        StatusFrame,
        StatusStreamDecoder,
        build_command_frame,
    )


REPO_ROOT = Path(__file__).resolve().parents[2]
RESULTS_ROOT = REPO_ROOT / "tests" / "results"
NORMAL_ARM_TEXT = "WHEELS_OFF_GROUND"
FAILSAFE_ARM_TEXT = "WHEELS_OFF_GROUND_AND_EMERGENCY_STOP_READY"
MAX_LINEAR_MPS = 0.15
MAX_ANGULAR_RADPS = 0.30
MAX_MOTION_DURATION_S = 5.0


BAUD_CONSTANTS = {
    9600: termios.B9600,
    19200: termios.B19200,
    38400: termios.B38400,
    57600: termios.B57600,
    115200: termios.B115200,
    230400: termios.B230400,
}


class LinuxSerialPort:
    """Small Linux serial wrapper using only the Python standard library."""

    def __init__(self, device: str, baud: int = 115200) -> None:
        if baud not in BAUD_CONSTANTS:
            raise ValueError(f"unsupported baud rate: {baud}")
        self.device = device
        self.baud = baud
        self.fd: Optional[int] = None

    def __enter__(self) -> "LinuxSerialPort":
        self.fd = os.open(
            self.device,
            os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK,
        )
        attrs = termios.tcgetattr(self.fd)
        attrs[0] = 0
        attrs[1] = 0
        attrs[2] = termios.CLOCAL | termios.CREAD | termios.CS8
        attrs[3] = 0
        attrs[4] = BAUD_CONSTANTS[self.baud]
        attrs[5] = BAUD_CONSTANTS[self.baud]
        attrs[6][termios.VMIN] = 0
        attrs[6][termios.VTIME] = 0
        termios.tcsetattr(self.fd, termios.TCSANOW, attrs)
        termios.tcflush(self.fd, termios.TCIOFLUSH)
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def read(self, timeout: float = 0.05, size: int = 4096) -> bytes:
        if self.fd is None:
            raise RuntimeError("serial port is not open")
        readable, _, _ = select.select([self.fd], [], [], timeout)
        if not readable:
            return b""
        try:
            return os.read(self.fd, size)
        except BlockingIOError:
            return b""

    def write(self, data: bytes, timeout: float = 1.0) -> None:
        if self.fd is None:
            raise RuntimeError("serial port is not open")
        view = memoryview(data)
        deadline = time.monotonic() + timeout
        while view:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("serial write timed out")
            _, writable, _ = select.select([], [self.fd], [], remaining)
            if not writable:
                continue
            written = os.write(self.fd, view)
            view = view[written:]


class CaptureSession:
    CSV_FIELDS = (
        "elapsed_s",
        "flag_stop",
        "vx_mps",
        "vy_mps",
        "wz_radps",
        "accel_x",
        "accel_y",
        "accel_z",
        "gyro_x",
        "gyro_y",
        "gyro_z",
        "battery_v",
    )

    def __init__(self, command: str, device: str, baud: int) -> None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        self.path = RESULTS_ROOT / f"{timestamp}_{command}"
        self.path.mkdir(parents=True, exist_ok=False)
        self.raw_file = (self.path / "raw.bin").open("wb")
        self.csv_file = (self.path / "frames.csv").open("w", newline="")
        self.writer = csv.DictWriter(self.csv_file, fieldnames=self.CSV_FIELDS)
        self.writer.writeheader()
        self.decoder = StatusStreamDecoder()
        self.started = time.monotonic()
        self.frame_count = 0
        self.latest: Optional[StatusFrame] = None
        metadata = {
            "command": command,
            "device": device,
            "baud": baud,
            "started_at": datetime.now().isoformat(timespec="seconds"),
        }
        (self.path / "metadata.json").write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def feed(self, data: bytes) -> list[tuple[float, StatusFrame]]:
        if not data:
            return []
        self.raw_file.write(data)
        rows = []
        for status in self.decoder.feed(data):
            elapsed = time.monotonic() - self.started
            row = {"elapsed_s": f"{elapsed:.6f}", **status.__dict__}
            self.writer.writerow(row)
            self.frame_count += 1
            self.latest = status
            rows.append((elapsed, status))
        return rows

    def close(self) -> None:
        self.raw_file.close()
        self.csv_file.close()

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.started

    @property
    def frame_rate(self) -> float:
        return self.frame_count / self.elapsed if self.elapsed > 0 else 0.0


def serial_candidates() -> list[str]:
    candidates = set()
    for pattern in (
        "/dev/serial/by-id/*",
        "/dev/ttyUSB*",
        "/dev/ttyACM*",
    ):
        candidates.update(glob.glob(pattern))
    return sorted(candidates)


def require_safe_motion(vx: float, vy: float, wz: float, duration: float) -> None:
    if abs(vx) > MAX_LINEAR_MPS or abs(vy) > MAX_LINEAR_MPS:
        raise ValueError(
            f"linear speed is limited to ±{MAX_LINEAR_MPS:.2f} m/s"
        )
    if abs(wz) > MAX_ANGULAR_RADPS:
        raise ValueError(
            f"angular speed is limited to ±{MAX_ANGULAR_RADPS:.2f} rad/s"
        )
    if not 0 < duration <= MAX_MOTION_DURATION_S:
        raise ValueError(
            f"motion duration must be within (0, {MAX_MOTION_DURATION_S:.1f}] s"
        )


def send_stop_burst(port: LinuxSerialPort, count: int = 15) -> None:
    stop = build_command_frame(0.0, 0.0, 0.0)
    for _ in range(count):
        port.write(stop)
        time.sleep(0.02)


def drain_feedback(
    port: LinuxSerialPort,
    capture: CaptureSession,
    duration: float,
    *,
    print_interval: float = 1.0,
) -> None:
    deadline = time.monotonic() + duration
    next_print = time.monotonic()
    while time.monotonic() < deadline:
        rows = capture.feed(port.read(timeout=0.05))
        now = time.monotonic()
        if rows and now >= next_print:
            _, status = rows[-1]
            print_status(status, capture.frame_rate)
            next_print = now + print_interval


def print_status(status: StatusFrame, rate: float) -> None:
    print(
        f"frames={rate:5.1f}Hz stop={status.flag_stop} "
        f"vx={status.vx_mps:+.3f} vy={status.vy_mps:+.3f} "
        f"wz={status.wz_radps:+.3f} battery={status.battery_v:.2f}V"
    )


def run_velocity(
    port: LinuxSerialPort,
    capture: CaptureSession,
    vx: float,
    vy: float,
    wz: float,
    duration: float,
    rate: float = 20.0,
) -> None:
    require_safe_motion(vx, vy, wz, duration)
    frame = build_command_frame(vx, vy, wz)
    period = 1.0 / rate
    deadline = time.monotonic() + duration
    next_send = time.monotonic()
    next_print = time.monotonic()
    while time.monotonic() < deadline:
        now = time.monotonic()
        if now >= next_send:
            port.write(frame)
            next_send += period
        rows = capture.feed(port.read(timeout=min(0.02, period)))
        if rows and now >= next_print:
            _, status = rows[-1]
            print_status(status, capture.frame_rate)
            next_print = now + 0.5


def with_port_and_capture(
    args: argparse.Namespace,
    command: str,
    operation: Callable[[LinuxSerialPort, CaptureSession], None],
) -> None:
    capture: Optional[CaptureSession] = None
    try:
        with LinuxSerialPort(args.port, args.baud) as port:
            capture = CaptureSession(command, args.port, args.baud)
            print(f"Opened {args.port} at {args.baud} baud")
            print(f"Results: {capture.path}")
            operation(port, capture)
    except PermissionError as exc:
        raise SystemExit(
            f"Permission denied opening {args.port}. "
            'Add the user to dialout: sudo usermod -aG dialout "$USER", '
            "then log out and back in."
        ) from exc
    except FileNotFoundError as exc:
        raise SystemExit(f"Serial device not found: {args.port}") from exc
    finally:
        if capture is not None:
            capture.close()
            print(
                f"Captured {capture.frame_count} valid frames "
                f"({capture.frame_rate:.1f} Hz average)"
            )


def command_ports(_args: argparse.Namespace) -> None:
    ports = serial_candidates()
    if not ports:
        print("No /dev/ttyUSB*, /dev/ttyACM* or /dev/serial/by-id/* devices found.")
        return
    for port in ports:
        resolved = os.path.realpath(port)
        suffix = f" -> {resolved}" if resolved != port else ""
        print(f"{port}{suffix}")


def command_selftest(_args: argparse.Namespace) -> None:
    samples = (
        ("stop", 0.0, 0.0, 0.0),
        ("forward", 0.05, 0.0, 0.0),
        ("reverse", -0.05, 0.0, 0.0),
        ("rotate-left", 0.0, 0.0, 0.15),
    )
    for name, vx, vy, wz in samples:
        frame = build_command_frame(vx, vy, wz)
        print(f"{name:12s}: {frame.hex(' ')}")


def command_listen(args: argparse.Namespace) -> None:
    def operation(port: LinuxSerialPort, capture: CaptureSession) -> None:
        drain_feedback(port, capture, args.duration)
        if capture.frame_count == 0:
            print(
                "WARNING: no valid 24-byte status frames were decoded. "
                "Check TX/RX/GND, baud rate, port selection and firmware."
            )

    with_port_and_capture(args, "listen", operation)


def command_stop(args: argparse.Namespace) -> None:
    def operation(port: LinuxSerialPort, capture: CaptureSession) -> None:
        send_stop_burst(port)
        drain_feedback(port, capture, 1.0)
        print("Stop burst sent.")

    with_port_and_capture(args, "stop", operation)


def command_motion(args: argparse.Namespace) -> None:
    if args.arm != NORMAL_ARM_TEXT:
        raise SystemExit(f"Refusing motion: pass --arm {NORMAL_ARM_TEXT}")
    require_safe_motion(args.vx, args.vy, args.wz, args.duration)

    def operation(port: LinuxSerialPort, capture: CaptureSession) -> None:
        try:
            print(
                f"Motion: vx={args.vx:+.3f}, vy={args.vy:+.3f}, "
                f"wz={args.wz:+.3f}, duration={args.duration:.1f}s"
            )
            run_velocity(
                port,
                capture,
                args.vx,
                args.vy,
                args.wz,
                args.duration,
            )
        finally:
            send_stop_burst(port)
            drain_feedback(port, capture, 0.5)
            print("Stop burst sent.")

    with_port_and_capture(args, "motion", operation)


def command_sequence(args: argparse.Namespace) -> None:
    if args.arm != NORMAL_ARM_TEXT:
        raise SystemExit(f"Refusing sequence: pass --arm {NORMAL_ARM_TEXT}")

    steps = (
        ("forward", 0.05, 0.0, 0.0),
        ("reverse", -0.05, 0.0, 0.0),
        ("rotate-left", 0.0, 0.0, 0.15),
        ("rotate-right", 0.0, 0.0, -0.15),
    )

    def operation(port: LinuxSerialPort, capture: CaptureSession) -> None:
        try:
            send_stop_burst(port)
            for name, vx, vy, wz in steps:
                print(f"\nSTEP: {name}")
                run_velocity(port, capture, vx, vy, wz, 2.0)
                send_stop_burst(port)
                drain_feedback(port, capture, 1.0, print_interval=0.5)
        finally:
            send_stop_burst(port)
            print("Final stop burst sent.")

    with_port_and_capture(args, "sequence", operation)


def command_failsafe(args: argparse.Namespace) -> None:
    if args.arm != FAILSAFE_ARM_TEXT:
        raise SystemExit(f"Refusing failsafe test: pass --arm {FAILSAFE_ARM_TEXT}")

    def operation(port: LinuxSerialPort, capture: CaptureSession) -> None:
        silence_started = 0.0
        stopped_after: Optional[float] = None
        try:
            print("Sending +0.03 m/s for 1.0 s...")
            run_velocity(port, capture, 0.03, 0.0, 0.0, 1.0)
            print("COMMAND SILENCE for 2.0 s; no stop frame is being sent.")
            silence_started = time.monotonic()
            deadline = silence_started + 2.0
            while time.monotonic() < deadline:
                rows = capture.feed(port.read(timeout=0.05))
                for _, status in rows:
                    if (
                        stopped_after is None
                        and abs(status.vx_mps) < 0.01
                        and abs(status.wz_radps) < 0.02
                    ):
                        stopped_after = time.monotonic() - silence_started
                if rows:
                    print_status(rows[-1][1], capture.frame_rate)
        finally:
            send_stop_burst(port)
            drain_feedback(port, capture, 0.5)
            print("Recovery stop burst sent.")

        if stopped_after is None:
            print(
                "FAIL/INCONCLUSIVE: feedback did not fall below the stop threshold "
                "during the 2.0 s command silence."
            )
        else:
            print(f"Observed near-zero feedback after {stopped_after:.3f} s.")
            if stopped_after <= 1.2:
                print("PASS candidate: verify the wheel video before accepting.")
            else:
                print("FAIL: stop response exceeded the 1.2 s acceptance threshold.")

    with_port_and_capture(args, "failsafe", operation)


def positive_duration(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("duration must be positive")
    return parsed


def add_serial_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--port", required=True, help="e.g. /dev/ttyUSB0")
    parser.add_argument("--baud", type=int, default=115200)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Safe serial field tests for the WHEELTEC STM32 chassis."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    ports = subparsers.add_parser("ports", help="list likely serial devices")
    ports.set_defaults(func=command_ports)

    selftest = subparsers.add_parser(
        "selftest", help="print known command frames without opening a port"
    )
    selftest.set_defaults(func=command_selftest)

    listen = subparsers.add_parser("listen", help="read and log status frames only")
    add_serial_arguments(listen)
    listen.add_argument("--duration", type=positive_duration, default=10.0)
    listen.set_defaults(func=command_listen)

    stop = subparsers.add_parser("stop", help="send repeated zero-velocity frames")
    add_serial_arguments(stop)
    stop.set_defaults(func=command_stop)

    motion = subparsers.add_parser("motion", help="run one short, low-speed motion")
    add_serial_arguments(motion)
    motion.add_argument("--vx", type=float, default=0.0)
    motion.add_argument("--vy", type=float, default=0.0)
    motion.add_argument("--wz", type=float, default=0.0)
    motion.add_argument("--duration", type=positive_duration, default=2.0)
    motion.add_argument("--arm", default="")
    motion.set_defaults(func=command_motion)

    sequence = subparsers.add_parser(
        "sequence", help="run forward/reverse/left/right with stops"
    )
    add_serial_arguments(sequence)
    sequence.add_argument("--arm", default="")
    sequence.set_defaults(func=command_sequence)

    failsafe = subparsers.add_parser(
        "failsafe", help="test automatic stop after command silence"
    )
    add_serial_arguments(failsafe)
    failsafe.add_argument("--arm", default="")
    failsafe.set_defaults(func=command_failsafe)
    return parser


def main(argv: Optional[Iterable[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
    except KeyboardInterrupt:
        print("\nInterrupted by user.", file=sys.stderr)
        return 130
    except (ValueError, TimeoutError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
