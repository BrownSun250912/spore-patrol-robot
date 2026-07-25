# 底盘测试工具

本目录保存项目的测试程序、测试模板和本机生成的测试结果。当前第一套工具用于在不启动 ROS 2 的情况下，直接通过 Ubuntu 串口测试 WHEELTEC STM32 底盘。

## 目录

```text
tests/
├── chassis_serial/
│   ├── protocol.py             STM32控制帧/反馈帧编解码
│   ├── chassis_serial_test.py  现场串口测试命令
│   ├── fake_stm32.py           不连接小车的伪串口模拟器
│   └── test_protocol.py        不连接小车也能运行的单元测试
├── templates/
│   └── chassis_test_record.md  现场测试记录模板
└── results/                    自动生成的CSV、原始数据和元数据
```

`results/` 中的现场数据默认不提交到 Git，确认数据不含敏感信息并且确实需要共享时再选择性提交。

## 安全要求

1. 第一次通电前必须把四个车轮可靠架空。
2. 小车旁必须有人能够立即按急停或切断总电源。
3. 先运行只读监听和停车命令，再允许运动测试。
4. 未通过通信失联停车测试前，不允许落地自动运行。
5. 当前固件启动后可能执行电机自检，通电时不要让车轮接触地面。
6. 不确认接口电平时，不要把5 V TTL直接接入STM32。

## 1. 离线检查测试代码

不连接小车即可运行，不需要安装第三方Python包：

```bash
cd /media/brown/新加卷1/STM32_Project/WHEELTEC_C50X_2026.05.29/spore_patrol_ws
python3 -m unittest -v tests/chassis_serial/test_protocol.py
python3 tests/chassis_serial/chassis_serial_test.py selftest
```

还可以用两个终端完整演练现场流程。终端一：

```bash
python3 tests/chassis_serial/fake_stm32.py
```

模拟器会输出一个形如 `/dev/pts/8` 的端口。终端二将该端口代入：

```bash
python3 tests/chassis_serial/chassis_serial_test.py listen \
  --port /dev/pts/8 \
  --duration 3
```

模拟器只用于验证电脑端程序，不代表真实底盘、真实传感器或真实失联停车已经通过。

## 2. 查找串口

插入USB转串口之前运行一次，插入之后再运行一次：

```bash
python3 tests/chassis_serial/chassis_serial_test.py ports
dmesg | tail -n 30
```

常见设备为 `/dev/ttyUSB0` 或 `/dev/ttyACM0`。如果提示没有权限：

```bash
sudo usermod -aG dialout "$USER"
```

执行后注销并重新登录。不要使用长期的 `sudo python3` 代替正确的串口权限配置。

以下示例假定设备是 `/dev/ttyUSB0`，实际操作时请替换。

## 3. 只读监听反馈

先不开启运动，只读取10秒STM32反馈：

```bash
python3 tests/chassis_serial/chassis_serial_test.py listen \
  --port /dev/ttyUSB0 \
  --duration 10
```

正常情况下应解析到约20 Hz的状态帧，并显示 `vx/vy/wz`、IMU和电池电压。结果自动保存到 `tests/results/日期_时间_listen/`。

## 4. 主动发送停车帧

```bash
python3 tests/chassis_serial/chassis_serial_test.py stop \
  --port /dev/ttyUSB0
```

确认四个车轮均不转后再继续。

## 5. 单项低速运动

必须保持车轮架空：

```bash
python3 tests/chassis_serial/chassis_serial_test.py motion \
  --port /dev/ttyUSB0 \
  --vx 0.05 \
  --wz 0 \
  --duration 2 \
  --arm WHEELS_OFF_GROUND
```

反向测试：

```bash
python3 tests/chassis_serial/chassis_serial_test.py motion \
  --port /dev/ttyUSB0 \
  --vx -0.05 \
  --duration 2 \
  --arm WHEELS_OFF_GROUND
```

原地低速旋转：

```bash
python3 tests/chassis_serial/chassis_serial_test.py motion \
  --port /dev/ttyUSB0 \
  --vx 0 \
  --wz 0.15 \
  --duration 2 \
  --arm WHEELS_OFF_GROUND
```

脚本限制线速度绝对值不超过 `0.15 m/s`、角速度绝对值不超过 `0.30 rad/s`、单次持续不超过5秒。测试结束或按 `Ctrl+C` 时会连续发送停车帧。

## 6. 自动架空轮动作序列

依次执行：停车、前进、停车、后退、停车、左转、停车、右转、停车。

```bash
python3 tests/chassis_serial/chassis_serial_test.py sequence \
  --port /dev/ttyUSB0 \
  --arm WHEELS_OFF_GROUND
```

一名同学操作电脑，一名同学守住电源，一名同学核对A/B/C/D轮，一名同学录像和记录。

## 7. 通信失联停车测试

只有在架空轮、急停人员就位后才能运行：

```bash
python3 tests/chassis_serial/chassis_serial_test.py failsafe \
  --port /dev/ttyUSB0 \
  --arm WHEELS_OFF_GROUND_AND_EMERGENCY_STOP_READY
```

脚本会：

1. 以 `0.03 m/s` 发送1秒低速前进命令；
2. 停止发送命令2秒，但继续读取反馈；
3. 观察速度是否自动降到接近零；
4. 最后主动发送停车帧恢复。

如果静默期间车轮没有自动停止，判定当前固件失联停车不合格。立即停车，不要落地测试。

## 8. 现场结束后

复制并填写：

```bash
cp tests/templates/chassis_test_record.md \
  tests/results/chassis_test_record_YYYY-MM-DD.md
```

将测试视频、照片和结果目录一起备份。需要提交到GitHub的记录应去除个人信息和不必要的大文件。
