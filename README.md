# Spore Patrol Robot

面向“基于机器人与 DNA-PCR 技术的孢子病害识别”项目的 ROS 2 机器人导航工作区。
本仓库只负责机器人底盘、定位、导航、路径规划和硬件联调；孢子收集及生物检测由其他
小组负责。

## 当前状态

已确认实车为 WHEELTEC 高配摆式悬挂四驱底盘：

- STM32F407 下位机；
- MD36L-P27 电机，24 V、60 W、1:27 减速比；
- 500 线 AB 相 GMR 编码器，STM32 四倍频计数；
- 152 mm 越野轮；
- 图纸轴距 312.7 mm、轮中心距约 335.6 mm；
- 裸车质量约 7.6 kg，24 V 6000 mAh 电池。

详细参数及“图纸尺寸”和“固件有效运动学参数”的区别见
[高配摆式悬挂底盘参数](docs/小车相关参数/README.md)。

### 已完成

- 高配摆式底盘 Xacro/URDF 模型和 ROS 坐标系；
- Gazebo Classic 简化农田场景及二维激光雷达仿真；
- STM32 11 字节速度命令和 24 字节状态反馈协议；
- ROS 2 串口底盘驱动；
- `/cmd_vel` 控制、轮式 `/odom`、`odom -> base_footprint` TF；
- `/imu/data_raw`、`/battery_state` 和 `/diagnostics`；
- 上位机 0.30 秒命令看门狗、STM32 通信失联停车；
- 速度和加速度限制、低电压诊断、串口断线重连；
- 独立串口测试工具、原始字节记录、CSV 和测试摘要；
- 3 m 直线、原地旋转、四轮动作和失联停车实车测试。

当前实测基线：

- STM32 状态反馈约 20 Hz；
- 编码器目标 3.000 m 对应卷尺距离约 3.05 m；
- 90°和 360°原地旋转表现正常，仍需补充重复测量数据；
- 失联停车已通过一次现场测试，修改或重新烧录固件后必须复测。

### 尚未完成

- 实物二维激光雷达接入和室外数据评估；
- 北斗 RTK、航向和 CORS/NTRIP 链路；
- `robot_localization` 轮速、IMU、RTK/SLAM 融合；
- Nav2 建图、定位、规划和动态避障；
- 田间往复式覆盖路径和电子围栏；
- “到点—停车—采样—确认—继续”任务状态机；
- 携带完整载荷后的质量、重心、续航和越障复测。

## 工作区结构

```text
spore_patrol_ws/
├── src/
│   ├── spore_patrol_base_driver  STM32协议、串口、里程计、IMU、电池、诊断
│   ├── spore_patrol_description  高配摆式底盘URDF/Xacro和RViz配置
│   ├── spore_patrol_sim          Gazebo农田世界及激光雷达仿真
│   └── spore_patrol_bringup      仿真和实车统一启动入口
├── tests/
│   ├── chassis_serial            不依赖ROS运行时的底盘测试程序
│   ├── results                   现场原始数据和测试结果
│   └── templates                 测试记录模板
└── docs/                         参数、协作说明和汇报材料
```

后续计划增加：

```text
spore_patrol_localization  轮速、IMU、RTK和SLAM融合
spore_patrol_navigation    Nav2规划、控制与避障
spore_patrol_coverage      田间覆盖路径
spore_patrol_mission       采样任务状态机
```

## 环境

- Ubuntu 22.04
- ROS 2 Humble
- Gazebo Classic 11
- Python 3.10

## 编译

当前工作区位于 `/media` 外接挂载盘，不要使用 `--symlink-install`：

```bash
cd "/media/brown/新加卷1/STM32_Project/WHEELTEC_C50X_2026.05.29/spore_patrol_ws"
source /opt/ros/humble/setup.bash
colcon build
source install/setup.bash
```

如果工作区以后迁移到 Ubuntu ext4 分区，才建议使用 `--symlink-install`。

离线测试：

```bash
python3 -m unittest -v tests/chassis_serial/test_protocol.py
python3 tests/chassis_serial/chassis_serial_test.py selftest
```

当前验证结果为：

```text
ROS 2四个包构建成功
底盘包colcon测试：8项通过
全部Python测试：17项通过
URDF/Xacro解析通过
```

## 不连接小车查看模型

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 launch spore_patrol_description display.launch.py
```

该启动文件会临时发布静态 `odom -> base_footprint`。不要与实车
`hardware.launch.py` 同时运行，否则会重复发布同一段 TF。

## Gazebo农田演示

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 launch spore_patrol_bringup demo.launch.py
```

另开终端控制：

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 run teleop_twist_keyboard teleop_twist_keyboard
```

Gazebo 当前使用平面运动插件，只适合展示话题、TF、场景和传感器链路，不代表真实四驱
滑移转向动力学，也不能作为 Nav2 控制器参数已经验证的依据。

## 真实底盘ROS 2驱动

先确认串口：

```bash
python3 tests/chassis_serial/chassis_serial_test.py ports
```

启动底盘驱动、机器人模型和 RViz：

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 launch spore_patrol_bringup hardware.launch.py \
  port:=/dev/ttyACM0 \
  rviz:=true
```

如果没有连接小车，驱动不会收到状态帧，也不会发布动态
`odom -> base_footprint`，RViz 会提示 `Frame [odom] does not exist`。这是预期现象，
不代表 URDF 损坏。

驱动默认参数：

| 参数 | 默认值 | 说明 |
|---|---:|---|
| 串口 | `/dev/ttyACM0` | 推荐后续配置固定 udev 名称 |
| 波特率 | 115200 | STM32 ROS 串口 |
| 发送频率 | 20 Hz | 持续发送速度或停车帧 |
| 命令超时 | 0.30 s | 超时立即发送零速度 |
| 最大线速度 | 0.15 m/s | 当前低速联调限制 |
| 最大角速度 | 0.30 rad/s | 当前低速联调限制 |
| 最大线加速度 | 0.40 m/s² | 正常控制指令斜坡 |
| 最大角加速度 | 0.80 rad/s² | 正常控制指令斜坡 |
| 低电压警告 | 21.0 V | 发布 WARN 诊断 |
| 严重低电压 | 20.0 V | 发布 ERROR 诊断 |

主要话题：

| 方向 | 话题 | 类型 |
|---|---|---|
| 订阅 | `/cmd_vel` | `geometry_msgs/msg/Twist` |
| 发布 | `/odom` | `nav_msgs/msg/Odometry` |
| 发布 | `/imu/data_raw` | `sensor_msgs/msg/Imu` |
| 发布 | `/battery_state` | `sensor_msgs/msg/BatteryState` |
| 发布 | `/diagnostics` | `diagnostic_msgs/msg/DiagnosticArray` |

运行检查：

```bash
ros2 topic hz /odom
ros2 topic echo /imu/data_raw --once
ros2 topic echo /battery_state --once
ros2 topic echo /diagnostics --once
ros2 run tf2_ros tf2_echo odom base_footprint
```

## STM32底盘现场测试

开始前必须完整阅读[底盘测试操作说明](tests/README.md)。测试工具支持：

- 查找串口、监听反馈和连续发送停车帧；
- 架空轮前进、后退、左转、右转；
- 3 m 编码器距离测试；
- 90°和 360°原地旋转测试；
- 通信失联停车测试；
- 不连接实车的伪 STM32 和协议单元测试。

每次新测试会保存：

```text
tests/results/时间_测试类型/
├── metadata.json  命令参数、串口和开始时间
├── summary.json   帧率、校验统计、结论、滑行或过转结果
├── frames.csv     速度、原始IMU、SI单位IMU和电池逐帧数据
└── raw.bin        未经处理的串口原始字节
```

测试工具会自动发送停车帧，但不能替代人员看守的物理急停。

## 固件说明

- `_4WD_CAR` 是当前需要编译的 Keil 工程目标；
- 高配摆式车型对应 `SENIOR_4WD_BS`、`MD36N_27`、`GMR_500` 和
  `WheelDiameter_4WD_152`；
- `SYSTEM/sys/sys.c` 中 `SecurityLevel=0`，启用串口命令丢失停车；
- `CarType/4wd_robot_init.c` 已加入车型 ADC 越界保护和安全回退；
- 修改后的固件源码只有重新编译并烧录后才会在实车生效。

图纸几何参数用于 URDF 外观和碰撞体；固件中的半轮距、半轴距还包含厂家运动学经验值，
不能仅按图纸直接覆盖，应使用重复直线和旋转实验标定。

## 可视化材料

系统总体方案：

![系统总体方案](docs/system_architecture.svg)

模型尺寸已经更新为高配摆式底盘。后续完成雷达安装和传感器位置测量后，再重新生成
RViz、Gazebo 和导航界面截图。

## 安全原则

- 首次测试、重新烧录或修改驱动后必须先将四轮可靠架空；
- 失联停车每次改动后必须重新实测，不能只根据源码判断；
- 落地测试必须有人守住硬件急停或总电源；
- 看门狗、软件停车和 `Ctrl+C` 不能替代独立硬件急停；
- 未完成定位、避障和电子围栏验证前，不允许无人自动运行；
- 仿真结果不能直接作为实车导航、定位、续航或安全指标；
- 比赛数据必须保留命令参数、原始数据、视频和可追溯记录。
