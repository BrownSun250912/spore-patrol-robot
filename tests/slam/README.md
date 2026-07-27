# 室内二维建图测试

完整流程见[室内二维建图操作说明](../../docs/室内二维建图.md)。

本目录的录包脚本会保存建图所需的雷达、里程计、TF、IMU、电池、诊断、控制命令
和地图话题：

```bash
source /opt/ros/humble/setup.bash
source tools/ydlidar_env.sh
source install/setup.bash
tests/slam/record_mapping_bag.sh
```

输出位于 `tests/results/时间_mapping/`，由 Git 忽略。录制期间按一次 `Ctrl+C`
会让 rosbag2 正常写完索引；不要直接关闭终端或强制断电。
