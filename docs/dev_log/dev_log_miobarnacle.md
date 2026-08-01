# miobarnacle-ops 开发日志

> 分支：`feature/miobarnacle`。负责 Web 控制台与机器人项目的整合（SLAM 建图、实时监控、轨迹导出回放）。

## 7/26
- 在 Windows 端完成多模态农田孢子监测系统 V4.0 Web 控制台（Next.js）的第一版开发，将原 Tkinter 桌面程序迁移为浏览器控制台
- 实现路径规划、环境监测、PCR 分析、病害识别、趋势预警、监管中心六大功能模块

## 8/1
- 将 Web 控制台从 Windows 迁移到 Ubuntu 开发环境，解决代理、Python 环境、依赖安装等问题
- **P0 - SLAM 地图导入**：实现 `.pgm + .yaml` 地图解析（分辨率、原点自动读取），导入后路径规划首边像素 × 分辨率自动换算真实米数，边界标定直接落在真实地图上
- **P0 - 数据层抽象**：设计 `DataSource` 接口（localStorage 实现），为后续接入 rosbridge 真实数据铺路
- **P1 - rosbridge 实时监控**：打通 仿真小车 → ROS 话题 → rosbridge → Web 浏览器 链路
  - 新增"机器人监控"Tab：实时位姿（/odom）、激光雷达点云（/scan）、话题频率统计
  - 远程遥控：发送 /cmd_vel 驱动小车、急停
  - 实测：Web 面板远程驱动仿真小车移动 0.98m，odom 29.4Hz / scan 5.0Hz
- **P2 - 轨迹叠加与导出回放**：
  - /odom 位姿历史实时叠加到 SLAM 地图或米制坐标上，闭环"建图→规划→执行→轨迹回放"
  - 导出轨迹 JSON / GeoJSON（可导入 QGIS 等工具）
  - 导入历史轨迹 + 回放动画（0.5×~8× 倍速、进度拖动、点间插值平滑）
  - 实测：采集 8 点轨迹 → 导出 JSON/GeoJSON → 导入恢复 → 回放推进

## 开发/运行环境备忘
- Web 控制台：`npm run dev`（端口 3000），无 ChatGPT 登录要求，数据不自动上传
- 仿真小车：`spore_patrol_sim/sim.launch.py`（Gazebo + rosbridge，WebSocket 端口 9091）
- 环境坑：需排除 anaconda Python 冲突；小车可能撞上农田世界中的障碍物卡死，需重启仿真
