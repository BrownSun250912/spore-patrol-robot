// 机器人实时数据桥接模块
// 通过 roslibjs 连接 rosbridge_server (WebSocket)，
// 订阅机器人话题(/odom /scan /cmd_vel 等)，供 UI 实时展示。
// 依赖: rosbridge_server 运行在机器人端(或本机仿真)，默认端口 9091。

import { Ros, Topic } from "roslib";

export interface RobotPose {
  x: number;
  y: number;
  yaw: number;
  linear: number;
  angular: number;
}

export interface RobotScan {
  angleMin: number;
  angleMax: number;
  angleIncrement: number;
  ranges: number[];
  rangeMin: number;
  rangeMax: number;
}

export interface RobotBattery {
  voltage: number;
  percentage: number;
}

/** 轨迹点：世界坐标(米) + 偏航 + 时间戳(秒)，供导出与回放 */
export interface RobotTrajectoryPoint {
  x: number;
  y: number;
  yaw: number;
  t: number;
}

export interface RobotStatus {
  connected: boolean;
  simTime: number;
  pose: RobotPose;
  scan: RobotScan | null;
  battery: RobotBattery;
  odomHz: number;
  scanHz: number;
  /** 世界坐标 (米) 下的位姿轨迹历史，用于地图叠加、导出与回放 */
  poseHistory: RobotTrajectoryPoint[];
}

export type RobotEventListener = (status: RobotStatus) => void;

const DEFAULT_URL = "ws://127.0.0.1:9091";

class RobotBridge {
  private ros: Ros | null = null;
  private listeners = new Set<RobotEventListener>();
  private status: RobotStatus = {
    connected: false,
    simTime: 0,
    pose: { x: 0, y: 0, yaw: 0, linear: 0, angular: 0 },
    scan: null,
    battery: { voltage: 0, percentage: 0 },
    odomHz: 0,
    scanHz: 0,
    poseHistory: [],
  };
  private lastOdomTime = 0;
  private odomCount = 0;
  private lastScanTime = 0;
  private scanCount = 0;
  private lastTrajectoryPoint: RobotTrajectoryPoint | null = null;
  private poseHistory: RobotTrajectoryPoint[] = [];
  private trajectoryT0 = 0;
  private pulseInterval: ReturnType<typeof setInterval> | null = null;

  getStatus(): RobotStatus {
    return this.status;
  }

  isConnected(): boolean {
    return Boolean(this.ros?.isConnected);
  }

  onStatus(listener: RobotEventListener): () => void {
    this.listeners.add(listener);
    listener(this.status);
    return () => this.listeners.delete(listener);
  }

  private emit() {
    this.listeners.forEach((listener) => listener(this.status));
  }

  /** 追加轨迹点：仅在离上一点足够远（≥0.15m）时记录，避免静止时堆点。时间戳以首点为 0。 */
  private pushTrajectory(x: number, y: number, yaw: number) {
    if (this.poseHistory.length === 0) this.trajectoryT0 = Date.now();
    const point: RobotTrajectoryPoint = { x, y, yaw, t: (Date.now() - this.trajectoryT0) / 1000 };
    if (this.lastTrajectoryPoint) {
      const dist = Math.hypot(x - this.lastTrajectoryPoint.x, y - this.lastTrajectoryPoint.y);
      if (dist < 0.15) return;
    }
    this.lastTrajectoryPoint = point;
    this.poseHistory.push(point);
    if (this.poseHistory.length > 4000) this.poseHistory.splice(0, this.poseHistory.length - 4000);
    this.status = { ...this.status, poseHistory: this.poseHistory };
  }

  /** 手动载入历史轨迹（回放/导入用） */
  setPoseHistory(points: RobotTrajectoryPoint[]) {
    this.poseHistory = points;
    this.lastTrajectoryPoint = points.length ? points[points.length - 1] : null;
    this.trajectoryT0 = 0;
    this.status = { ...this.status, poseHistory: this.poseHistory };
    this.emit();
  }

  clearPoseHistory() {
    this.poseHistory = [];
    this.lastTrajectoryPoint = null;
    this.trajectoryT0 = 0;
    this.status = { ...this.status, poseHistory: [] };
    this.emit();
  }

  connect(url = DEFAULT_URL): Promise<void> {
    if (this.ros?.isConnected) return Promise.resolve();
    return new Promise((resolve, reject) => {
      this.ros = new Ros({ url });
      const onConnected = () => {
        this.status = { ...this.status, connected: true };
        this.emit();
        this.cleanup();
        this.subscribe();
        this.startPulse();
        resolve();
      };
      const onError = (error: unknown) => {
        this.status = { ...this.status, connected: false };
        this.emit();
        this.cleanup();
        reject(error instanceof Error ? error : new Error("WebSocket 连接失败"));
      };
      const onClose = () => {
        this.status = { ...this.status, connected: false };
        this.emit();
        this.cleanup();
      };
      this.cleanup = () => {
        this.ros?.removeListener("connection", onConnected);
        this.ros?.removeListener("error", onError);
        this.ros?.removeListener("close", onClose);
      };
      this.ros.on("connection", onConnected);
      this.ros.on("error", onError);
      this.ros.on("close", onClose);
    });
  }

  private cleanup: () => void = () => {};

  disconnect() {
    if (this.ros) {
      this.ros.close();
      this.ros = null;
    }
    if (this.pulseInterval) {
      clearInterval(this.pulseInterval);
      this.pulseInterval = null;
    }
    this.status = { ...this.status, connected: false };
    this.emit();
  }

  private subscribe() {
    if (!this.ros) return;

    const odom = new Topic({
      ros: this.ros,
      name: "/odom",
      messageType: "nav_msgs/msg/Odometry",
    });
    odom.subscribe((message: any) => {
      const { x, y, z, w } = message.pose?.pose?.orientation ?? {};
      const yaw = Math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z));
      this.status = {
        ...this.status,
        pose: {
          x: message.pose?.pose?.position?.x ?? 0,
          y: message.pose?.pose?.position?.y ?? 0,
          yaw,
          linear: message.twist?.twist?.linear?.x ?? 0,
          angular: message.twist?.twist?.angular?.z ?? 0,
        },
      };
      const px = message.pose?.pose?.position?.x ?? 0;
      const py = message.pose?.pose?.position?.y ?? 0;
      this.pushTrajectory(px, py, yaw);
      const now = Date.now();
      this.odomCount++;
      if (this.lastOdomTime === 0 || now - this.lastOdomTime >= 2000) {
        this.status.odomHz = this.lastOdomTime === 0 ? Math.max(1, this.odomCount / 2) : this.odomCount / Math.max(1, (now - this.lastOdomTime) / 1000);
        this.odomCount = 0;
        this.lastOdomTime = now;
      }
      this.emit();
    });

    const scan = new Topic({
      ros: this.ros,
      name: "/scan",
      messageType: "sensor_msgs/msg/LaserScan",
    });
    scan.subscribe((message: any) => {
      this.status = {
        ...this.status,
        scan: {
          angleMin: message.angle_min ?? 0,
          angleMax: message.angle_max ?? 0,
          angleIncrement: message.angle_increment ?? 0,
          ranges: message.ranges ?? [],
          rangeMin: message.range_min ?? 0,
          rangeMax: message.range_max ?? 0,
        },
      };
      const now = Date.now();
      this.scanCount++;
      if (this.lastScanTime === 0 || now - this.lastScanTime >= 2000) {
        this.status.scanHz = this.lastScanTime === 0 ? Math.max(1, this.scanCount / 2) : this.scanCount / Math.max(1, (now - this.lastScanTime) / 1000);
        this.scanCount = 0;
        this.lastScanTime = now;
      }
      this.emit();
    });
  }

  private startPulse() {
    if (this.pulseInterval) return;
    this.pulseInterval = setInterval(() => {
      this.status = { ...this.status, simTime: Date.now() / 1000 };
      this.emit();
    }, 1000);
  }

  /** 发布速度指令到 /cmd_vel（远程遥控用） */
  publishCmdVel(linear: number, angular: number) {
    if (!this.ros?.isConnected) return;
    const topic = new Topic({
      ros: this.ros,
      name: "/cmd_vel",
      messageType: "geometry_msgs/msg/Twist",
    });
    topic.publish({
      linear: { x: linear, y: 0, z: 0 },
      angular: { x: 0, y: 0, z: angular },
    });
  }
}

let instance: RobotBridge | null = null;

export function getRobotBridge(): RobotBridge {
  if (!instance) instance = new RobotBridge();
  return instance;
}
