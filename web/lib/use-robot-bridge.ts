"use client";

import { useEffect, useRef, useState } from "react";
import { getRobotBridge, type RobotStatus, type RobotTrajectoryPoint } from "./robot-bridge";

export interface RobotBridgeState {
  status: RobotStatus;
  connected: boolean;
  connecting: boolean;
  connect: (url?: string) => Promise<void>;
  disconnect: () => void;
  publishCmdVel: (linear: number, angular: number) => void;
  clearPoseHistory: () => void;
  setPoseHistory: (points: RobotTrajectoryPoint[]) => void;
}

/** React hook：订阅机器人实时状态（rosbridge）。页面挂载后自动连接默认地址。 */
export function useRobotBridge(autoConnect = true, url = "ws://127.0.0.1:9091"): RobotBridgeState {
  const bridge = useRef(getRobotBridge());
  const [connected, setConnected] = useState(bridge.current.isConnected());
  const [connecting, setConnecting] = useState(false);
  const [status, setStatus] = useState<RobotStatus>(bridge.current.getStatus());

  useEffect(() => {
    const unsubscribe = bridge.current.onStatus((next) => {
      setStatus(next);
      setConnected(next.connected);
    });
    return unsubscribe;
  }, []);

  useEffect(() => {
    if (autoConnect) {
      const current = bridge.current;
      if (!current.isConnected()) {
        setConnecting(true);
        current.connect(url).catch(() => {}).finally(() => setConnecting(false));
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const connect = (nextUrl?: string) => {
    setConnecting(true);
    return bridge.current.connect(nextUrl ?? url).finally(() => setConnecting(false));
  };

  const disconnect = () => bridge.current.disconnect();
  const publishCmdVel = (linear: number, angular: number) => bridge.current.publishCmdVel(linear, angular);
  const clearPoseHistory = () => bridge.current.clearPoseHistory();
  const setPoseHistory = (points: RobotTrajectoryPoint[]) => bridge.current.setPoseHistory(points);

  return { status, connected, connecting, connect, disconnect, publishCmdVel, clearPoseHistory, setPoseHistory };
}
