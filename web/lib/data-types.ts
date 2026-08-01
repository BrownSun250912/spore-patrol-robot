// 跨模块共享的数据类型。这些类型同时被 page.tsx (UI) 与 data-source.ts (数据层) 使用。

export interface EnvironmentSnapshot {
  id: string;
  createdAt: string;
  fieldName: string;
  temperature: number;
  humidity: number;
  soilMoisture: number;
  soilTemperature: number;
  lightIntensity: number;
  rainfall: number;
  leafWetness: number;
  sporeMean: number;
  highRiskCount: number;
  anomalyScore: number;
}

export type AlertStatus = "new" | "acknowledged" | "resolved";

export interface MonitoringAlert {
  id: string;
  createdAt: string;
  fieldName: string;
  level: "notice" | "warning" | "critical";
  type: string;
  message: string;
  status: AlertStatus;
  assignee: string;
  resolution: string;
}

export interface FieldRegistryItem {
  id: string;
  name: string;
  crop: string;
  areaMu: number;
  manager: string;
  lastUpdated: string;
  risk: "low" | "medium" | "high";
  sporeMean: number;
  openAlerts: number;
}

export interface ForecastHistoryRecord {
  id: string;
  createdAt: string;
  fieldName: string;
  p90_3d: number;
  p90_5d: number;
  p90_7d: number;
  meanSpore: number;
  anomalyScore: number;
}
