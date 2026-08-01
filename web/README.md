# 多模态农田孢子监测与病害扩散预警系统 V4.0 — Web 控制台

面向"作物重大病害智能巡检机器人"大学生创新竞赛的浏览器控制台。以原 `main_inspection_system_v4_compliance.py`（Tkinter 桌面程序）为功能基准，迁移为 Next.js 单页应用，并逐步与 ROS 2 机器人项目整合（SLAM 建图、rosbridge 实时监控、轨迹导出回放）。

## 快速开始

```bash
# 需要 Node.js ≥ 22.13
npm install
npm run dev
```

浏览器打开 <http://localhost:3000>。

- 不需要 ChatGPT 登录，运行在本地，数据不自动上传。
- 当前数据源为本地模拟 + localStorage；接入机器人真实数据时，数据层接口保持不变。

## 六大功能模块

| Tab | 功能 | 说明 |
|---|---|---|
| 路径规划 | 底图导入、边界标定、覆盖路径规划 | 支持导入机器人 SLAM 建图作为真实底图 |
| 环境监测 | 气象/土壤/孢子浓度录入、异常检测 | 稳健异常分数算法 |
| PCR 分析 | Ct 录入、标曲、融合热力图、对比 | 支持 CSV 导入、模拟数据 |
| 病害识别 | 8 种常见病害 HSV 特征分类 | 含混淆矩阵 |
| 趋势预警 | 3/5/7 天扩散预测、P90 风险分级 | 高斯烟羽 + Pasquill 稳定度模型 |
| 监管中心 | 地块注册、告警闭环、历史趋势 | 告警待确认→处理中→已闭环 |

所有模块支持导出 JSON / CSV / TXT / GeoJSON / HTML 报告。

## 与机器人项目的整合成果（P0-P2）

### P0 — SLAM 地图导入 + 数据层抽象
- **导入机器人 SLAM 建图**：解析 `.pgm + .yaml`（分辨率、原点自动读取），渲染为底图。
- **比例尺自动换算**：在 SLAM 地图上标定边界时，首边像素 × 分辨率 = 真实米数，规划坐标直接落在真实世界坐标系。
- **数据层抽象**：`lib/data-source.ts` 定义 `DataSource` 接口（当前 localStorage 实现），后续接 rosbridge 真实数据只需实现同接口。

### P1 — rosbridge 实时机器人监控（「机器人监控」Tab）
- 打通 **仿真/实车 → ROS 话题 → rosbridge → Web 浏览器** 链路。
- 实时显示：`/odom` 位姿、`/scan` 激光点云、话题频率、更新状态。
- 远程遥控：发送 `/cmd_vel` 线/角速度指令，一键急停。
- 实测（Gazebo 仿真）：远程驱动小车移动 0.98 m，odom 29.4 Hz / scan 5.0 Hz。

### P2 — 轨迹叠加、导出与回放
- **实时轨迹叠加**：`/odom` 位姿历史叠加到 SLAM 地图（同一世界坐标系）或纯米制坐标，闭环"建图→规划→执行→轨迹回放"。
- **导出**：轨迹 JSON（完整点位+时间戳）、GeoJSON（LineString，可导入 QGIS）。
- **回放**：导入历史轨迹后按真实时间回放动画，支持 0.5×~8× 倍速、进度条拖动、点间插值平滑。

## 目录结构

```
web/
├── app/page.tsx           # 主界面（单页 UI，路径规划/环境/ PCR/病害/预警/监管）
├── components/
│   └── robot-monitor-panel.tsx  # 机器人监控面板（桥接、点云、遥控、轨迹、回放）
├── lib/
│   ├── slam-map.ts        # PGM/YAML 地图解析
│   ├── robot-bridge.ts    # roslib 桥接（/odom /scan /cmd_vel）
│   ├── use-robot-bridge.ts# React hook 封装
│   ├── data-source.ts     # DataSource 数据层接口
│   ├── data-types.ts      # 共享类型
│   ├── inspection-engine.ts  # 规划/IDW/融合/扩散模型
│   └── disease-monitoring.ts # 病害库 + HSV 分类
├── public/demo_slam_map.pgm+yaml  # 演示 SLAM 地图
└── start-dev.sh           # 一键启动脚本
```

## 与 ROS 机器人对接方式（接手必读）

Web 端通过 `roslib.js` + `rosbridge_server` 连接 ROS，默认 `ws://127.0.0.1:9091`：

```bash
# 机器人端（或仿真机）启动 rosbridge，避开 9090 被占用的场景
ros2 launch rosbridge_server rosbridge_websocket_launch.xml port:=9091

# 仿真小车（无实车时）
ros2 launch spore_patrol_sim sim.launch.py gui:=false rviz:=false
```

Web 端订阅/发布的话题：

| 话题 | 类型 | 用途 |
|---|---|---|
| `/odom` | nav_msgs/Odometry | 位姿、轨迹、频率 |
| `/scan` | sensor_msgs/LaserScan | 激光点云可视化 |
| `/cmd_vel` | geometry_msgs/Twist | 远程遥控 |

## 开发与测试备忘

- 本项目带独立 git 历史，位于仓库根目录 `web/` 下；`.gitignore` 已排除 node_modules、.next、.env 等。
- 环境坑：开发机需排除 anaconda Python 冲突（ROS 用系统 python3.10）；Gazebo 仿真小车可能撞上农田世界障碍物卡死，需重启仿真。
- 完整迁移清单见 [FUNCTION_PARITY.md](./FUNCTION_PARITY.md)。
