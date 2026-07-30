# ICM20948 零偏校准与 EKF 复测

本目录用于验证 STM32 板载 ICM20948、轮式里程计和
`robot_localization` EKF。测试不需要启动激光雷达。

## 原理

MEMS 陀螺仪即使完全静止也会输出一个很小的非零角速度。持续积分后，这个固定偏差
会变成不断增长的航向误差：

```text
航向角 = 角速度随时间的积分
```

首次实测中，ICM20948 Z轴静止均值约为：

```text
+0.000835 rad/s = +0.0479°/s ≈ +2.87°/min
```

因此原EKF在静止123秒后漂移约5.88°。现在启动流程增加
`imu_bias_calibrator`：

```text
前10秒保持静止
        ↓
对三轴角速度求平均，得到 bias_x/y/z
        ↓
校正角速度 = 原始角速度 - bias
        ↓
/imu/data_calibrated
        ↓
EKF与轮速融合，输出 /odometry/filtered
```

原始 `/imu/data_raw` 不会被修改，便于审计和离线比较。如果校准期间检测到角速度
模长超过0.03 rad/s，10秒窗口会自动清零重计，防止把真实运动当成零偏。

## 1. 编译

```bash
cd ~/spore_patrol_ws
source /opt/ros/humble/setup.bash
colcon build --symlink-install --packages-up-to spore_patrol_localization
source install/setup.bash
```

## 2. 启动和等待校准

终端一：

```bash
cd ~/spore_patrol_ws
source /opt/ros/humble/setup.bash
source install/setup.bash

ros2 launch spore_patrol_localization hardware_localization.launch.py \
  port:=/dev/ttyACM0 \
  lidar:=false \
  rviz:=true
```

启动后不要碰车、不要发送 `/cmd_vel`。先看到：

```text
Keep the robot completely stationary for 10.0 s
```

约10秒后应看到：

```text
Gyro bias calibration complete with ... samples:
x=..., y=..., z=... rad/s
```

出现第二条日志后才能开始运动。若持续提示 `motion detected`，说明车体被移动、底盘
振动过大或陀螺仪数据异常。

终端二检查：

```bash
source /opt/ros/humble/setup.bash
source ~/spore_patrol_ws/install/setup.bash

ros2 topic hz /imu/data_raw
ros2 topic hz /imu/data_calibrated
ros2 topic hz /odometry/filtered
ros2 topic echo /diagnostics --once
```

校准完成后三个话题均应约20 Hz，诊断中的
`spore_patrol_localization: IMU gyro bias` 应为 `calibrated`。

需要重新校准时先让车完全静止，再执行：

```bash
ros2 service call \
  /imu_bias_calibrator/recalibrate \
  std_srvs/srv/Trigger \
  "{}"
```

执行后重新静止等待10秒。

## 3. 静止60秒复测

终端三：

```bash
cd ~/spore_patrol_ws
source /opt/ros/humble/setup.bash
source install/setup.bash

ros2 bag record \
  -o tests/results/imu_static_after_bias_60s \
  /odom \
  /imu/data_raw \
  /imu/data_calibrated \
  /odometry/filtered \
  /tf \
  /tf_static \
  /cmd_vel \
  /diagnostics \
  /battery_state
```

保持静止60秒后按一次 `Ctrl+C`。目标：

- `/imu/data_calibrated` 的Z轴均值接近0；
- 融合航向60秒漂移最好不超过1°，最多不超过2°；
- 融合位置保持不动。

## 4. 左转360°复测

用胶带标出车头起始方向。开始录包：

```bash
ros2 bag record \
  -o tests/results/imu_rotate_left_360_retry \
  /odom \
  /imu/data_raw \
  /imu/data_calibrated \
  /odometry/filtered \
  /tf \
  /tf_static \
  /cmd_vel \
  /diagnostics \
  /battery_state
```

先静止10秒，然后在另一个终端持续发布左转命令：

```bash
ros2 topic pub -r 10 \
  /cmd_vel \
  geometry_msgs/msg/Twist \
  "{linear: {x: 0.0, y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: 0.20}}"
```

车头完成一整圈并重新对准标记时，在运动命令终端按 `Ctrl+C`，立即发送：

```bash
ros2 topic pub --once /cmd_vel geometry_msgs/msg/Twist "{}"
```

保持静止10秒，然后结束录包。不要再前进，也不要做多次左右修正。

## 5. 右转360°复测

录包名称：

```text
tests/results/imu_rotate_right_360_verify
```

录制话题与左转相同，运动命令只把Z轴角速度改为负值：

```bash
ros2 topic pub -r 10 \
  /cmd_vel \
  geometry_msgs/msg/Twist \
  "{linear: {x: 0.0, y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: -0.20}}"
```

完成一圈后按 `Ctrl+C` 并发送一次空 `Twist` 停车。

如果左右转已经录在同一个 bag 中，也可以直接继续分析。脚本会根据
`/cmd_vel.angular.z` 的正负自动拆分左转和右转，不必为了拆分文件重新跑车。
分析前必须先在录包终端按 `Ctrl+C`，等终端显示录制停止并生成
`metadata.yaml`。

## 6. 自动分析

3 m直行基线已经通过，可继续使用原包：

```bash
cd ~/spore_patrol_ws
source /opt/ros/humble/setup.bash
source install/setup.bash

python3 tests/localization/analyze_ekf_bags.py \
  --static tests/results/imu_static_after_bias_60s \
  --straight tests/results/imu_straight_3m \
  --left tests/results/imu_rotate_left_360_retry \
  --left-angle 720 \
  --right-angle 360 \
  --straight-distance 3.05 \
  --output tests/results/imu_ekf_analysis_after_bias
```

上面的命令适用于本次“同一 bag 内左转约720°、右转约360°”的数据。
`--left-angle` 和 `--right-angle` 是人工观察到的实际目标角度，脚本会据此计算
融合角度误差。

如果以后左右转分别录包，则增加右转包参数：

```bash
python3 tests/localization/analyze_ekf_bags.py \
  --static tests/results/imu_static_after_bias_60s \
  --straight tests/results/imu_straight_3m \
  --left tests/results/imu_rotate_left_360_retry \
  --right tests/results/imu_rotate_right_360_verify \
  --left-angle 360 \
  --right-angle 360 \
  --straight-distance 3.05 \
  --output tests/results/imu_ekf_analysis_after_bias
```

同一个 bag 中有多个方向时，报告中的 `rotate_left` 和 `rotate_right` 分别表示
`angular.z > 0` 和 `angular.z < 0` 的命令窗口。

输出：

```text
tests/results/imu_ekf_analysis_after_bias/
├── report.md
├── summary.json
└── trajectories.png
```

## 7. 验收指标

| 项目 | 目标 |
|---|---:|
| 静止60秒融合航向漂移 | 最好≤1°，最多≤2° |
| 旋转融合角度 | 相对人工目标角度误差≤2% |
| 左右每圈等效绝对角度差 | ≤5° |
| 原地旋转净平移 | ≤3 cm |
| 原始/校正IMU和融合里程计频率 | 约20 Hz |

所有落地运动必须有人跟车并能立即关闭电机使能或总电源。
