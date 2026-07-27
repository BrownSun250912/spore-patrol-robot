# YDLIDAR X3 Pro 测试

## 1. 识别串口

插入原装 CP210x 转接板后：

```bash
python3 tests/lidar/lidar_test.py ports
```

应至少看到 `/dev/ttyUSB0`，USB ID 为 `10c4:ea60`。如果转接板提供唯一
`ID_SERIAL_SHORT`，可安装稳定设备名：

```bash
tools/install_lidar_udev_rule.sh /dev/ttyUSB0
```

重新插拔后应出现 `/dev/ydlidar`。

## 2. 单独启动雷达和 RViz

```bash
source /opt/ros/humble/setup.bash
source tools/ydlidar_env.sh
source install/setup.bash
ros2 launch spore_patrol_lidar lidar_view.launch.py \
  port:=/dev/ttyUSB0
```

建立 `/dev/ydlidar` 后可省略 `port` 参数。

## 3. 自动检查数据

保持驱动运行，另开终端：

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
python3 tests/lidar/lidar_test.py scan --duration 10
```

结果保存在 `tests/results/时间_lidar_scan/summary.json`。首轮重点记录：

- 是否持续发布 `/scan`；
- `frame_id` 是否为 `laser_link`；
- 实际频率；
- 每圈点数和角分辨率；
- 有效点比例及最近、最远观测距离。

## 4. 确定方向

把纸箱放在小车左前方：

```bash
python3 tests/lidar/lidar_test.py orientation
```

在 ROS 坐标中左前方应为 `x > 0, y > 0`：

- 点云跑到右后方：切换 `reversion`；
- 点云仍在前方但左右颠倒：切换 `inverted`；
- 点云从左前跑到左后方：同时切换 `reversion` 和 `inverted`；
- 方向正确但整体偏转固定角度：修正 URDF 的 `laser_joint` yaw。

示例：

```bash
ros2 launch spore_patrol_lidar lidar_view.launch.py \
  port:=/dev/ttyUSB0 \
  reversion:=true \
  inverted:=true
```

当前实物安装已经通过左前纸箱测试，默认值为
`reversion=true`、`inverted=true`。

## 安全与现场注意事项

- 雷达旋转时不要按压旋转头；
- USB 线需要固定和应力释放，不能让插头承担拉力；
- 先做室内静态测试，再做小车低速运动测试；
- 室外需要分别记录阴天、阳光直射和作物叶片环境的数据；
- RViz 看起来正常不等于满足建图要求，必须保存频率和有效点统计。
