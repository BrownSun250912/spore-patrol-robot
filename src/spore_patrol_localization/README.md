# Spore Patrol Localization

This package provides the continuous local `odom -> base_footprint` estimate.
It fuses the STM32 wheel-velocity feedback with the chassis ICM20948 yaw rate
using `robot_localization` in planar mode.

The current STM32 protocol does not expose an orientation quaternion or the
ICM20948 magnetometer, so the EKF deliberately uses only:

- `/odom`: forward and zero lateral velocity;
- `/imu/data_raw`: unchanged STM32 IMU data for calibration and audit;
- `/imu/data_calibrated`: startup-bias-corrected yaw angular velocity.

At startup the calibrator requires 10 seconds of stationary gyro samples. It
holds the calibrated topic until the window finishes and restarts the window
if angular motion exceeds 0.03 rad/s. The raw topic is never modified. A
manual recalibration is available through
`/imu_bias_calibrator/recalibrate`.

The CMP10A is reserved for a later outdoor absolute-heading input. Do not fuse
both IMUs as equivalent yaw-rate sources before their axes, latency, covariance
and magnetic interference have been measured.

## Real-hardware launch

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash

ros2 launch spore_patrol_localization hardware_localization.launch.py \
  port:=/dev/ttyACM0 \
  lidar:=false \
  rviz:=true
```

Keep the chassis completely stationary until the terminal prints
`Gyro bias calibration complete`. The normal configuration uses 10 seconds
and approximately 200 samples at the current 20 Hz feedback rate.

This launch disables the base driver's raw TF and lets the EKF be the only
publisher of `odom -> base_footprint`. The raw `/odom` topic remains available
as an EKF measurement and `/odometry/filtered` is the fused output.

## Mapping with fused local odometry

```bash
ros2 launch spore_patrol_localization mapping_localization.launch.py \
  base_port:=/dev/ttyACM0 \
  lidar_port:=/dev/ydlidar \
  rviz:=true
```

SLAM Toolbox remains the owner of `map -> odom`; the EKF owns only
`odom -> base_footprint`.

## Checks

```bash
ros2 topic hz /odom
ros2 topic hz /imu/data_raw
ros2 topic hz /imu/data_calibrated
ros2 topic hz /odometry/filtered
ros2 run tf2_ros tf2_echo odom base_footprint
ros2 topic echo /diagnostics --once
```

After calibration, the raw IMU, calibrated IMU and odometry streams should be approximately
20 Hz. To restart calibration while the chassis is stationary:

```bash
ros2 service call /imu_bias_calibrator/recalibrate std_srvs/srv/Trigger "{}"
```

Never launch the original hardware bringup and
`hardware_localization.launch.py` at the same time because both would open the
same STM32 serial port.

## CMP10A boundary

The later CMP10A driver should publish a separate `cmp10a_link` frame and an
absolute-heading topic such as `/imu/heading`. Its magnetometer must be tested
with motors and all payload electronics powered before it is accepted as an
outdoor heading source.
