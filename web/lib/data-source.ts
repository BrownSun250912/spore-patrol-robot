// 数据层抽象：为"模拟数据源"与"真实数据源（机器人/云端）"提供统一接口。
// 当前 DataSource 用 localStorage 提供离线模拟数据（与 V4 控制台行为一致）；
// 后续接入 rosbridge / HTTP API 时，只需实现同一接口的 LiveSource 即可无缝替换。
// 所有方法均返回 Promise，便于未来切换为异步真实源。

import type { EnvironmentSnapshot, MonitoringAlert, FieldRegistryItem, ForecastHistoryRecord } from "./data-types";

const KEYS = {
  presets: "inspection-presets-v4",
  history: "inspection-history-v4",
  alerts: "monitoring-alerts-v4",
  envHistory: "environment-history-v4",
  fieldRegistry: "field-registry-v4",
  forecastHistory: "forecast-history-v4",
  diseaseRecords: "disease-evaluation-v4",
} as const;

function load<T>(key: string, fallback: T): T {
  if (typeof window === "undefined") return fallback;
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

function save<T>(key: string, value: T): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* 存储满时静默降级：仅本次会话有效 */
  }
}

export interface DataSource {
  // 环境快照
  listEnvironmentSnapshots(): Promise<EnvironmentSnapshot[]>;
  appendEnvironmentSnapshot(snapshot: EnvironmentSnapshot): Promise<EnvironmentSnapshot[]>;
  // 告警
  listAlerts(): Promise<MonitoringAlert[]>;
  appendAlert(alert: MonitoringAlert): Promise<MonitoringAlert[]>;
  updateAlert(alert: MonitoringAlert): Promise<MonitoringAlert[]>;
  // 地块
  listFieldRegistry(): Promise<FieldRegistryItem[]>;
  upsertField(item: FieldRegistryItem): Promise<FieldRegistryItem[]>;
  // 预测历史
  listForecastHistory(): Promise<ForecastHistoryRecord[]>;
  appendForecastHistory(record: ForecastHistoryRecord): Promise<ForecastHistoryRecord[]>;
  // 元信息
  readonly sourceName: string;
  readonly isLive: boolean;
}

/** 离线模拟数据源（localStorage 持久化，行为与当前 V4 控制台一致） */
export class LocalDataSource implements DataSource {
  readonly sourceName = "本地模拟数据源 (localStorage)";
  readonly isLive = false;

  async listEnvironmentSnapshots(): Promise<EnvironmentSnapshot[]> {
    return load<EnvironmentSnapshot[]>(KEYS.envHistory, []);
  }
  async appendEnvironmentSnapshot(snapshot: EnvironmentSnapshot): Promise<EnvironmentSnapshot[]> {
    const next = [...(await this.listEnvironmentSnapshots()), snapshot].slice(-500);
    save(KEYS.envHistory, next);
    return next;
  }

  async listAlerts(): Promise<MonitoringAlert[]> {
    return load<MonitoringAlert[]>(KEYS.alerts, []);
  }
  async appendAlert(alert: MonitoringAlert): Promise<MonitoringAlert[]> {
    const next = [alert, ...(await this.listAlerts())].slice(0, 300);
    save(KEYS.alerts, next);
    return next;
  }
  async updateAlert(updated: MonitoringAlert): Promise<MonitoringAlert[]> {
    const next = (await this.listAlerts()).map((alert) => (alert.id === updated.id ? updated : alert));
    save(KEYS.alerts, next);
    return next;
  }

  async listFieldRegistry(): Promise<FieldRegistryItem[]> {
    return load<FieldRegistryItem[]>(KEYS.fieldRegistry, []);
  }
  async upsertField(item: FieldRegistryItem): Promise<FieldRegistryItem[]> {
    const next = [...(await this.listFieldRegistry()).filter((f) => f.name !== item.name), item];
    save(KEYS.fieldRegistry, next);
    return next;
  }

  async listForecastHistory(): Promise<ForecastHistoryRecord[]> {
    return load<ForecastHistoryRecord[]>(KEYS.forecastHistory, []);
  }
  async appendForecastHistory(record: ForecastHistoryRecord): Promise<ForecastHistoryRecord[]> {
    const next = [...(await this.listForecastHistory()), record].slice(-300);
    save(KEYS.forecastHistory, next);
    return next;
  }
}

let instance: DataSource | null = null;
/** 单例访问入口：后续接入真实源时在这里替换实现即可 */
export function getDataSource(): DataSource {
  if (!instance) instance = new LocalDataSource();
  return instance;
}
