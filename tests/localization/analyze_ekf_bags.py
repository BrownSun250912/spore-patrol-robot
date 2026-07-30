#!/usr/bin/env python3
"""Analyze wheel odometry, ICM20948 and EKF output in ROS 2 bags."""

import argparse
import bisect
import json
import math
from pathlib import Path
import statistics

from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
import rosbag2_py
from rclpy.serialization import deserialize_message
from sensor_msgs.msg import Imu


def yaw_from_quaternion(q):
    return math.atan2(
        2.0 * (q.w * q.z + q.x * q.y),
        1.0 - 2.0 * (q.y * q.y + q.z * q.z),
    )


def read_bag(path):
    reader = rosbag2_py.SequentialReader()
    reader.open(
        rosbag2_py.StorageOptions(uri=str(path), storage_id="sqlite3"),
        rosbag2_py.ConverterOptions(
            input_serialization_format="cdr",
            output_serialization_format="cdr",
        ),
    )
    available = {
        item.name: item.type for item in reader.get_all_topics_and_types()
    }
    required_types = {
        "/odom": ("nav_msgs/msg/Odometry", Odometry),
        "/odometry/filtered": ("nav_msgs/msg/Odometry", Odometry),
        "/imu/data_raw": ("sensor_msgs/msg/Imu", Imu),
        "/imu/data_calibrated": ("sensor_msgs/msg/Imu", Imu),
        "/cmd_vel": ("geometry_msgs/msg/Twist", Twist),
    }
    rows = {topic: [] for topic in required_types}
    first_time = None
    last_time = None

    while reader.has_next():
        topic, serialized, timestamp_ns = reader.read_next()
        if first_time is None:
            first_time = timestamp_ns
        last_time = timestamp_ns
        if topic not in required_types:
            continue
        expected_type, message_type = required_types[topic]
        if available.get(topic) != expected_type:
            continue
        message = deserialize_message(serialized, message_type)
        t = timestamp_ns * 1e-9
        if topic in ("/odom", "/odometry/filtered"):
            rows[topic].append(
                {
                    "t": t,
                    "x": message.pose.pose.position.x,
                    "y": message.pose.pose.position.y,
                    "yaw": yaw_from_quaternion(
                        message.pose.pose.orientation
                    ),
                    "vx": message.twist.twist.linear.x,
                    "vy": message.twist.twist.linear.y,
                    "wz": message.twist.twist.angular.z,
                }
            )
        elif topic in ("/imu/data_raw", "/imu/data_calibrated"):
            rows[topic].append(
                {
                    "t": t,
                    "wz": message.angular_velocity.z,
                    "ax": message.linear_acceleration.x,
                    "ay": message.linear_acceleration.y,
                    "az": message.linear_acceleration.z,
                }
            )
        else:
            rows[topic].append(
                {
                    "t": t,
                    "vx": message.linear.x,
                    "wz": message.angular.z,
                }
            )

    for topic in ("/odom", "/odometry/filtered"):
        unwrap_yaw(rows[topic])

    return {
        "path": str(path),
        "duration_s": (
            (last_time - first_time) * 1e-9
            if first_time is not None and last_time is not None
            else 0.0
        ),
        "available_topics": available,
        "rows": rows,
    }


def unwrap_yaw(rows):
    if not rows:
        return
    offset = 0.0
    previous = rows[0]["yaw"]
    rows[0]["yaw_unwrapped"] = previous
    for row in rows[1:]:
        current = row["yaw"]
        delta = current - previous
        if delta > math.pi:
            offset -= 2.0 * math.pi
        elif delta < -math.pi:
            offset += 2.0 * math.pi
        row["yaw_unwrapped"] = current + offset
        previous = current


def classify_command(row):
    if row["wz"] >= 0.02:
        return "rotate_left"
    if row["wz"] <= -0.02:
        return "rotate_right"
    if abs(row["vx"]) >= 0.01:
        return "translate"
    return None


def command_intervals(rows, maximum_gap_s=0.5):
    active = []
    for row in rows:
        mode = classify_command(row)
        if mode is not None:
            active.append((row["t"], mode, row["vx"], row["wz"]))
    if not active:
        return []

    intervals = []
    start_t, mode, vx, wz = active[0]
    end_t = start_t
    vx_values = [vx]
    wz_values = [wz]
    for t, current_mode, current_vx, current_wz in active[1:]:
        if current_mode != mode or t - end_t > maximum_gap_s:
            intervals.append(
                {
                    "mode": mode,
                    "command_start_s": start_t,
                    "command_end_s": end_t,
                    "command_duration_s": end_t - start_t,
                    "mean_command_vx": statistics.fmean(vx_values),
                    "mean_command_wz": statistics.fmean(wz_values),
                }
            )
            start_t = t
            mode = current_mode
            vx_values = []
            wz_values = []
        end_t = t
        vx_values.append(current_vx)
        wz_values.append(current_wz)
    intervals.append(
        {
            "mode": mode,
            "command_start_s": start_t,
            "command_end_s": end_t,
            "command_duration_s": end_t - start_t,
            "mean_command_vx": statistics.fmean(vx_values),
            "mean_command_wz": statistics.fmean(wz_values),
        }
    )
    return intervals


def nearest_index(rows, timestamp):
    times = [row["t"] for row in rows]
    index = bisect.bisect_left(times, timestamp)
    if index <= 0:
        return 0
    if index >= len(rows):
        return len(rows) - 1
    before = index - 1
    if timestamp - times[before] <= times[index] - timestamp:
        return before
    return index


def series_metrics(rows, start_t, end_t):
    if len(rows) < 2:
        return None
    start_index = nearest_index(rows, start_t)
    end_index = nearest_index(rows, end_t)
    if end_index <= start_index:
        return None
    selected = rows[start_index:end_index + 1]
    start = selected[0]
    end = selected[-1]
    path_length = 0.0
    for previous, current in zip(selected, selected[1:]):
        path_length += math.hypot(
            current["x"] - previous["x"],
            current["y"] - previous["y"],
        )
    return {
        "start_time_s": start["t"],
        "end_time_s": end["t"],
        "duration_s": end["t"] - start["t"],
        "delta_x_m": end["x"] - start["x"],
        "delta_y_m": end["y"] - start["y"],
        "net_displacement_m": math.hypot(
            end["x"] - start["x"],
            end["y"] - start["y"],
        ),
        "path_length_m": path_length,
        "yaw_change_deg": math.degrees(
            end["yaw_unwrapped"] - start["yaw_unwrapped"]
        ),
    }


def integrate_imu(rows, start_t, end_t, bias):
    selected = [
        row for row in rows if start_t <= row["t"] <= end_t
    ]
    if len(selected) < 2:
        return None
    angle = 0.0
    for previous, current in zip(selected, selected[1:]):
        delta_t = current["t"] - previous["t"]
        angle += (
            0.5
            * ((previous["wz"] - bias) + (current["wz"] - bias))
            * delta_t
        )
    return {
        "duration_s": selected[-1]["t"] - selected[0]["t"],
        "bias_corrected_angle_deg": math.degrees(angle),
        "mean_wz_rad_s": statistics.fmean(
            row["wz"] for row in selected
        ),
    }


def static_metrics(bag):
    imu = bag["rows"]["/imu/data_raw"]
    calibrated_imu = bag["rows"]["/imu/data_calibrated"]
    raw = bag["rows"]["/odom"]
    filtered = bag["rows"]["/odometry/filtered"]
    wz_values = [row["wz"] for row in imu]
    result = {
        "duration_s": bag["duration_s"],
        "sample_counts": {
            topic: len(rows) for topic, rows in bag["rows"].items()
        },
        "imu_wz_mean_rad_s": statistics.fmean(wz_values),
        "imu_wz_median_rad_s": statistics.median(wz_values),
        "imu_wz_stddev_rad_s": statistics.pstdev(wz_values),
    }
    if calibrated_imu:
        calibrated_wz = [row["wz"] for row in calibrated_imu]
        result["calibrated_imu_wz_mean_rad_s"] = statistics.fmean(
            calibrated_wz
        )
    if raw:
        result["raw_odom_whole_bag"] = series_metrics(
            raw, raw[0]["t"], raw[-1]["t"]
        )
    if filtered:
        result["filtered_odom_whole_bag"] = series_metrics(
            filtered, filtered[0]["t"], filtered[-1]["t"]
        )
    return result


def analyze_motion_bag(bag, imu_bias):
    result = {
        "duration_s": bag["duration_s"],
        "sample_counts": {
            topic: len(rows) for topic, rows in bag["rows"].items()
        },
        "intervals": [],
    }
    calibrated_imu = bag["rows"]["/imu/data_calibrated"]
    imu_rows = calibrated_imu or bag["rows"]["/imu/data_raw"]
    imu_bias_to_remove = 0.0 if calibrated_imu else imu_bias
    result["imu_source"] = (
        "/imu/data_calibrated" if calibrated_imu else "/imu/data_raw"
    )
    intervals = command_intervals(bag["rows"]["/cmd_vel"])
    bag_start = min(
        rows[0]["t"] for rows in bag["rows"].values() if rows
    )
    for index, interval in enumerate(intervals, start=1):
        analysis_start = interval["command_start_s"] - 0.25
        analysis_end = interval["command_end_s"] + 1.0
        item = dict(interval)
        item["index"] = index
        item["relative_start_s"] = (
            interval["command_start_s"] - bag_start
        )
        item["relative_end_s"] = interval["command_end_s"] - bag_start
        item["raw_odom"] = series_metrics(
            bag["rows"]["/odom"], analysis_start, analysis_end
        )
        item["filtered_odom"] = series_metrics(
            bag["rows"]["/odometry/filtered"],
            analysis_start,
            analysis_end,
        )
        item["imu"] = integrate_imu(
            imu_rows,
            analysis_start,
            analysis_end,
            imu_bias_to_remove,
        )
        result["intervals"].append(item)
    result["mode_windows"] = []
    for mode in ("rotate_left", "rotate_right", "translate"):
        matching = [
            row
            for row in bag["rows"]["/cmd_vel"]
            if classify_command(row) == mode
        ]
        if not matching:
            continue
        analysis_start = matching[0]["t"] - 0.25
        analysis_end = matching[-1]["t"] + 1.0
        result["mode_windows"].append(
            {
                "mode": mode,
                "command_start_s": matching[0]["t"],
                "command_end_s": matching[-1]["t"],
                "relative_start_s": matching[0]["t"] - bag_start,
                "relative_end_s": matching[-1]["t"] - bag_start,
                "window_duration_s": matching[-1]["t"] - matching[0]["t"],
                "active_command_samples": len(matching),
                "mean_command_vx": statistics.fmean(
                    row["vx"] for row in matching
                ),
                "mean_command_wz": statistics.fmean(
                    row["wz"] for row in matching
                ),
                "raw_odom": series_metrics(
                    bag["rows"]["/odom"], analysis_start, analysis_end
                ),
                "filtered_odom": series_metrics(
                    bag["rows"]["/odometry/filtered"],
                    analysis_start,
                    analysis_end,
                ),
                "imu": integrate_imu(
                    imu_rows,
                    analysis_start,
                    analysis_end,
                    imu_bias_to_remove,
                ),
            }
        )
    return result


def relative_trajectory(rows):
    if not rows:
        return [], []
    x0 = rows[0]["x"]
    y0 = rows[0]["y"]
    return (
        [row["x"] - x0 for row in rows],
        [row["y"] - y0 for row in rows],
    )


def create_plot(bags, output_path):
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return False
    names = list(bags)
    figure, axes = plt.subplots(2, 2, figsize=(11, 9))
    for axis, name in zip(axes.flat, names, strict=False):
        bag = bags[name]
        for topic, label, color in (
            ("/odom", "raw wheel odom", "#d95f02"),
            ("/odometry/filtered", "wheel + IMU EKF", "#1b9e77"),
        ):
            x_values, y_values = relative_trajectory(bag["rows"][topic])
            axis.plot(x_values, y_values, label=label, color=color)
        axis.set_title(name)
        axis.set_xlabel("relative x (m)")
        axis.set_ylabel("relative y (m)")
        axis.axis("equal")
        axis.grid(True, alpha=0.3)
        axis.legend()
    for axis in axes.flat[len(names):]:
        axis.set_visible(False)
    figure.tight_layout()
    figure.savefig(output_path, dpi=160)
    plt.close(figure)
    return True


def format_metric(value, digits=3):
    if value is None:
        return "n/a"
    return f"{value:.{digits}f}"


def write_report(summary, output_path, expected_angles):
    static = summary["static"]
    lines = [
        "# ICM20948 and EKF test report",
        "",
        "## Static test",
        "",
        f"- Bag duration: {static['duration_s']:.1f} s",
        (
            "- IMU yaw-rate mean: "
            f"{static['imu_wz_mean_rad_s']:.6f} rad/s"
        ),
        (
            "- IMU yaw-rate standard deviation: "
            f"{static['imu_wz_stddev_rad_s']:.6f} rad/s"
        ),
    ]
    for key, label in (
        ("raw_odom_whole_bag", "Raw odometry"),
        ("filtered_odom_whole_bag", "Filtered odometry"),
    ):
        metric = static.get(key)
        if metric:
            lines.append(
                f"- {label}: net {metric['net_displacement_m']:.3f} m, "
                f"yaw drift {metric['yaw_change_deg']:.2f} deg"
            )

    for name in ("straight", "left", "right"):
        if name not in summary:
            continue
        section = summary[name]
        lines.extend(["", f"## {name.title()} test", ""])
        if not section["mode_windows"]:
            lines.append("- No non-zero `/cmd_vel` interval was found.")
            continue
        for interval in section["mode_windows"]:
            raw = interval.get("raw_odom")
            filtered = interval.get("filtered_odom")
            imu = interval.get("imu")
            lines.append(
                "### Whole command window: "
                f"{interval['mode']} "
                f"({interval['relative_start_s']:.1f}-"
                f"{interval['relative_end_s']:.1f} s)"
            )
            lines.append("")
            lines.append(
                f"- Command: vx={interval['mean_command_vx']:.3f} m/s, "
                f"wz={interval['mean_command_wz']:.3f} rad/s, "
                f"{interval['active_command_samples']} active samples"
            )
            if raw:
                lines.append(
                    "- Raw odometry: "
                    f"path {raw['path_length_m']:.3f} m, "
                    f"net {raw['net_displacement_m']:.3f} m, "
                    f"yaw {raw['yaw_change_deg']:.2f} deg"
                )
            if filtered:
                lines.append(
                    "- Filtered odometry: "
                    f"path {filtered['path_length_m']:.3f} m, "
                    f"net {filtered['net_displacement_m']:.3f} m, "
                    f"yaw {filtered['yaw_change_deg']:.2f} deg"
                )
            if imu:
                lines.append(
                    "- Calibrated/bias-corrected IMU yaw integral: "
                    f"{imu['bias_corrected_angle_deg']:.2f} deg"
                )
            expected_magnitude = expected_angles.get(interval["mode"])
            if expected_magnitude is not None and filtered:
                expected_signed = (
                    expected_magnitude
                    if interval["mode"] == "rotate_left"
                    else -expected_magnitude
                )
                error = filtered["yaw_change_deg"] - expected_signed
                magnitude_error_percent = (
                    (abs(filtered["yaw_change_deg"]) - expected_magnitude)
                    / expected_magnitude
                    * 100.0
                )
                lines.append(
                    f"- Expected {expected_signed:.1f} deg: signed error "
                    f"{error:+.2f} deg, magnitude error "
                    f"{magnitude_error_percent:+.2f}%"
                )

    physical = summary.get("physical_measurements", {})
    if physical:
        lines.extend(["", "## Physical measurements", ""])
        for key, value in physical.items():
            lines.append(f"- {key}: {value}")
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("--static", required=True, type=Path)
    parser.add_argument("--straight", required=True, type=Path)
    parser.add_argument("--left", required=True, type=Path)
    parser.add_argument("--right", type=Path)
    parser.add_argument("--left-angle", type=float)
    parser.add_argument("--right-angle", type=float)
    parser.add_argument("--straight-distance", type=float)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main():
    args = parse_arguments()
    bags = {
        "static": read_bag(args.static),
        "straight": read_bag(args.straight),
        "left": read_bag(args.left),
    }
    if args.right is not None:
        bags["right"] = read_bag(args.right)
    static = static_metrics(bags["static"])
    imu_bias = static["imu_wz_mean_rad_s"]
    summary = {
        "static": static,
        "straight": analyze_motion_bag(bags["straight"], imu_bias),
        "left": analyze_motion_bag(bags["left"], imu_bias),
    }
    if "right" in bags:
        summary["right"] = analyze_motion_bag(bags["right"], imu_bias)
    expected_angles = {
        key: value
        for key, value in (
            ("rotate_left", args.left_angle),
            ("rotate_right", args.right_angle),
        )
        if value is not None
    }
    if args.straight_distance is not None:
        summary["physical_measurements"] = {
            "straight_distance_m": args.straight_distance
        }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_report(
        summary,
        args.output / "report.md",
        expected_angles,
    )
    plotted = create_plot(bags, args.output / "trajectories.png")
    print(f"Wrote {args.output / 'summary.json'}")
    print(f"Wrote {args.output / 'report.md'}")
    if plotted:
        print(f"Wrote {args.output / 'trajectories.png'}")
    else:
        print("matplotlib is unavailable; skipped trajectory plot")


if __name__ == "__main__":
    main()
