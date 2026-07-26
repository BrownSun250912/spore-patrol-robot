#!/usr/bin/env python3
"""Safe, dependency-free field test CLI for the WHEELTEC STM32 chassis."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
import glob
import json
import math
import os
from pathlib import Path
import select
import sys
import termios
import time
from typing import Callable, Iterable, Optional

try:
    from protocol import (
        StatusFrame,
        StatusStreamDecoder,
        accel_raw_to_mps2,
        build_command_frame,
        gyro_raw_to_radps,
    )
except ImportError:
    from tests.chassis_serial.protocol import (
        StatusFrame,
        StatusStreamDecoder,
        accel_raw_to_mps2,
        build_command_frame,
        gyro_raw_to_radps,
    )


REPO_ROOT = Path(__file__).resolve().parents[2]
RESULTS_ROOT = REPO_ROOT / "tests" / "results"
NORMAL_ARM_TEXT = "WHEELS_OFF_GROUND"
FAILSAFE_ARM_TEXT = "WHEELS_OFF_GROUND_AND_EMERGENCY_STOP_READY"
DISTANCE_ARM_TEXT = "OPEN_AREA_AND_EMERGENCY_STOP_READY"
MAX_LINEAR_MPS = 0.15
MAX_ANGULAR_RADPS = 0.30
MAX_MOTION_DURATION_S = 5.0
MAX_DISTANCE_M = 3.0
MAX_DISTANCE_SPEED_MPS = 0.10
MIN_DISTANCE_SPEED_MPS = 0.03
MAX_ROTATION_ANGLE_DEG = 360.0
MAX_ROTATION_SPEED_RADPS = 0.25
MIN_ROTATION_SPEED_RADPS = 0.10


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
        "accel_x_raw",
        "accel_y_raw",
        "accel_z_raw",
        "gyro_x_raw",
        "gyro_y_raw",
        "gyro_z_raw",
        "accel_x_mps2",
        "accel_y_mps2",
        "accel_z_mps2",
        "gyro_x_radps",
        "gyro_y_radps",
        "gyro_z_radps",
        "battery_v",
    )

    def __init__(
        self,
        command: str,
        device: str,
        baud: int,
        parameters: dict,
    ) -> None:
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
        self.metadata = {
            "command": command,
            "device": device,
            "baud": baud,
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "parameters": parameters,
        }
        self._write_json("metadata.json", self.metadata)

    def _write_json(self, filename: str, value: dict) -> None:
        (self.path / filename).write_text(
            json.dumps(value, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def feed(self, data: bytes) -> list[tuple[float, StatusFrame]]:
        if not data:
            return []
        self.raw_file.write(data)
        rows = []
        for status in self.decoder.feed(data):
            elapsed = time.monotonic() - self.started
            row = {
                "elapsed_s": f"{elapsed:.6f}",
                **status.__dict__,
                "accel_x_mps2": accel_raw_to_mps2(status.accel_x_raw),
                "accel_y_mps2": accel_raw_to_mps2(status.accel_y_raw),
                "accel_z_mps2": accel_raw_to_mps2(status.accel_z_raw),
                "gyro_x_radps": gyro_raw_to_radps(status.gyro_x_raw),
                "gyro_y_radps": gyro_raw_to_radps(status.gyro_y_raw),
                "gyro_z_radps": gyro_raw_to_radps(status.gyro_z_raw),
            }
            self.writer.writerow(row)
            self.frame_count += 1
            self.latest = status
            rows.append((elapsed, status))
        return rows

    def close(self) -> None:
        self.raw_file.close()
        self.csv_file.close()

    def write_summary(
        self,
        outcome: str,
        details: Optional[dict] = None,
        error: Optional[str] = None,
    ) -> None:
        summary = {
            "command": self.metadata["command"],
            "outcome": outcome,
            "finished_at": datetime.now().isoformat(timespec="seconds"),
            "frame_count": self.frame_count,
            "average_feedback_rate_hz": round(self.frame_rate, 3),
            "discarded_serial_bytes": self.decoder.discarded_bytes,
            "invalid_frame_candidates": self.decoder.invalid_candidates,
        }
        if details:
            summary.update(details)
        if error:
            summary["error"] = error
        self._write_json("summary.json", summary)

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
        raise ValueError(f"linear speed is limited to ±{MAX_LINEAR_MPS:.2f} m/s")
    if abs(wz) > MAX_ANGULAR_RADPS:
        raise ValueError(f"angular speed is limited to ±{MAX_ANGULAR_RADPS:.2f} rad/s")
    if not 0 < duration <= MAX_MOTION_DURATION_S:
        raise ValueError(
            f"motion duration must be within (0, {MAX_MOTION_DURATION_S:.1f}] s"
        )


def require_safe_distance(distance: float, speed: float) -> None:
    if not 0 < distance <= MAX_DISTANCE_M:
        raise ValueError(f"distance must be within (0, {MAX_DISTANCE_M:.1f}] m")
    if not MIN_DISTANCE_SPEED_MPS <= speed <= MAX_DISTANCE_SPEED_MPS:
        raise ValueError(
            "distance-test speed must be within "
            f"[{MIN_DISTANCE_SPEED_MPS:.2f}, {MAX_DISTANCE_SPEED_MPS:.2f}] m/s"
        )


def require_safe_rotation(angle_deg: float, speed_radps: float) -> None:
    if not 0 < angle_deg <= MAX_ROTATION_ANGLE_DEG:
        raise ValueError(
            f"rotation angle must be within (0, {MAX_ROTATION_ANGLE_DEG:.0f}] deg"
        )
    if not MIN_ROTATION_SPEED_RADPS <= speed_radps <= MAX_ROTATION_SPEED_RADPS:
        raise ValueError(
            "rotation-test speed must be within "
            f"[{MIN_ROTATION_SPEED_RADPS:.2f}, "
            f"{MAX_ROTATION_SPEED_RADPS:.2f}] rad/s"
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
) -> list[tuple[float, StatusFrame]]:
    captured_rows: list[tuple[float, StatusFrame]] = []
    deadline = time.monotonic() + duration
    next_print = time.monotonic()
    while time.monotonic() < deadline:
        rows = capture.feed(port.read(timeout=0.05))
        captured_rows.extend(rows)
        now = time.monotonic()
        if rows and now >= next_print:
            _, status = rows[-1]
            print_status(status, capture.frame_rate)
            next_print = now + print_interval
    return captured_rows


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
    operation: Callable[
        [LinuxSerialPort, CaptureSession],
        Optional[dict],
    ],
) -> None:
    capture: Optional[CaptureSession] = None
    try:
        with LinuxSerialPort(args.port, args.baud) as port:
            parameters = {
                key: value
                for key, value in vars(args).items()
                if key not in {"func", "arm", "command", "port", "baud"}
            }
            capture = CaptureSession(
                command,
                args.port,
                args.baud,
                parameters,
            )
            print(f"Opened {args.port} at {args.baud} baud")
            print(f"Results: {capture.path}")
            try:
                details = operation(port, capture)
            except BaseException as exc:
                outcome = (
                    "interrupted"
                    if isinstance(exc, KeyboardInterrupt)
                    else "error"
                )
                capture.write_summary(
                    outcome,
                    error=f"{type(exc).__name__}: {exc}",
                )
                raise
            else:
                capture.write_summary("completed", details)
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


def command_distance(args: argparse.Namespace) -> None:
    if args.arm != DISTANCE_ARM_TEXT:
        raise SystemExit(f"Refusing distance test: pass --arm {DISTANCE_ARM_TEXT}")
    require_safe_distance(args.distance, args.speed)

    def operation(port: LinuxSerialPort, capture: CaptureSession) -> dict:
        send_stop_burst(port)
        drain_feedback(port, capture, 0.5, print_interval=0.5)
        if capture.latest is None:
            raise ValueError("no valid chassis feedback during preflight")
        if capture.latest.flag_stop != 0:
            raise ValueError(
                f"chassis reports stop={capture.latest.flag_stop}; "
                "release the motor enable/emergency stop before this test"
            )

        print(
            f"Distance test: target={args.distance:.3f} m, "
            f"speed={args.speed:.3f} m/s"
        )
        print(
            "This stops at encoder-integrated distance, not tape-measure distance. "
            "Keep a person at the physical emergency stop."
        )
        for remaining in (3, 2, 1):
            print(f"Starting in {remaining}...")
            time.sleep(1.0)

        frame = build_command_frame(args.speed, 0.0, 0.0)
        period = 1.0 / 20.0
        estimated_duration = args.distance / args.speed
        deadline = time.monotonic() + min(
            90.0,
            max(15.0, estimated_duration * 1.5 + 10.0),
        )
        next_send = time.monotonic()
        next_print = time.monotonic()
        last_feedback_wall = time.monotonic()
        last_frame_elapsed: Optional[float] = None
        integrated_distance = 0.0
        distance_at_stop_command = 0.0

        try:
            while integrated_distance < args.distance:
                now = time.monotonic()
                if now >= deadline:
                    raise TimeoutError(
                        "distance test timed out before reaching the target"
                    )
                if now >= next_send:
                    port.write(frame)
                    next_send = now + period

                rows = capture.feed(port.read(timeout=min(0.02, period)))
                if rows:
                    last_feedback_wall = time.monotonic()
                    for elapsed, status in rows:
                        if status.flag_stop != 0:
                            raise ValueError(
                                f"chassis changed to stop={status.flag_stop} "
                                "during the distance test"
                            )
                        if last_frame_elapsed is not None:
                            dt = elapsed - last_frame_elapsed
                            if 0 < dt <= 0.25:
                                integrated_distance += max(0.0, status.vx_mps) * dt
                        last_frame_elapsed = elapsed

                    now = time.monotonic()
                    if now >= next_print:
                        status = rows[-1][1]
                        print(
                            f"distance={integrated_distance:.3f}/"
                            f"{args.distance:.3f}m "
                            f"vx={status.vx_mps:+.3f} "
                            f"wz={status.wz_radps:+.3f}"
                        )
                        next_print = now + 0.5

                if time.monotonic() - last_feedback_wall > 0.5:
                    raise TimeoutError(
                        "lost chassis feedback for more than 0.5 s"
                    )
            distance_at_stop_command = integrated_distance
        finally:
            send_stop_burst(port)
            settling_rows = drain_feedback(
                port,
                capture,
                0.8,
                print_interval=0.4,
            )
            for elapsed, status in settling_rows:
                if last_frame_elapsed is not None:
                    dt = elapsed - last_frame_elapsed
                    if 0 < dt <= 0.25:
                        integrated_distance += max(
                            0.0,
                            status.vx_mps,
                        ) * dt
                last_frame_elapsed = elapsed
            print("Distance-test stop burst sent.")

        coast_distance = max(
            0.0,
            integrated_distance - distance_at_stop_command,
        )
        print(
            "Encoder-integrated target reached: "
            f"{distance_at_stop_command:.3f} m; "
            f"after settling: {integrated_distance:.3f} m "
            f"(coast {coast_distance:.3f} m). "
            "Measure the physical start-to-stop distance now."
        )
        return {
            "test_result": "TARGET_REACHED",
            "target_distance_m": args.distance,
            "command_speed_mps": args.speed,
            "encoder_distance_at_stop_command_m": round(
                distance_at_stop_command,
                6,
            ),
            "encoder_distance_after_settling_m": round(
                integrated_distance,
                6,
            ),
            "encoder_coast_distance_m": round(coast_distance, 6),
            "physical_distance_m": None,
        }

    with_port_and_capture(args, "distance", operation)


def command_rotate(args: argparse.Namespace) -> None:
    if args.arm != DISTANCE_ARM_TEXT:
        raise SystemExit(f"Refusing rotation test: pass --arm {DISTANCE_ARM_TEXT}")
    require_safe_rotation(args.angle, args.speed)
    direction_sign = 1.0 if args.direction == "left" else -1.0
    target_angle_rad = math.radians(args.angle)
    commanded_wz = direction_sign * args.speed

    def operation(port: LinuxSerialPort, capture: CaptureSession) -> dict:
        send_stop_burst(port)
        drain_feedback(port, capture, 0.5, print_interval=0.5)
        if capture.latest is None:
            raise ValueError("no valid chassis feedback during preflight")
        if capture.latest.flag_stop != 0:
            raise ValueError(
                f"chassis reports stop={capture.latest.flag_stop}; "
                "release the motor enable/emergency stop before this test"
            )

        print(
            f"Rotation test: direction={args.direction}, "
            f"target={args.angle:.1f} deg, speed={args.speed:.3f} rad/s"
        )
        print(
            "This stops at wheel-odometry-integrated angle, not measured physical "
            "heading. Keep a person at the physical emergency stop."
        )
        for remaining in (3, 2, 1):
            print(f"Starting in {remaining}...")
            time.sleep(1.0)

        frame = build_command_frame(0.0, 0.0, commanded_wz)
        period = 1.0 / 20.0
        estimated_duration = target_angle_rad / args.speed
        deadline = time.monotonic() + min(
            90.0,
            max(15.0, estimated_duration * 1.5 + 10.0),
        )
        next_send = time.monotonic()
        next_print = time.monotonic()
        last_feedback_wall = time.monotonic()
        last_frame_elapsed: Optional[float] = None
        integrated_angle_rad = 0.0
        integrated_gyro_angle_rad = 0.0
        angle_at_stop_command_rad = 0.0

        try:
            while integrated_angle_rad < target_angle_rad:
                now = time.monotonic()
                if now >= deadline:
                    raise TimeoutError(
                        "rotation test timed out before reaching the target angle"
                    )
                if now >= next_send:
                    port.write(frame)
                    next_send = now + period

                rows = capture.feed(port.read(timeout=min(0.02, period)))
                if rows:
                    last_feedback_wall = time.monotonic()
                    for elapsed, status in rows:
                        if status.flag_stop != 0:
                            raise ValueError(
                                f"chassis changed to stop={status.flag_stop} "
                                "during the rotation test"
                            )
                        if last_frame_elapsed is not None:
                            dt = elapsed - last_frame_elapsed
                            if 0 < dt <= 0.25:
                                signed_wz = direction_sign * status.wz_radps
                                integrated_angle_rad += max(0.0, signed_wz) * dt
                                signed_gyro = direction_sign * gyro_raw_to_radps(
                                    status.gyro_z_raw
                                )
                                integrated_gyro_angle_rad += max(
                                    0.0,
                                    signed_gyro,
                                ) * dt
                        last_frame_elapsed = elapsed

                    now = time.monotonic()
                    if now >= next_print:
                        status = rows[-1][1]
                        print(
                            f"angle={math.degrees(integrated_angle_rad):.1f}/"
                            f"{args.angle:.1f}deg "
                            f"wz={status.wz_radps:+.3f}"
                        )
                        next_print = now + 0.5

                if time.monotonic() - last_feedback_wall > 0.5:
                    raise TimeoutError(
                        "lost chassis feedback for more than 0.5 s"
                    )
            angle_at_stop_command_rad = integrated_angle_rad
        finally:
            send_stop_burst(port)
            settling_rows = drain_feedback(
                port,
                capture,
                0.8,
                print_interval=0.4,
            )
            for elapsed, status in settling_rows:
                if last_frame_elapsed is not None:
                    dt = elapsed - last_frame_elapsed
                    if 0 < dt <= 0.25:
                        signed_wz = direction_sign * status.wz_radps
                        integrated_angle_rad += max(0.0, signed_wz) * dt
                        signed_gyro = direction_sign * gyro_raw_to_radps(
                            status.gyro_z_raw
                        )
                        integrated_gyro_angle_rad += max(
                            0.0,
                            signed_gyro,
                        ) * dt
                last_frame_elapsed = elapsed
            print("Rotation-test stop burst sent.")

        coast_angle_rad = max(
            0.0,
            integrated_angle_rad - angle_at_stop_command_rad,
        )
        print(
            "Wheel-odometry target reached: "
            f"{math.degrees(angle_at_stop_command_rad):.1f} deg; "
            f"after settling: {math.degrees(integrated_angle_rad):.1f} deg "
            f"(coast {math.degrees(coast_angle_rad):.1f} deg). "
            "Measure the physical final heading now."
        )
        return {
            "test_result": "TARGET_REACHED",
            "direction": args.direction,
            "target_angle_deg": args.angle,
            "command_speed_radps": args.speed,
            "wheel_angle_at_stop_command_deg": round(
                math.degrees(angle_at_stop_command_rad),
                6,
            ),
            "wheel_angle_after_settling_deg": round(
                math.degrees(integrated_angle_rad),
                6,
            ),
            "wheel_coast_angle_deg": round(
                math.degrees(coast_angle_rad),
                6,
            ),
            "gyro_angle_after_settling_deg": round(
                math.degrees(integrated_gyro_angle_rad),
                6,
            ),
            "physical_angle_deg": None,
        }

    with_port_and_capture(args, "rotate", operation)


def command_failsafe(args: argparse.Namespace) -> None:
    if args.arm != FAILSAFE_ARM_TEXT:
        raise SystemExit(f"Refusing failsafe test: pass --arm {FAILSAFE_ARM_TEXT}")

    def operation(port: LinuxSerialPort, capture: CaptureSession) -> dict:
        drive_duration = 2.0
        silence_duration = 2.0
        moving_vx_threshold = 0.015
        stopped_vx_threshold = 0.01
        stopped_wz_threshold = 0.02
        required_stopped_frames = 3
        silence_started = 0.0
        silence_capture_started = 0.0
        stopped_after: Optional[float] = None
        stop_candidate_after: Optional[float] = None
        stopped_frame_count = 0
        motion_confirmed = False
        try:
            print(f"Sending +0.03 m/s for {drive_duration:.1f} s...")
            run_velocity(port, capture, 0.03, 0.0, 0.0, drive_duration)
            moving_status = capture.latest
            motion_confirmed = (
                moving_status is not None
                and moving_status.flag_stop == 0
                and abs(moving_status.vx_mps) >= moving_vx_threshold
            )
            if moving_status is None:
                print("PRECONDITION FAILED: no feedback before command silence.")
            else:
                print(
                    "Pre-silence feedback: "
                    f"stop={moving_status.flag_stop} "
                    f"vx={moving_status.vx_mps:+.3f} "
                    f"wz={moving_status.wz_radps:+.3f}"
                )
            print(
                f"COMMAND SILENCE for {silence_duration:.1f} s; "
                "no stop frame is being sent."
            )
            silence_started = time.monotonic()
            silence_capture_started = capture.elapsed
            deadline = silence_started + silence_duration
            next_print = silence_started
            while time.monotonic() < deadline:
                rows = capture.feed(port.read(timeout=0.05))
                for elapsed, status in rows:
                    sample_after = max(0.0, elapsed - silence_capture_started)
                    is_stopped = (
                        abs(status.vx_mps) < stopped_vx_threshold
                        and abs(status.wz_radps) < stopped_wz_threshold
                    )
                    if is_stopped:
                        if stopped_frame_count == 0:
                            stop_candidate_after = sample_after
                        stopped_frame_count += 1
                        if (
                            stopped_after is None
                            and stopped_frame_count >= required_stopped_frames
                        ):
                            stopped_after = stop_candidate_after
                    else:
                        stopped_frame_count = 0
                        stop_candidate_after = None
                now = time.monotonic()
                if rows and now >= next_print:
                    print_status(rows[-1][1], capture.frame_rate)
                    next_print = now + 0.25
        finally:
            send_stop_burst(port)
            drain_feedback(port, capture, 0.5)
            print("Recovery stop burst sent.")

        if not motion_confirmed:
            test_result = "INCONCLUSIVE"
            print(
                "INCONCLUSIVE: the chassis was not confirmed moving before "
                f"command silence (requires |vx| >= {moving_vx_threshold:.3f} m/s "
                "with stop=0)."
            )
        elif stopped_after is None:
            test_result = "FAIL"
            print(
                "FAIL: after confirmed motion, feedback did not remain below the "
                f"stop threshold for {required_stopped_frames} consecutive frames "
                f"during the {silence_duration:.1f} s command silence."
            )
        else:
            print(
                "Observed stable near-zero feedback "
                f"after {stopped_after:.3f} s."
            )
            if stopped_after <= 1.2:
                test_result = "PASS_CANDIDATE"
                print("PASS candidate: verify the wheel video before accepting.")
            else:
                test_result = "FAIL"
                print("FAIL: stop response exceeded the 1.2 s acceptance threshold.")
        return {
            "test_result": test_result,
            "motion_confirmed_before_silence": motion_confirmed,
            "commanded_speed_mps": 0.03,
            "command_duration_s": drive_duration,
            "command_silence_duration_s": silence_duration,
            "stable_stop_after_s": (
                None if stopped_after is None else round(stopped_after, 6)
            ),
            "acceptance_threshold_s": 1.2,
            "video_review_required": True,
        }

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

    distance = subparsers.add_parser(
        "distance",
        help="drive straight until encoder-integrated distance reaches a target",
    )
    add_serial_arguments(distance)
    distance.add_argument("--distance", type=float, default=3.0)
    distance.add_argument("--speed", type=float, default=0.10)
    distance.add_argument("--arm", default="")
    distance.set_defaults(func=command_distance)

    rotate = subparsers.add_parser(
        "rotate",
        help="rotate until wheel-odometry-integrated yaw reaches a target",
    )
    add_serial_arguments(rotate)
    rotate.add_argument("--angle", type=float, default=360.0)
    rotate.add_argument("--speed", type=float, default=0.15)
    rotate.add_argument(
        "--direction",
        choices=("left", "right"),
        default="left",
    )
    rotate.add_argument("--arm", default="")
    rotate.set_defaults(func=command_rotate)

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
