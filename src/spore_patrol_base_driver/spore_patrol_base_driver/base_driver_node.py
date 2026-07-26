"""ROS 2 node bridging cmd_vel and the WHEELTEC STM32 serial protocol."""

import math
import time
from typing import Optional, Tuple

from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
from geometry_msgs.msg import TransformStamped, Twist
from nav_msgs.msg import Odometry
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import BatteryState, Imu
from tf2_ros import TransformBroadcaster

from .motion_limits import clamp, move_toward
from .odometry import PlanarOdometry
from .protocol import (
    StatusFrame,
    StatusStreamDecoder,
    accel_raw_to_mps2,
    build_command_frame,
    gyro_raw_to_radps,
)
from .serial_transport import LinuxSerialPort


def yaw_quaternion(yaw: float) -> Tuple[float, float, float, float]:
    half = 0.5 * yaw
    return 0.0, 0.0, math.sin(half), math.cos(half)


class BaseDriverNode(Node):
    """Serial base driver with host and STM32 watchdog support."""

    def __init__(self) -> None:
        super().__init__("spore_patrol_base_driver")

        self.declare_parameter("port", "/dev/ttyACM0")
        self.declare_parameter("baud", 115200)
        self.declare_parameter("command_rate_hz", 20.0)
        self.declare_parameter("cmd_vel_timeout_s", 0.30)
        self.declare_parameter("feedback_timeout_s", 0.50)
        self.declare_parameter("max_linear_mps", 0.15)
        self.declare_parameter("max_angular_radps", 0.30)
        self.declare_parameter("max_linear_accel_mps2", 0.40)
        self.declare_parameter("max_angular_accel_radps2", 0.80)
        self.declare_parameter("battery_warn_voltage", 21.0)
        self.declare_parameter("battery_error_voltage", 20.0)
        self.declare_parameter("use_feedback_vy", False)
        self.declare_parameter("publish_tf", True)
        self.declare_parameter("publish_imu", True)
        self.declare_parameter("odom_frame_id", "odom")
        self.declare_parameter("base_frame_id", "base_footprint")
        self.declare_parameter("imu_frame_id", "base_link")
        self.declare_parameter("accel_lsb_per_g", 16384.0)
        self.declare_parameter("gyro_lsb_per_deg_s", 65.5)

        self.port_name = str(self.get_parameter("port").value)
        self.baud = int(self.get_parameter("baud").value)
        self.command_rate_hz = float(
            self.get_parameter("command_rate_hz").value
        )
        self.cmd_vel_timeout_s = float(
            self.get_parameter("cmd_vel_timeout_s").value
        )
        self.feedback_timeout_s = float(
            self.get_parameter("feedback_timeout_s").value
        )
        self.max_linear_mps = float(
            self.get_parameter("max_linear_mps").value
        )
        self.max_angular_radps = float(
            self.get_parameter("max_angular_radps").value
        )
        self.max_linear_accel_mps2 = float(
            self.get_parameter("max_linear_accel_mps2").value
        )
        self.max_angular_accel_radps2 = float(
            self.get_parameter("max_angular_accel_radps2").value
        )
        self.battery_warn_voltage = float(
            self.get_parameter("battery_warn_voltage").value
        )
        self.battery_error_voltage = float(
            self.get_parameter("battery_error_voltage").value
        )
        self.use_feedback_vy = bool(
            self.get_parameter("use_feedback_vy").value
        )
        self.publish_tf = bool(self.get_parameter("publish_tf").value)
        self.publish_imu = bool(self.get_parameter("publish_imu").value)
        self.odom_frame_id = str(
            self.get_parameter("odom_frame_id").value
        )
        self.base_frame_id = str(
            self.get_parameter("base_frame_id").value
        )
        self.imu_frame_id = str(
            self.get_parameter("imu_frame_id").value
        )
        self.accel_lsb_per_g = float(
            self.get_parameter("accel_lsb_per_g").value
        )
        self.gyro_lsb_per_deg_s = float(
            self.get_parameter("gyro_lsb_per_deg_s").value
        )

        if self.command_rate_hz <= 0.0:
            raise ValueError("command_rate_hz must be positive")
        if self.cmd_vel_timeout_s <= 0.0:
            raise ValueError("cmd_vel_timeout_s must be positive")
        if self.max_linear_mps <= 0.0 or self.max_angular_radps <= 0.0:
            raise ValueError("velocity limits must be positive")
        if (
            self.max_linear_accel_mps2 <= 0.0
            or self.max_angular_accel_radps2 <= 0.0
        ):
            raise ValueError("acceleration limits must be positive")
        if not (
            0.0
            < self.battery_error_voltage
            < self.battery_warn_voltage
        ):
            raise ValueError(
                "battery thresholds must satisfy "
                "0 < error voltage < warning voltage"
            )
        if self.accel_lsb_per_g <= 0.0:
            raise ValueError("accel_lsb_per_g must be positive")
        if self.gyro_lsb_per_deg_s <= 0.0:
            raise ValueError("gyro_lsb_per_deg_s must be positive")

        self.transport: Optional[LinuxSerialPort] = None
        self.decoder = StatusStreamDecoder()
        self.planar_odom = PlanarOdometry()
        self.latest_status: Optional[StatusFrame] = None
        self.requested_velocity = (0.0, 0.0)
        self.sent_velocity = (0.0, 0.0)
        self.last_cmd_vel_wall: Optional[float] = None
        self.last_command_send_wall: Optional[float] = None
        self.last_feedback_wall: Optional[float] = None
        self.last_feedback_batch_wall: Optional[float] = None
        self.serial_opened_wall: Optional[float] = None
        self.next_command_wall = time.monotonic()
        self.next_reconnect_wall = time.monotonic()
        self.last_connection_warning_wall = 0.0
        self.frames_since_diagnostic = 0
        self.last_diagnostic_wall = time.monotonic()
        self.shutting_down = False

        self.odom_publisher = self.create_publisher(Odometry, "odom", 20)
        self.imu_publisher = self.create_publisher(Imu, "imu/data_raw", 20)
        self.battery_publisher = self.create_publisher(
            BatteryState, "battery_state", 10
        )
        self.diagnostic_publisher = self.create_publisher(
            DiagnosticArray, "diagnostics", 10
        )
        self.tf_broadcaster = TransformBroadcaster(self)
        self.create_subscription(Twist, "cmd_vel", self._cmd_vel_callback, 10)
        self.io_timer = self.create_timer(0.01, self._io_callback)
        self.diagnostic_timer = self.create_timer(
            1.0, self._publish_diagnostics
        )

        self.get_logger().info(
            f"STM32 base driver configured for {self.port_name} "
            f"at {self.baud} baud"
        )

    def _cmd_vel_callback(self, message: Twist) -> None:
        vx = float(message.linear.x)
        wz = float(message.angular.z)
        if not math.isfinite(vx) or not math.isfinite(wz):
            self.get_logger().error("Rejected non-finite cmd_vel")
            self.requested_velocity = (0.0, 0.0)
        else:
            self.requested_velocity = (
                clamp(vx, -self.max_linear_mps, self.max_linear_mps),
                clamp(
                    wz,
                    -self.max_angular_radps,
                    self.max_angular_radps,
                ),
            )
        self.last_cmd_vel_wall = time.monotonic()

    def _try_open(self, now: float) -> None:
        if self.transport is not None or now < self.next_reconnect_wall:
            return
        candidate = LinuxSerialPort(self.port_name, self.baud)
        try:
            candidate.open()
        except (OSError, ValueError) as exc:
            self.next_reconnect_wall = now + 1.0
            if now - self.last_connection_warning_wall >= 5.0:
                self.get_logger().warning(
                    f"Cannot open {self.port_name}: {exc}; retrying"
                )
                self.last_connection_warning_wall = now
            return

        self.transport = candidate
        self.decoder = StatusStreamDecoder()
        self.last_feedback_wall = None
        self.last_feedback_batch_wall = None
        self.serial_opened_wall = now
        self.next_command_wall = now
        self.sent_velocity = (0.0, 0.0)
        self.last_command_send_wall = None
        self.get_logger().info(f"Opened STM32 serial port {self.port_name}")

    def _disconnect(self, reason: str) -> None:
        if self.transport is not None:
            try:
                self.transport.close()
            except OSError:
                pass
        self.transport = None
        self.serial_opened_wall = None
        self.sent_velocity = (0.0, 0.0)
        self.last_command_send_wall = None
        self.next_reconnect_wall = time.monotonic() + 1.0
        if not self.shutting_down:
            self.get_logger().error(f"STM32 serial connection lost: {reason}")

    def _active_command(self, now: float) -> Tuple[float, float]:
        if (
            self.last_cmd_vel_wall is None
            or now - self.last_cmd_vel_wall > self.cmd_vel_timeout_s
        ):
            return 0.0, 0.0
        return self.requested_velocity

    def _command_for_send(self, now: float) -> Tuple[float, float]:
        command_is_stale = (
            self.last_cmd_vel_wall is None
            or now - self.last_cmd_vel_wall > self.cmd_vel_timeout_s
        )
        if command_is_stale:
            # A watchdog stop bypasses the normal acceleration ramp.
            self.sent_velocity = (0.0, 0.0)
            self.last_command_send_wall = now
            return self.sent_velocity

        if self.last_command_send_wall is None:
            dt = 1.0 / self.command_rate_hz
        else:
            dt = clamp(
                now - self.last_command_send_wall,
                0.0,
                2.0 / self.command_rate_hz,
            )
        desired_vx, desired_wz = self._active_command(now)
        sent_vx, sent_wz = self.sent_velocity
        self.sent_velocity = (
            move_toward(
                sent_vx,
                desired_vx,
                self.max_linear_accel_mps2 * dt,
            ),
            move_toward(
                sent_wz,
                desired_wz,
                self.max_angular_accel_radps2 * dt,
            ),
        )
        self.last_command_send_wall = now
        return self.sent_velocity

    def _io_callback(self) -> None:
        now = time.monotonic()
        self._try_open(now)
        if self.transport is None:
            return

        try:
            raw = self.transport.read()
            if raw:
                frames = self.decoder.feed(raw)
                if frames:
                    self._process_feedback_batch(frames, now)

            if now >= self.next_command_wall:
                vx, wz = self._command_for_send(now)
                self.transport.write(build_command_frame(vx, 0.0, wz))
                self.next_command_wall = now + 1.0 / self.command_rate_hz

            stale_limit = max(1.0, 2.0 * self.feedback_timeout_s)
            if (
                self.last_feedback_wall is None
                and self.serial_opened_wall is not None
                and now - self.serial_opened_wall > stale_limit
            ):
                self._disconnect("no feedback after opening port")
            elif (
                self.last_feedback_wall is not None
                and now - self.last_feedback_wall > stale_limit
            ):
                self._disconnect("feedback timeout")
        except (OSError, RuntimeError, TimeoutError, ValueError) as exc:
            self._disconnect(str(exc))

    def _process_feedback_batch(
        self, frames: list[StatusFrame], now: float
    ) -> None:
        if self.last_feedback_batch_wall is None:
            dt_per_frame = 0.0
        else:
            batch_dt = now - self.last_feedback_batch_wall
            dt_per_frame = batch_dt / len(frames)
        self.last_feedback_batch_wall = now
        self.last_feedback_wall = now

        for frame in frames:
            self.latest_status = frame
            self.frames_since_diagnostic += 1
            vy = frame.vy_mps if self.use_feedback_vy else 0.0
            self.planar_odom.update(
                frame.vx_mps,
                vy,
                frame.wz_radps,
                dt_per_frame,
            )
            self._publish_feedback(frame, vy)

    def _publish_feedback(self, frame: StatusFrame, vy: float) -> None:
        stamp = self.get_clock().now().to_msg()
        qx, qy, qz, qw = yaw_quaternion(self.planar_odom.yaw)

        odom = Odometry()
        odom.header.stamp = stamp
        odom.header.frame_id = self.odom_frame_id
        odom.child_frame_id = self.base_frame_id
        odom.pose.pose.position.x = self.planar_odom.x
        odom.pose.pose.position.y = self.planar_odom.y
        odom.pose.pose.orientation.x = qx
        odom.pose.pose.orientation.y = qy
        odom.pose.pose.orientation.z = qz
        odom.pose.pose.orientation.w = qw
        odom.twist.twist.linear.x = frame.vx_mps
        odom.twist.twist.linear.y = vy
        odom.twist.twist.angular.z = frame.wz_radps
        odom.pose.covariance = [
            0.05, 0.0, 0.0, 0.0, 0.0, 0.0,
            0.0, 0.10, 0.0, 0.0, 0.0, 0.0,
            0.0, 0.0, 1e6, 0.0, 0.0, 0.0,
            0.0, 0.0, 0.0, 1e6, 0.0, 0.0,
            0.0, 0.0, 0.0, 0.0, 1e6, 0.0,
            0.0, 0.0, 0.0, 0.0, 0.0, 0.10,
        ]
        odom.twist.covariance = [
            0.03, 0.0, 0.0, 0.0, 0.0, 0.0,
            0.0, 0.10, 0.0, 0.0, 0.0, 0.0,
            0.0, 0.0, 1e6, 0.0, 0.0, 0.0,
            0.0, 0.0, 0.0, 1e6, 0.0, 0.0,
            0.0, 0.0, 0.0, 0.0, 1e6, 0.0,
            0.0, 0.0, 0.0, 0.0, 0.0, 0.05,
        ]
        self.odom_publisher.publish(odom)

        if self.publish_tf:
            transform = TransformStamped()
            transform.header.stamp = stamp
            transform.header.frame_id = self.odom_frame_id
            transform.child_frame_id = self.base_frame_id
            transform.transform.translation.x = self.planar_odom.x
            transform.transform.translation.y = self.planar_odom.y
            transform.transform.rotation.x = qx
            transform.transform.rotation.y = qy
            transform.transform.rotation.z = qz
            transform.transform.rotation.w = qw
            self.tf_broadcaster.sendTransform(transform)

        if self.publish_imu:
            imu = Imu()
            imu.header.stamp = stamp
            imu.header.frame_id = self.imu_frame_id
            imu.orientation_covariance[0] = -1.0
            imu.angular_velocity.x = gyro_raw_to_radps(
                frame.gyro_x_raw, self.gyro_lsb_per_deg_s
            )
            imu.angular_velocity.y = gyro_raw_to_radps(
                frame.gyro_y_raw, self.gyro_lsb_per_deg_s
            )
            imu.angular_velocity.z = gyro_raw_to_radps(
                frame.gyro_z_raw, self.gyro_lsb_per_deg_s
            )
            imu.linear_acceleration.x = accel_raw_to_mps2(
                frame.accel_x_raw, self.accel_lsb_per_g
            )
            imu.linear_acceleration.y = accel_raw_to_mps2(
                frame.accel_y_raw, self.accel_lsb_per_g
            )
            imu.linear_acceleration.z = accel_raw_to_mps2(
                frame.accel_z_raw, self.accel_lsb_per_g
            )
            imu.angular_velocity_covariance = [
                0.02, 0.0, 0.0,
                0.0, 0.02, 0.0,
                0.0, 0.0, 0.02,
            ]
            imu.linear_acceleration_covariance = [
                0.10, 0.0, 0.0,
                0.0, 0.10, 0.0,
                0.0, 0.0, 0.10,
            ]
            self.imu_publisher.publish(imu)

        battery = BatteryState()
        battery.header.stamp = stamp
        battery.voltage = frame.battery_v
        battery.present = True
        battery.percentage = float("nan")
        battery.power_supply_status = BatteryState.POWER_SUPPLY_STATUS_UNKNOWN
        battery.power_supply_health = BatteryState.POWER_SUPPLY_HEALTH_UNKNOWN
        battery.power_supply_technology = (
            BatteryState.POWER_SUPPLY_TECHNOLOGY_UNKNOWN
        )
        self.battery_publisher.publish(battery)

    def _publish_diagnostics(self) -> None:
        now = time.monotonic()
        elapsed = max(1e-6, now - self.last_diagnostic_wall)
        feedback_rate = self.frames_since_diagnostic / elapsed
        self.frames_since_diagnostic = 0
        self.last_diagnostic_wall = now

        status = DiagnosticStatus()
        status.name = "spore_patrol_base_driver/STM32"
        status.hardware_id = self.port_name
        status.level = DiagnosticStatus.OK
        status.message = "connected"

        connected = self.transport is not None
        feedback_age = (
            float("inf")
            if self.last_feedback_wall is None
            else now - self.last_feedback_wall
        )
        command_age = (
            float("inf")
            if self.last_cmd_vel_wall is None
            else now - self.last_cmd_vel_wall
        )

        if not connected:
            status.level = DiagnosticStatus.ERROR
            status.message = "serial disconnected"
        elif feedback_age > self.feedback_timeout_s:
            status.level = DiagnosticStatus.ERROR
            status.message = "feedback stale"
        elif (
            self.latest_status is not None
            and self.latest_status.battery_v <= self.battery_error_voltage
        ):
            status.level = DiagnosticStatus.ERROR
            status.message = "battery voltage critical"
        elif (
            self.latest_status is not None
            and self.latest_status.battery_v <= self.battery_warn_voltage
        ):
            status.level = DiagnosticStatus.WARN
            status.message = "battery voltage low"
        elif self.latest_status is not None and self.latest_status.flag_stop:
            status.level = DiagnosticStatus.WARN
            status.message = "motor control disabled"

        values = {
            "port": self.port_name,
            "baud": str(self.baud),
            "connected": str(connected).lower(),
            "feedback_rate_hz": f"{feedback_rate:.1f}",
            "feedback_age_s": (
                "inf" if math.isinf(feedback_age) else f"{feedback_age:.3f}"
            ),
            "cmd_vel_age_s": (
                "inf" if math.isinf(command_age) else f"{command_age:.3f}"
            ),
            "host_cmd_timeout_s": f"{self.cmd_vel_timeout_s:.3f}",
            "requested_vx_mps": f"{self.requested_velocity[0]:.3f}",
            "requested_wz_radps": f"{self.requested_velocity[1]:.3f}",
            "sent_vx_mps": f"{self.sent_velocity[0]:.3f}",
            "sent_wz_radps": f"{self.sent_velocity[1]:.3f}",
            "max_linear_accel_mps2": (
                f"{self.max_linear_accel_mps2:.3f}"
            ),
            "max_angular_accel_radps2": (
                f"{self.max_angular_accel_radps2:.3f}"
            ),
            "discarded_serial_bytes": str(self.decoder.discarded_bytes),
            "invalid_frame_candidates": str(
                self.decoder.invalid_candidates
            ),
        }
        if self.latest_status is not None:
            values["flag_stop"] = str(self.latest_status.flag_stop)
            values["battery_v"] = f"{self.latest_status.battery_v:.3f}"
        status.values = [
            KeyValue(key=key, value=value) for key, value in values.items()
        ]

        array = DiagnosticArray()
        array.header.stamp = self.get_clock().now().to_msg()
        array.status = [status]
        self.diagnostic_publisher.publish(array)

    def send_final_stop(self) -> None:
        self.shutting_down = True
        if self.transport is None:
            return
        stop_frame = build_command_frame(0.0, 0.0, 0.0)
        try:
            for _ in range(15):
                self.transport.write(stop_frame)
                time.sleep(0.02)
        except (OSError, RuntimeError, TimeoutError):
            pass
        finally:
            try:
                self.transport.close()
            except OSError:
                pass
            self.transport = None


def main(args=None) -> None:
    rclpy.init(args=args)
    node = BaseDriverNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.send_final_stop()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
