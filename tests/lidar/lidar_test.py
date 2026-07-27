#!/usr/bin/env python3
"""Bench tests for the YDLIDAR X3 Pro ROS 2 integration."""

from __future__ import annotations

import argparse
from datetime import datetime
import glob
import json
import math
from pathlib import Path
import statistics
import subprocess
import sys
import time


def command_output(command: list[str]) -> str:
    result = subprocess.run(
        command,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return result.stdout.strip()


def show_ports(_args: argparse.Namespace) -> int:
    devices = sorted(
        glob.glob("/dev/ttyUSB*")
        + glob.glob("/dev/ttyACM*")
        + glob.glob("/dev/ydlidar")
    )
    if not devices:
        print("No ttyUSB, ttyACM or /dev/ydlidar device found.")
        return 1

    for device in devices:
        print(f"\n[{device}]")
        print(command_output(["ls", "-l", device]))
        properties = command_output(
            ["udevadm", "info", "--query=property", f"--name={device}"]
        )
        wanted = (
            "ID_VENDOR_ID=",
            "ID_MODEL_ID=",
            "ID_SERIAL=",
            "ID_SERIAL_SHORT=",
            "ID_PATH=",
        )
        for line in properties.splitlines():
            if line.startswith(wanted):
                print(line)

    for directory in ("/dev/serial/by-id", "/dev/serial/by-path"):
        if Path(directory).is_dir():
            print(f"\n[{directory}]")
            print(command_output(["ls", "-l", directory]))
    return 0


class ScanMonitor:
    def __init__(self, topic: str):
        try:
            import rclpy
            from rclpy.node import Node
            from rclpy.qos import qos_profile_sensor_data
            from sensor_msgs.msg import LaserScan
        except ImportError as error:
            raise RuntimeError(
                "ROS 2 Python packages are unavailable. Source "
                "/opt/ros/humble/setup.bash and install/setup.bash first."
            ) from error

        self.rclpy = rclpy
        self.node = Node("spore_patrol_lidar_test")
        self.receive_times: list[float] = []
        self.frames: list[str] = []
        self.point_counts: list[int] = []
        self.valid_counts: list[int] = []
        self.scan_times: list[float] = []
        self.angle_increments: list[float] = []
        self.minimum_ranges: list[float] = []
        self.maximum_ranges: list[float] = []
        self.subscription = self.node.create_subscription(
            LaserScan,
            topic,
            self.callback,
            qos_profile_sensor_data,
        )

    def callback(self, message) -> None:
        finite = [
            value
            for value in message.ranges
            if math.isfinite(value)
            and message.range_min <= value <= message.range_max
        ]
        self.receive_times.append(time.monotonic())
        self.frames.append(message.header.frame_id)
        self.point_counts.append(len(message.ranges))
        self.valid_counts.append(len(finite))
        self.scan_times.append(float(message.scan_time))
        self.angle_increments.append(float(message.angle_increment))
        if finite:
            self.minimum_ranges.append(min(finite))
            self.maximum_ranges.append(max(finite))

    def run(self, duration: float) -> None:
        deadline = time.monotonic() + duration
        while time.monotonic() < deadline:
            self.rclpy.spin_once(self.node, timeout_sec=0.2)

    def close(self) -> None:
        self.node.destroy_node()

    def summary(self, duration: float, topic: str) -> dict:
        scan_count = len(self.receive_times)
        receive_hz = 0.0
        if scan_count >= 2:
            interval = self.receive_times[-1] - self.receive_times[0]
            if interval > 0:
                receive_hz = (scan_count - 1) / interval

        median_points = (
            statistics.median(self.point_counts) if self.point_counts else 0
        )
        median_valid = (
            statistics.median(self.valid_counts) if self.valid_counts else 0
        )
        valid_ratio = median_valid / median_points if median_points else 0.0
        median_scan_time = (
            statistics.median(self.scan_times) if self.scan_times else 0.0
        )
        reported_hz = 1.0 / median_scan_time if median_scan_time > 0 else 0.0
        angle_increment_deg = (
            math.degrees(statistics.median(self.angle_increments))
            if self.angle_increments
            else 0.0
        )
        frame_ids = sorted(set(self.frames))

        checks = {
            "received_scans": scan_count > 0,
            "frame_is_laser_link": frame_ids == ["laser_link"],
            "frequency_plausible_3_to_12_hz": 3.0 <= receive_hz <= 12.0,
            "point_count_plausible_300_to_1200": 300 <= median_points <= 1200,
        }

        return {
            "topic": topic,
            "requested_duration_s": duration,
            "scan_count": scan_count,
            "receive_frequency_hz": round(receive_hz, 3),
            "reported_frequency_hz": round(reported_hz, 3),
            "frame_ids": frame_ids,
            "median_point_count": median_points,
            "median_valid_point_count": median_valid,
            "median_valid_ratio": round(valid_ratio, 4),
            "median_angle_increment_deg": round(angle_increment_deg, 5),
            "minimum_observed_range_m": (
                round(min(self.minimum_ranges), 4)
                if self.minimum_ranges
                else None
            ),
            "maximum_observed_range_m": (
                round(max(self.maximum_ranges), 4)
                if self.maximum_ranges
                else None
            ),
            "checks": checks,
            "pass": all(checks.values()),
        }


def monitor_scan(args: argparse.Namespace) -> int:
    try:
        import rclpy
    except ImportError:
        print(
            "rclpy is unavailable. Source /opt/ros/humble/setup.bash and "
            "install/setup.bash first.",
            file=sys.stderr,
        )
        return 2

    rclpy.init()
    monitor = ScanMonitor(args.topic)
    try:
        print(f"Monitoring {args.topic} for {args.duration:.1f} seconds...")
        monitor.run(args.duration)
        summary = monitor.summary(args.duration, args.topic)
    finally:
        monitor.close()
        rclpy.shutdown()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    result_directory = Path(args.results_dir) / f"{timestamp}_lidar_scan"
    result_directory.mkdir(parents=True, exist_ok=False)
    result_path = result_directory / "summary.json"
    result_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Result: {result_path.resolve()}")
    return 0 if summary["pass"] else 1


def show_orientation(_args: argparse.Namespace) -> int:
    print(
        "Place one box at the robot's front-left corner.\n"
        "Expected in laser_link: x > 0 and y > 0.\n"
        "- Front-left appears rear-right: toggle reversion.\n"
        "- Front-left appears front-right: toggle inverted.\n"
        "- Front-left appears rear-left: toggle both reversion and inverted.\n"
        "- Correct side but constant angular offset: change laser_joint yaw."
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    ports_parser = subparsers.add_parser(
        "ports",
        help="List candidate serial devices and stable USB identifiers.",
    )
    ports_parser.set_defaults(function=show_ports)

    scan_parser = subparsers.add_parser(
        "scan",
        help="Measure ROS LaserScan frequency, point count and basic validity.",
    )
    scan_parser.add_argument("--topic", default="/scan")
    scan_parser.add_argument("--duration", type=float, default=10.0)
    scan_parser.add_argument("--results-dir", default="tests/results")
    scan_parser.set_defaults(function=monitor_scan)

    orientation_parser = subparsers.add_parser(
        "orientation",
        help="Print the front-left-box orientation procedure.",
    )
    orientation_parser.set_defaults(function=show_orientation)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if getattr(args, "duration", 1.0) <= 0:
        parser.error("--duration must be positive")
    return args.function(args)


if __name__ == "__main__":
    raise SystemExit(main())
