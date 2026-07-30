#!/usr/bin/env python3
"""Stationary startup calibration for IMU angular-velocity bias."""

from copy import deepcopy
import math

from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Imu
from std_srvs.srv import Trigger


class GyroBiasEstimator:
    """Estimate a constant three-axis gyro bias from stationary samples."""

    def __init__(
        self,
        calibration_duration_s,
        minimum_samples,
        motion_threshold_rad_s,
    ):
        if calibration_duration_s <= 0.0:
            raise ValueError("calibration_duration_s must be positive")
        if minimum_samples < 1:
            raise ValueError("minimum_samples must be positive")
        if motion_threshold_rad_s <= 0.0:
            raise ValueError("motion_threshold_rad_s must be positive")
        self.calibration_duration_s = calibration_duration_s
        self.minimum_samples = minimum_samples
        self.motion_threshold_rad_s = motion_threshold_rad_s
        self.reset()

    def reset(self):
        self.start_time_s = None
        self.last_time_s = None
        self.sample_count = 0
        self.sums = [0.0, 0.0, 0.0]
        self.bias = [0.0, 0.0, 0.0]
        self.ready = False

    @property
    def elapsed_s(self):
        if self.start_time_s is None or self.last_time_s is None:
            return 0.0
        return max(0.0, self.last_time_s - self.start_time_s)

    def add_sample(self, time_s, x, y, z):
        """Add one sample; return a state string for node diagnostics."""
        if self.ready:
            return "ready"
        if self.last_time_s is not None and time_s < self.last_time_s:
            self.reset()
            return "time_reset"

        angular_speed = math.sqrt(x * x + y * y + z * z)
        if angular_speed > self.motion_threshold_rad_s:
            had_samples = self.sample_count > 0
            self.reset()
            return "motion_reset" if had_samples else "moving"

        if self.start_time_s is None:
            self.start_time_s = time_s
        self.last_time_s = time_s
        self.sample_count += 1
        self.sums[0] += x
        self.sums[1] += y
        self.sums[2] += z

        if (
            self.elapsed_s >= self.calibration_duration_s
            and self.sample_count >= self.minimum_samples
        ):
            self.bias = [
                total / self.sample_count for total in self.sums
            ]
            self.ready = True
            return "completed"
        return "collecting"


class ImuBiasCalibrator(Node):
    """Publish a bias-corrected IMU after a stationary startup window."""

    def __init__(self):
        super().__init__("imu_bias_calibrator")
        self.declare_parameter("input_topic", "/imu/data_raw")
        self.declare_parameter("output_topic", "/imu/data_calibrated")
        self.declare_parameter("calibration_duration", 10.0)
        self.declare_parameter("minimum_samples", 100)
        self.declare_parameter("motion_threshold", 0.03)

        input_topic = (
            self.get_parameter("input_topic")
            .get_parameter_value()
            .string_value
        )
        output_topic = (
            self.get_parameter("output_topic")
            .get_parameter_value()
            .string_value
        )
        calibration_duration = (
            self.get_parameter("calibration_duration")
            .get_parameter_value()
            .double_value
        )
        minimum_samples = (
            self.get_parameter("minimum_samples")
            .get_parameter_value()
            .integer_value
        )
        motion_threshold = (
            self.get_parameter("motion_threshold")
            .get_parameter_value()
            .double_value
        )

        self.estimator = GyroBiasEstimator(
            calibration_duration,
            minimum_samples,
            motion_threshold,
        )
        self.output_publisher = self.create_publisher(
            Imu, output_topic, qos_profile_sensor_data
        )
        self.diagnostic_publisher = self.create_publisher(
            DiagnosticArray, "/diagnostics", 10
        )
        self.subscription = self.create_subscription(
            Imu,
            input_topic,
            self.imu_callback,
            qos_profile_sensor_data,
        )
        self.recalibrate_service = self.create_service(
            Trigger,
            "~/recalibrate",
            self.recalibrate_callback,
        )
        self.create_timer(1.0, self.publish_diagnostic)
        self.last_motion_warning_ns = 0

        self.get_logger().warn(
            "Keep the robot completely stationary for "
            f"{calibration_duration:.1f} s; calibrated IMU output is held "
            "until gyro bias calibration finishes."
        )

    def imu_callback(self, message):
        now = self.get_clock().now()
        state = self.estimator.add_sample(
            now.nanoseconds * 1e-9,
            message.angular_velocity.x,
            message.angular_velocity.y,
            message.angular_velocity.z,
        )
        if state in ("motion_reset", "moving"):
            if now.nanoseconds - self.last_motion_warning_ns >= 2_000_000_000:
                self.get_logger().warn(
                    "IMU motion detected during calibration; keep the robot "
                    "stationary. The calibration window has been restarted."
                )
                self.last_motion_warning_ns = now.nanoseconds
            return
        if state == "time_reset":
            self.get_logger().warn(
                "Clock moved backwards; IMU bias calibration restarted."
            )
            return
        if state == "completed":
            bias = self.estimator.bias
            self.get_logger().info(
                "Gyro bias calibration complete with "
                f"{self.estimator.sample_count} samples: "
                f"x={bias[0]:+.7f}, y={bias[1]:+.7f}, "
                f"z={bias[2]:+.7f} rad/s"
            )
        if not self.estimator.ready:
            return

        calibrated = deepcopy(message)
        calibrated.angular_velocity.x -= self.estimator.bias[0]
        calibrated.angular_velocity.y -= self.estimator.bias[1]
        calibrated.angular_velocity.z -= self.estimator.bias[2]
        self.output_publisher.publish(calibrated)

    def recalibrate_callback(self, request, response):
        del request
        self.estimator.reset()
        response.success = True
        response.message = (
            "IMU gyro bias calibration restarted; keep robot stationary."
        )
        self.get_logger().warn(response.message)
        return response

    def publish_diagnostic(self):
        array = DiagnosticArray()
        array.header.stamp = self.get_clock().now().to_msg()
        status = DiagnosticStatus()
        status.name = "spore_patrol_localization: IMU gyro bias"
        status.hardware_id = "ICM20948@STM32"
        if self.estimator.ready:
            status.level = DiagnosticStatus.OK
            status.message = "calibrated"
        else:
            status.level = DiagnosticStatus.WARN
            status.message = "keep robot stationary: calibrating"
        values = {
            "ready": str(self.estimator.ready).lower(),
            "samples": str(self.estimator.sample_count),
            "elapsed_s": f"{self.estimator.elapsed_s:.2f}",
            "bias_x_rad_s": f"{self.estimator.bias[0]:+.8f}",
            "bias_y_rad_s": f"{self.estimator.bias[1]:+.8f}",
            "bias_z_rad_s": f"{self.estimator.bias[2]:+.8f}",
            "motion_threshold_rad_s": (
                f"{self.estimator.motion_threshold_rad_s:.4f}"
            ),
        }
        status.values = [
            KeyValue(key=key, value=value)
            for key, value in values.items()
        ]
        array.status = [status]
        self.diagnostic_publisher.publish(array)


def main(args=None):
    rclpy.init(args=args)
    node = ImuBiasCalibrator()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
