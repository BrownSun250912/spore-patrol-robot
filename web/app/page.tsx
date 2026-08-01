"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  PARAMETER_PRESETS,
  TARGET_GENE_DATABASE,
  buildFusionField,
  classifyRisk,
  classifyStability,
  ctToConcentration,
  pcrVerdict,
  pearsonComparison,
  pointInPolygon,
  polygonArea,
  runForecast,
  simulatePcr,
  simulateTurbidity,
  solvePlanning,
  type ForecastResult,
  type FusionField,
  type PlanParams,
  type PlanningResult,
  type Point,
  type PcrQuality,
  type SamplingPoint,
  type StandardCurve,
  type WeatherParams,
} from "../lib/inspection-engine";
import {
  DISEASE_DATABASE,
  calculateDiseaseMetrics,
  classifyDiseaseImage,
  extractImageFeatures,
  type CropType,
  type DiseaseEvaluationRecord,
  type DiseasePrediction,
} from "../lib/disease-monitoring";
import { parseSlamMap, type SlamMapInfo } from "../lib/slam-map";
import type {
  EnvironmentSnapshot,
  MonitoringAlert,
  FieldRegistryItem,
  ForecastHistoryRecord,
} from "../lib/data-types";
import { getDataSource } from "../lib/data-source";
import { useRobotBridge } from "../lib/use-robot-bridge";
import RobotMonitorPanel from "../components/robot-monitor-panel";

type Tab = "planning" | "sensing" | "pcr" | "disease" | "forecast" | "regulation" | "robot";
type Modal = { title: string; body: React.ReactNode } | null;

interface SavedProject {
  name: string;
  savedAt: string;
  polygon: Point[];
  params: PlanParams;
  planning: PlanningResult | null;
  samples: SamplingPoint[];
  imageUrl: string;
}

const DEFAULT_PLAN: PlanParams = { ...PARAMETER_PRESETS["玉米大田(中)"] };
const DEFAULT_CURVE: StandardCurve = { slope: -3.32, intercept: 38.5, lod: 10, positiveCt: 22.5, negativeCt: 36, gene: "ITS1-F/ITS4-R" };
const DEFAULT_WEATHER: WeatherParams = { windSpeed: 3.5, windDirection: 135, temperature: 25, humidity: 75, cloud: 40, daytime: true, diseaseIndex: 45, lai: 3, plantHeight: 0.8, soilMoisture: 58, soilTemperature: 22, lightIntensity: 36000, rainfall: 0, leafWetness: 62 };
const RISK_TEXT = { low: "低风险", medium: "中风险", high: "高风险", pending: "待检测" } as const;
const QUALITY_TEXT = { valid: "有效", doubtful: "存疑", invalid: "无效", pending: "待录入" } as const;
const ROUND_COLORS = ["#ff9f43", "#00a8ff", "#e056a0", "#f1c40f", "#9b59b6"];
const COVERAGE_PALETTE = ["#2b185f", "#2847a7", "#147dcc", "#10b7c9", "#35d49a", "#b7dd4d", "#ffe36a"];
const RISK_PALETTE = ["#18275f", "#2450a4", "#168ac1", "#10b8a0", "#9bd04b", "#f2c84b", "#f28a38", "#dc3f64"];
const CONCENTRATION_PALETTE = ["#24154f", "#3e3194", "#285fc1", "#1596c1", "#11b59b", "#88ca55", "#efca4a", "#f27c38", "#d9365d"];

function downloadFile(filename: string, content: string, type = "text/plain;charset=utf-8") {
  const link = document.createElement("a");
  link.href = URL.createObjectURL(new Blob([content], { type }));
  link.download = filename;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(link.href), 500);
}

function csvEscape(value: unknown) {
  const text = value == null ? "" : String(value);
  return /[",\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

function toCsv(rows: unknown[][]) {
  return "\ufeff" + rows.map((row) => row.map(csvEscape).join(",")).join("\r\n");
}

function parseCsv(text: string) {
  const rows: string[][] = [];
  let row: string[] = [], cell = "", quoted = false;
  for (let i = 0; i < text.length; i++) {
    const char = text[i];
    if (char === '"') {
      if (quoted && text[i + 1] === '"') { cell += '"'; i++; } else quoted = !quoted;
    } else if (char === "," && !quoted) { row.push(cell.trim()); cell = ""; }
    else if ((char === "\n" || char === "\r") && !quoted) {
      if (char === "\r" && text[i + 1] === "\n") i++;
      row.push(cell.trim()); if (row.some(Boolean)) rows.push(row); row = []; cell = "";
    } else cell += char;
  }
  row.push(cell.trim()); if (row.some(Boolean)) rows.push(row);
  return rows;
}

function numberValue(value: string, fallback: number) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function normalizePcrQuality(value: string, fallback: PcrQuality): PcrQuality {
  const normalized = value.trim().toLowerCase();
  if (["valid", "有效", "合格"].includes(normalized)) return "valid";
  if (["doubtful", "存疑", "可疑"].includes(normalized)) return "doubtful";
  if (["invalid", "无效", "不合格"].includes(normalized)) return "invalid";
  if (["pending", "待录入", "待检测"].includes(normalized)) return "pending";
  return fallback;
}

function rgbaForRisk(risk: string, alpha = 1) {
  if (risk === "high") return `rgba(231,76,60,${alpha})`;
  if (risk === "medium") return `rgba(225,177,44,${alpha})`;
  if (risk === "low") return `rgba(39,174,96,${alpha})`;
  return `rgba(113,128,147,${alpha})`;
}

function heatColor(value: number, palette: readonly string[], alpha = 1) {
  const normalized = Math.max(0, Math.min(1, value));
  const scaled = normalized * (palette.length - 1);
  const index = Math.min(palette.length - 2, Math.floor(scaled));
  const amount = scaled - index;
  const parse = (hex: string) => [Number.parseInt(hex.slice(1, 3), 16), Number.parseInt(hex.slice(3, 5), 16), Number.parseInt(hex.slice(5, 7), 16)];
  const from = parse(palette[index]), to = parse(palette[index + 1]);
  const channel = (i: number) => Math.round(from[i] + (to[i] - from[i]) * amount);
  return `rgba(${channel(0)},${channel(1)},${channel(2)},${alpha})`;
}

function concentrationColor(value: number, alpha = 0.62) {
  const log = Math.log10(Math.max(1, value));
  return heatColor((log - 1) / 5, CONCENTRATION_PALETTE, alpha);
}

function Field({ label, value, onChange, unit, type = "number", min, max, step = "any" }: { label: string; value: string | number; onChange: (value: string) => void; unit?: string; type?: string; min?: number; max?: number; step?: string }) {
  return <label className="field-row"><span>{label}</span><div><input type={type} value={value} min={min} max={max} step={step} onChange={(e) => onChange(e.target.value)} /><em>{unit}</em></div></label>;
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return <section className="control-section"><h3>{title}</h3>{children}</section>;
}

function TrendChart({ records }: { records: EnvironmentSnapshot[] }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = ref.current, context = canvas?.getContext("2d"); if (!canvas || !context) return;
    canvas.width = 720; canvas.height = 240; context.clearRect(0, 0, 720, 240);
    context.fillStyle = "#172129"; context.fillRect(0, 0, 720, 240);
    const points = records.slice(-30), values = points.map((record) => record.sporeMean);
    if (!values.length) { context.fillStyle = "#78909c"; context.font = "15px Microsoft YaHei"; context.textAlign = "center"; context.fillText("记录环境快照后显示孢子浓度历史趋势", 360, 124); return; }
    const max = Math.max(1, ...values) * 1.12, left = 48, right = 700, top = 22, bottom = 205;
    context.strokeStyle = "rgba(145,165,174,.18)"; context.lineWidth = 1;
    for (let row = 0; row <= 4; row++) { const y = top + (bottom - top) * row / 4; context.beginPath(); context.moveTo(left, y); context.lineTo(right, y); context.stroke(); }
    const medianValue = [...values].sort((a, b) => a - b)[Math.floor(values.length / 2)] ?? 0;
    const pointAt = (value: number, index: number) => [left + (right - left) * index / Math.max(1, values.length - 1), bottom - value / max * (bottom - top)] as const;
    context.strokeStyle = "#22c7b8"; context.lineWidth = 3; context.shadowColor = "rgba(34,199,184,.4)"; context.shadowBlur = 8; context.beginPath();
    values.forEach((value, index) => { const [x, y] = pointAt(value, index); if (index) context.lineTo(x, y); else context.moveTo(x, y); }); context.stroke(); context.shadowBlur = 0;
    points.forEach((record, index) => { const [x, y] = pointAt(record.sporeMean, index); context.fillStyle = record.anomalyScore >= 3 ? "#ff5f68" : "#63e6be"; context.beginPath(); context.arc(x, y, record.anomalyScore >= 3 ? 5 : 3, 0, Math.PI * 2); context.fill(); });
    context.setLineDash([5, 4]); context.strokeStyle = "#e7bd51"; const baselineY = bottom - medianValue / max * (bottom - top); context.beginPath(); context.moveTo(left, baselineY); context.lineTo(right, baselineY); context.stroke(); context.setLineDash([]);
    context.fillStyle = "#91a5ae"; context.font = "11px Microsoft YaHei"; context.textAlign = "left"; context.fillText(`中位基线 ${medianValue.toFixed(0)} NTU`, left, 232); context.textAlign = "right"; context.fillText(`最新 ${values.at(-1)?.toFixed(0) ?? "--"} NTU`, right, 232);
  }, [records]);
  return <canvas ref={ref} className="trend-chart" aria-label="孢子浓度历史趋势图" />;
}

export default function InspectionConsole() {
  const [tab, setTab] = useState<Tab>("planning");
  const [status, setStatus] = useState("SYS READY: 导入卫星图 → 标定边界 → 规划路径 → 田间检测 → PCR分析");
  const [modal, setModal] = useState<Modal>(null);
  const [imageUrl, setImageUrl] = useState("");
  const [slamInfo, setSlamInfo] = useState<SlamMapInfo | null>(null);
  const [slamLabel, setSlamLabel] = useState("");
  const [polygon, setPolygon] = useState<Point[]>([]);
  const [drawing, setDrawing] = useState(false);
  const [closed, setClosed] = useState(false);
  const [planParams, setPlanParams] = useState<PlanParams>(DEFAULT_PLAN);
  const [presetName, setPresetName] = useState("玉米大田(中)");
  const [customPresets, setCustomPresets] = useState<Record<string, PlanParams>>(() => {
    if (typeof window === "undefined") return {};
    try { return JSON.parse(localStorage.getItem("inspection-presets-v4") ?? "{}"); } catch { return {}; }
  });
  const [planning, setPlanning] = useState<PlanningResult | null>(null);
  const [samples, setSamples] = useState<SamplingPoint[]>([]);
  const [selectedIndex, setSelectedIndex] = useState(-1);
  const [showGrid, setShowGrid] = useState(true);
  const [showLegend, setShowLegend] = useState(true);
  const [history, setHistory] = useState<SavedProject[]>(() => {
    if (typeof window === "undefined") return [];
    try { return JSON.parse(localStorage.getItem("inspection-history-v4") ?? "[]"); } catch { return []; }
  });
  const [historyName, setHistoryName] = useState("");
  const [view, setView] = useState({ zoom: 1, panX: 0, panY: 0 });
  const [coordinate, setCoordinate] = useState("X: --  Y: --");

  const [mediumThreshold, setMediumThreshold] = useState(150);
  const [highThreshold, setHighThreshold] = useState(400);
  const [scanDelay, setScanDelay] = useState(0.8);
  const [coverageRadius, setCoverageRadius] = useState(20);
  const [simulationMode, setSimulationMode] = useState("uniform");
  const [scanning, setScanning] = useState(false);
  const [scanProgress, setScanProgress] = useState("");

  const [curve, setCurve] = useState<StandardCurve>(DEFAULT_CURVE);
  const [ctInput, setCtInput] = useState("");
  const [dilution, setDilution] = useState(1);
  const [quality, setQuality] = useState<PcrQuality>("valid");
  const [fusionEnabled, setFusionEnabled] = useState(false);

  const [weather, setWeather] = useState<WeatherParams>(DEFAULT_WEATHER);
  const [forecast, setForecast] = useState<ForecastResult | null>(null);
  const [forecastHour, setForecastHour] = useState(72);
  const [cropType, setCropType] = useState<CropType>("小麦");
  const [diseaseImage, setDiseaseImage] = useState("");
  const [diseaseImageName, setDiseaseImageName] = useState("");
  const [diseasePredictions, setDiseasePredictions] = useState<DiseasePrediction[]>([]);
  const [confirmedDiseaseId, setConfirmedDiseaseId] = useState("");
  const [diseaseBrowseId, setDiseaseBrowseId] = useState(DISEASE_DATABASE[0].id);
  const [diseaseRecords, setDiseaseRecords] = useState<DiseaseEvaluationRecord[]>(() => {
    if (typeof window === "undefined") return [];
    try { return JSON.parse(localStorage.getItem("disease-evaluation-v4") ?? "[]"); } catch { return []; }
  });
  const [environmentHistory, setEnvironmentHistory] = useState<EnvironmentSnapshot[]>(() => {
    if (typeof window === "undefined") return [];
    try { return JSON.parse(localStorage.getItem("environment-history-v4") ?? "[]"); } catch { return []; }
  });
  const [alerts, setAlerts] = useState<MonitoringAlert[]>(() => {
    if (typeof window === "undefined") return [];
    try { return JSON.parse(localStorage.getItem("monitoring-alerts-v4") ?? "[]"); } catch { return []; }
  });
  const [fieldRegistry, setFieldRegistry] = useState<FieldRegistryItem[]>(() => {
    if (typeof window === "undefined") return [];
    try { return JSON.parse(localStorage.getItem("field-registry-v4") ?? "[]"); } catch { return []; }
  });
  const [forecastHistory, setForecastHistory] = useState<ForecastHistoryRecord[]>(() => {
    if (typeof window === "undefined") return [];
    try { return JSON.parse(localStorage.getItem("forecast-history-v4") ?? "[]"); } catch { return []; }
  });

  const canvasRef = useRef<HTMLCanvasElement>(null);
  const imageInputRef = useRef<HTMLInputElement>(null);
  const slamInputRef = useRef<HTMLInputElement>(null);
  const slamYamlInputRef = useRef<HTMLInputElement>(null);
  const pendingSlamPgmRef = useRef<File | null>(null);
  const presetInputRef = useRef<HTMLInputElement>(null);
  const sessionInputRef = useRef<HTMLInputElement>(null);
  const pcrInputRef = useRef<HTMLInputElement>(null);
  const diseaseImageInputRef = useRef<HTMLInputElement>(null);
  const scanTimerRef = useRef<number | null>(null);
  const panRef = useRef<{ x: number; y: number; panX: number; panY: number } | null>(null);

  const allPresets = useMemo(() => ({ ...PARAMETER_PRESETS, ...customPresets }), [customPresets]);
  const selected = selectedIndex >= 0 ? samples[selectedIndex] : null;
  const geneInfo = TARGET_GENE_DATABASE[curve.gene];
  const sensingStats = useMemo(() => {
    const done = samples.filter((p) => p.turbidity != null), high = done.filter((p) => p.risk === "high");
    return { total: samples.length, done: done.length, high: high.length, average: done.length ? done.reduce((sum, p) => sum + (p.turbidity ?? 0), 0) / done.length : null };
  }, [samples]);
  const pcrStats = useMemo(() => {
    const done = samples.filter((p) => p.pcr_ct != null), valid = done.filter((p) => p.pcr_qual === "valid");
    return { done: done.length, valid: valid.length, positive: valid.filter((p) => p.pcr_verdict.includes("阳性")).length, negative: valid.filter((p) => p.pcr_verdict === "阴性").length };
  }, [samples]);
  const fusionField: FusionField | null = useMemo(() => {
    if (!planning || polygon.length < 3 || !samples.some((sample) => sample.pcr_conc != null)) return null;
    try { return buildFusionField(polygon, planning, samples, mediumThreshold, highThreshold); }
    catch { return null; }
  }, [highThreshold, mediumThreshold, planning, polygon, samples]);
  const diseaseMetrics = useMemo(() => calculateDiseaseMetrics(diseaseRecords), [diseaseRecords]);
  const selectedDisease = DISEASE_DATABASE.find((disease) => disease.id === diseaseBrowseId) ?? DISEASE_DATABASE[0];
  const openAlerts = useMemo(() => alerts.filter((alert) => alert.status !== "resolved"), [alerts]);

  useEffect(() => () => { if (scanTimerRef.current) window.clearTimeout(scanTimerRef.current); }, []);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        if (scanTimerRef.current) window.clearTimeout(scanTimerRef.current);
        scanTimerRef.current = null; setScanning(false); setScanProgress("已手动停止");
      }
      if (tab === "planning" && event.ctrlKey && event.key.toLowerCase() === "z") {
        event.preventDefault(); setPolygon((old) => old.slice(0, -1)); setClosed(false);
      }
      if (tab === "planning" && event.ctrlKey && event.key.toLowerCase() === "s") {
        event.preventDefault();
        const content = JSON.stringify({ generated_at: new Date().toISOString(), params: planParams, field_polygon_m: planning?.fieldPolygonMeters ?? [], sampling_points: samples, route_segments: planning?.roundSegments ?? [] }, null, 2);
        downloadFile("planning.json", content, "application/json");
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [planParams, planning, samples, tab]);

  const showMessage = useCallback((title: string, body: React.ReactNode) => setModal({ title, body }), []);

  const drawMap = useCallback((background?: HTMLImageElement) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    canvas.width = 1000; canvas.height = 700;
    ctx.imageSmoothingEnabled = true; ctx.imageSmoothingQuality = "high";
    ctx.fillStyle = "#15191c"; ctx.fillRect(0, 0, 1000, 700);
    ctx.save(); ctx.translate(view.panX, view.panY); ctx.scale(view.zoom, view.zoom);
    if (background) {
      // Keep the uploaded orthophoto's native aspect ratio. The previous
      // implementation forced every image into 1000×700, which stretched
      // portrait or panoramic imagery before the overlay was rendered.
      ctx.fillStyle = "#10171c"; ctx.fillRect(0, 0, 1000, 700);
      const sourceWidth = background.naturalWidth || background.width;
      const sourceHeight = background.naturalHeight || background.height;
      const fit = Math.min(1000 / sourceWidth, 700 / sourceHeight);
      const drawWidth = sourceWidth * fit, drawHeight = sourceHeight * fit;
      ctx.drawImage(background, (1000 - drawWidth) / 2, (700 - drawHeight) / 2, drawWidth, drawHeight);
    }
    else {
      ctx.fillStyle = "#1a2023"; ctx.fillRect(0, 0, 1000, 700);
      ctx.strokeStyle = "rgba(113,128,147,.12)"; ctx.lineWidth = 1;
      for (let x = 0; x <= 1000; x += 40) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, 700); ctx.stroke(); }
      for (let y = 0; y <= 700; y += 40) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(1000, y); ctx.stroke(); }
      ctx.fillStyle = "#718093"; ctx.font = "16px Microsoft YaHei"; ctx.textAlign = "center";
      ctx.fillText("可导入卫星图，也可直接在格网上标定农田边界", 500, 345);
    }

    const drawPolygon = () => {
      if (!polygon.length) return;
      ctx.strokeStyle = "#00ecc6"; ctx.lineWidth = 2 / view.zoom; ctx.setLineDash([8 / view.zoom, 4 / view.zoom]);
      ctx.beginPath(); polygon.forEach(([x, y], i) => i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)); if (closed) ctx.closePath(); ctx.stroke(); ctx.setLineDash([]);
      polygon.forEach(([x, y], i) => { ctx.fillStyle = i < 2 ? "#e1b12c" : "#00ecc6"; ctx.beginPath(); ctx.arc(x, y, 5 / view.zoom, 0, Math.PI * 2); ctx.fill(); ctx.fillStyle = "#dcdde1"; ctx.font = `${11 / view.zoom}px Consolas`; ctx.fillText(String(i + 1), x + 9 / view.zoom, y - 8 / view.zoom); });
    };

    if (planning && tab === "planning" && showGrid) {
      planning.evaluationGrid.forEach(([x, y], i) => {
        const confidence = planning.cumulativeConfidence[i] ?? 0;
        ctx.fillStyle = heatColor(confidence, COVERAGE_PALETTE, .44);
        const cell = planning.gridStepPx + .8;
        ctx.fillRect(x - cell / 2, y - cell / 2, cell, cell);
      });
    }

    if (tab === "sensing" && samples.some((p) => p.turbidity != null) && polygon.length >= 3) {
      for (let x = 0; x < 1000; x += 10) for (let y = 0; y < 700; y += 10) {
        if (!pointInPolygon([x, y], polygon)) continue;
        let weights = 0, value = 0;
        samples.forEach((point) => { if (point.turbidity == null) return; const d2 = Math.max(1, (x - point.real_xy[0]) ** 2 + (y - point.real_xy[1]) ** 2); const w = 1 / d2; weights += w; value += w * point.turbidity; });
        if (weights) {
          const turbidity = value / weights;
          const normalized = turbidity / Math.max(1, highThreshold * 1.35);
          ctx.fillStyle = heatColor(normalized, RISK_PALETTE, .4);
          ctx.fillRect(x, y, 10.8, 10.8);
        }
      }
    }

    if (tab === "pcr" && fusionEnabled && fusionField && planning && polygon.length >= 3) {
      const fieldValues = fusionField.concentrations.filter((_, index) => fusionField.inside[index]);
      const sorted = [...fieldValues].sort((a, b) => a - b), p95 = sorted[Math.floor((sorted.length - 1) * .95)] ?? 10;
      const logCeiling = Math.max(1.2, Math.log10(Math.max(10, p95)));
      ctx.save(); ctx.beginPath(); polygon.forEach(([x, y], index) => index ? ctx.lineTo(x, y) : ctx.moveTo(x, y)); ctx.closePath(); ctx.clip();
      fusionField.grid.forEach(([mx, my], index) => {
        const x = planning.reference[0] + mx * planning.scale, y = planning.reference[1] + my * planning.scale;
        const size = fusionField.gridStep * planning.scale + 1.8;
        const normalized = (Math.log10(Math.max(1, fusionField.concentrations[index])) - .6) / Math.max(.6, logCeiling - .6);
        const confidence = fusionField.reliabilities[index];
        ctx.fillStyle = heatColor(normalized, CONCENTRATION_PALETTE, .38 + .16 * confidence); ctx.fillRect(x - size / 2, y - size / 2, size, size);
      });
      ctx.restore();
    }

    if (tab === "forecast" && forecast && planning) {
      const slice = forecast[forecastHour];
      const sharedCeiling = Math.max(10, ...Object.values(forecast).flatMap((item) => [item.p90, item.peak * .7]));
      const logCeiling = Math.max(1.2, Math.log10(sharedCeiling));
      ctx.save(); ctx.beginPath(); polygon.forEach(([x, y], index) => index ? ctx.lineTo(x, y) : ctx.moveTo(x, y)); ctx.closePath(); ctx.clip();
      slice?.grid.forEach(([mx, my], index) => {
        const x = planning.reference[0] + mx * planning.scale, y = planning.reference[1] + my * planning.scale;
        const size = Math.max(3, slice.gridStep * planning.scale + 1.8);
        const normalized = (Math.log10(Math.max(1, slice.concentrations[index])) - .6) / Math.max(.6, logCeiling - .6);
        ctx.fillStyle = heatColor(normalized, CONCENTRATION_PALETTE, .56); ctx.fillRect(x - size / 2, y - size / 2, size, size);
      });
      ctx.restore();
    }

    drawPolygon();
    if (planning && tab === "planning") planning.roundSegments.forEach((segments, round) => segments.forEach((segment) => {
      ctx.strokeStyle = ROUND_COLORS[round % ROUND_COLORS.length]; ctx.lineWidth = 2.2 / view.zoom;
      ctx.beginPath(); segment.waypoints.forEach(([x, y], i) => i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)); ctx.stroke();
    }));

    if (samples.length) {
      samples.forEach((point, index) => {
        const [x, y] = point.real_xy;
        if (tab === "sensing") {
          const radius = planning ? coverageRadius * planning.scale : 12;
          ctx.strokeStyle = rgbaForRisk(point.risk, .28); ctx.lineWidth = 1 / view.zoom; ctx.beginPath(); ctx.arc(x, y, radius, 0, Math.PI * 2); ctx.stroke();
        }
        const color = tab === "planning"
          ? ROUND_COLORS[Math.max(0, point.round - 1) % ROUND_COLORS.length]
          : tab === "pcr" && point.pcr_ct != null
            ? (point.pcr_qual === "valid" ? concentrationColor(point.pcr_conc ?? 1) : "#e1b12c")
            : rgbaForRisk(point.risk);
        const radius = (index === selectedIndex ? 8.5 : 6.5) / view.zoom;
        ctx.save(); ctx.shadowColor = color; ctx.shadowBlur = (index === selectedIndex ? 18 : 10) / view.zoom;
        ctx.fillStyle = "rgba(12,18,23,.9)"; ctx.beginPath(); ctx.arc(x, y, radius + 2.5 / view.zoom, 0, Math.PI * 2); ctx.fill();
        ctx.fillStyle = index === selectedIndex ? "#ffffff" : color; ctx.strokeStyle = index === selectedIndex ? color : "rgba(255,255,255,.86)"; ctx.lineWidth = 1.6 / view.zoom;
        ctx.beginPath(); ctx.arc(x, y, radius, 0, Math.PI * 2); ctx.fill(); ctx.stroke(); ctx.restore();
        ctx.fillStyle = "#f2f7f8"; ctx.strokeStyle = "rgba(8,12,16,.82)"; ctx.lineWidth = 3 / view.zoom; ctx.font = `600 ${10 / view.zoom}px Consolas`; ctx.textAlign = "left";
        ctx.strokeText(point.point_id, x + 10 / view.zoom, y - 8 / view.zoom); ctx.fillText(point.point_id, x + 10 / view.zoom, y - 8 / view.zoom);
      });
    }

    if (tab === "forecast") {
      const radians = weather.windDirection * Math.PI / 180, ox = 920, oy = 75;
      ctx.strokeStyle = "#00ecc6"; ctx.fillStyle = "#00ecc6"; ctx.lineWidth = 3 / view.zoom;
      const tx = ox + Math.sin(radians) * 42, ty = oy - Math.cos(radians) * 42;
      ctx.beginPath(); ctx.moveTo(ox, oy); ctx.lineTo(tx, ty); ctx.stroke(); ctx.beginPath(); ctx.arc(tx, ty, 4, 0, Math.PI * 2); ctx.fill();
      ctx.font = "12px Microsoft YaHei"; ctx.fillText(`风 ${weather.windDirection}°  ${weather.windSpeed}m/s`, 835, 25);
    }

    if (showLegend && polygon.length && ["planning", "sensing", "pcr", "forecast"].includes(tab)) {
      ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0);
      const palette = tab === "planning" ? COVERAGE_PALETTE : tab === "sensing" ? RISK_PALETTE : CONCENTRATION_PALETTE;
      const legendTitle = tab === "planning" ? "覆盖置信度" : tab === "sensing" ? "浊度风险强度" : tab === "pcr" ? "PCR 浓度强度" : `${forecastHour / 24}天扩散风险`;
      const lowLabel = tab === "planning" ? "低覆盖" : "低";
      const highLabel = tab === "planning" ? "高覆盖" : "高";
      ctx.fillStyle = "rgba(12,18,23,.9)"; ctx.strokeStyle = "rgba(130,164,177,.65)"; ctx.lineWidth = 1; ctx.fillRect(20, 618, 286, 64); ctx.strokeRect(20.5, 618.5, 285, 63);
      ctx.fillStyle = "#dbe9ed"; ctx.font = "600 10px Microsoft YaHei"; ctx.textAlign = "left"; ctx.fillText(legendTitle, 34, 636);
      const gradient = ctx.createLinearGradient(34, 0, 292, 0); palette.forEach((color, i) => gradient.addColorStop(i / (palette.length - 1), color));
      ctx.fillStyle = gradient; ctx.fillRect(34, 644, 258, 12); ctx.strokeStyle = "rgba(255,255,255,.28)"; ctx.strokeRect(34.5, 644.5, 257, 11);
      ctx.fillStyle = "#91a5ad"; ctx.font = "9px Microsoft YaHei"; ctx.fillText(lowLabel, 34, 671); ctx.textAlign = "right"; ctx.fillText(highLabel, 292, 671); ctx.restore();
    }
    ctx.restore();
  }, [closed, coverageRadius, forecast, forecastHour, fusionEnabled, fusionField, highThreshold, planning, polygon, samples, selectedIndex, showGrid, showLegend, tab, view, weather]);

  useEffect(() => {
    if (!imageUrl) { drawMap(); return; }
    const image = new Image(); image.onload = () => drawMap(image); image.src = imageUrl;
  }, [drawMap, imageUrl]);

  function canvasPoint(event: React.PointerEvent<HTMLCanvasElement> | React.MouseEvent<HTMLCanvasElement>) {
    const rect = canvasRef.current!.getBoundingClientRect();
    const screenX = (event.clientX - rect.left) * (1000 / rect.width), screenY = (event.clientY - rect.top) * (700 / rect.height);
    return [(screenX - view.panX) / view.zoom, (screenY - view.panY) / view.zoom] as Point;
  }

  function onCanvasClick(event: React.MouseEvent<HTMLCanvasElement>) {
    if (panRef.current) return;
    const point = canvasPoint(event);
    if (tab === "planning" && drawing && !closed) { setPolygon((old) => [...old, point]); setPlanning(null); setSamples([]); return; }
    let best = -1, distance = Infinity;
    samples.forEach((sample, index) => { const d = Math.hypot(point[0] - sample.real_xy[0], point[1] - sample.real_xy[1]); if (d < distance) { best = index; distance = d; } });
    if (best >= 0 && distance < 30 / view.zoom) { setSelectedIndex(best); setCtInput(samples[best].pcr_ct?.toString() ?? ""); setQuality(samples[best].pcr_qual === "pending" ? "valid" : samples[best].pcr_qual); }
  }

  function onPointerDown(event: React.PointerEvent<HTMLCanvasElement>) {
    if (event.button === 1 || (event.button === 0 && event.shiftKey)) { panRef.current = { x: event.clientX, y: event.clientY, panX: view.panX, panY: view.panY }; event.currentTarget.setPointerCapture(event.pointerId); }
  }

  function onPointerMove(event: React.PointerEvent<HTMLCanvasElement>) {
    const point = canvasPoint(event); setCoordinate(`X: ${point[0].toFixed(1)} px  Y: ${point[1].toFixed(1)} px`);
    if (panRef.current) setView((old) => ({ ...old, panX: panRef.current!.panX + event.clientX - panRef.current!.x, panY: panRef.current!.panY + event.clientY - panRef.current!.y }));
  }

  function onPointerUp() { panRef.current = null; }

  function updatePlan<K extends keyof PlanParams>(key: K, value: string) { setPlanParams((old) => ({ ...old, [key]: numberValue(value, old[key]) })); }
  function updateCurve<K extends keyof StandardCurve>(key: K, value: StandardCurve[K]) { setCurve((old) => ({ ...old, [key]: value })); }
  function updateWeather<K extends keyof WeatherParams>(key: K, value: WeatherParams[K]) { setWeather((old) => ({ ...old, [key]: value })); }

  const dataSource = useMemo(() => getDataSource(), []);

  function addAlert(level: MonitoringAlert["level"], type: string, message: string, fieldName = historyName || "当前地块") {
    const alert: MonitoringAlert = { id: `ALT-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`, createdAt: new Date().toISOString(), fieldName, level, type, message, status: "new", assignee: "", resolution: "" };
    void dataSource.appendAlert(alert).then((next) => setAlerts(next));
  }

  function updateAlertStatus(id: string, statusValue: "new" | "acknowledged" | "resolved") {
    const assignee = statusValue === "acknowledged" ? window.prompt("请输入处置负责人：", "农业技术员")?.trim() ?? "" : "";
    const resolution = statusValue === "resolved" ? window.prompt("请输入处置结果：", "已完成现场复核与定点防控")?.trim() ?? "" : "";
    if (statusValue === "acknowledged" && !assignee) return;
    if (statusValue === "resolved" && !resolution) return;
    setAlerts((old) => {
      const next = old.map((alert) => alert.id === id ? { ...alert, status: statusValue, assignee: assignee || alert.assignee, resolution: resolution || alert.resolution } : alert);
      const target = next.find((alert) => alert.id === id);
      if (target) void dataSource.updateAlert(target).then((latest) => setAlerts(latest));
      return next;
    });
  }

  function calculateAnomalyScore(current: number, fieldName: string) {
    const baseline = environmentHistory.filter((record) => record.fieldName === fieldName && record.sporeMean > 0).slice(-20).map((record) => record.sporeMean);
    if (baseline.length < 4) return current > highThreshold ? 3.1 : current > mediumThreshold ? 1.8 : 0;
    const ordered = [...baseline].sort((a, b) => a - b), center = ordered[Math.floor(ordered.length / 2)];
    const deviations = baseline.map((value) => Math.abs(value - center)).sort((a, b) => a - b), mad = Math.max(1, deviations[Math.floor(deviations.length / 2)] * 1.4826);
    return Math.max(0, (current - center) / mad);
  }

  function recordEnvironmentSnapshot() {
    const fieldName = historyName || "当前地块", sporeMean = sensingStats.average ?? 0, anomalyScore = calculateAnomalyScore(sporeMean, fieldName);
    const snapshot: EnvironmentSnapshot = { id: `ENV-${Date.now()}`, createdAt: new Date().toISOString(), fieldName, temperature: weather.temperature, humidity: weather.humidity, soilMoisture: weather.soilMoisture, soilTemperature: weather.soilTemperature, lightIntensity: weather.lightIntensity, rainfall: weather.rainfall, leafWetness: weather.leafWetness, sporeMean, highRiskCount: sensingStats.high, anomalyScore };
    void dataSource.appendEnvironmentSnapshot(snapshot).then((next) => setEnvironmentHistory(next));
    if (anomalyScore >= 3) addAlert("critical", "孢子浓度异常", `孢子均值 ${sporeMean.toFixed(1)} NTU，稳健异常分数 ${anomalyScore.toFixed(1)}。`, fieldName);
    else if (sensingStats.high > 0) addAlert("warning", "高风险采样点", `检测到 ${sensingStats.high} 个高风险采样点，建议进行PCR复核。`, fieldName);
    setStatus(`ENV SNAPSHOT: ${fieldName} 已记录，异常分数 ${anomalyScore.toFixed(1)}。`);
  }

  function registerCurrentField() {
    const name = window.prompt("地块名称：", historyName || `监管地块-${fieldRegistry.length + 1}`)?.trim(); if (!name) return;
    const manager = window.prompt("负责人：", "农业技术员")?.trim() || "未指定";
    const areaMu = planning ? polygonArea(polygon) / planning.scale ** 2 / 666.67 : 0;
    const risk: FieldRegistryItem["risk"] = sensingStats.high > 0 || openAlerts.some((alert) => alert.fieldName === name && alert.level === "critical") ? "high" : sensingStats.done ? "medium" : "low";
    const item: FieldRegistryItem = { id: fieldRegistry.find((field) => field.name === name)?.id ?? `FIELD-${Date.now()}`, name, crop: cropType, areaMu, manager, lastUpdated: new Date().toISOString(), risk, sporeMean: sensingStats.average ?? 0, openAlerts: openAlerts.filter((alert) => alert.fieldName === name).length };
    void dataSource.upsertField(item).then((next) => setFieldRegistry(next)); setStatus(`FIELD REGISTRY: ${name} 已加入监管。`);
  }

  async function analyzeDiseaseImage(file?: File) {
    if (!file) return;
    const source = await new Promise<string>((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(String(reader.result)); reader.onerror = reject; reader.readAsDataURL(file); });
    const image = await new Promise<HTMLImageElement>((resolve, reject) => { const element = new Image(); element.onload = () => resolve(element); element.onerror = reject; element.src = source; });
    const features = extractImageFeatures(image), predictions = classifyDiseaseImage(features, cropType);
    const thumbnail = document.createElement("canvas"), context = thumbnail.getContext("2d"); thumbnail.width = 320; thumbnail.height = 220;
    if (context) { context.fillStyle = "#10171c"; context.fillRect(0, 0, 320, 220); const scale = Math.min(320 / image.width, 220 / image.height), width = image.width * scale, height = image.height * scale; context.drawImage(image, (320 - width) / 2, (220 - height) / 2, width, height); }
    setDiseaseImage(thumbnail.toDataURL("image/jpeg", .78)); setDiseaseImageName(file.name); setDiseasePredictions(predictions); setConfirmedDiseaseId(""); if (predictions[0]) setDiseaseBrowseId(predictions[0].diseaseId);
    setStatus(`IMAGE ANALYSIS: ${file.name} → ${predictions[0]?.name ?? "无法识别"}`);
  }

  function confirmDiseaseEvaluation() {
    if (!diseasePredictions.length || !confirmedDiseaseId || !diseaseImage) { showMessage("真实标签确认", "请先分析图片，并选择人工复核后的真实病害标签。"); return; }
    const image = new Image(); image.onload = () => {
      const record: DiseaseEvaluationRecord = { id: `IMG-${Date.now()}`, createdAt: new Date().toISOString(), fieldName: historyName || "当前地块", crop: cropType, imageName: diseaseImageName, imageUrl: diseaseImage, predictedId: diseasePredictions[0].diseaseId, confidence: diseasePredictions[0].confidence, confirmedId: confirmedDiseaseId, features: extractImageFeatures(image) };
      const next = [record, ...diseaseRecords].slice(0, 200); setDiseaseRecords(next); localStorage.setItem("disease-evaluation-v4", JSON.stringify(next));
      const truth = DISEASE_DATABASE.find((disease) => disease.id === confirmedDiseaseId); setDiseaseBrowseId(confirmedDiseaseId); addAlert("warning", "病害影像复核", `人工确认：${truth?.name ?? confirmedDiseaseId}；图像模型预测：${diseasePredictions[0].name}。`);
      setStatus(`GROUND TRUTH SAVED: 当前真实评估样本 ${next.length} 条。`);
    }; image.src = diseaseImage;
  }

  function loadImage(file?: File) {
    if (!file) return;
    const reader = new FileReader(); reader.onload = () => { setImageUrl(String(reader.result)); setSlamInfo(null); setSlamLabel(""); setStatus(`IMAGE LOADED: ${file.name}`); }; reader.readAsDataURL(file);
  }

  async function loadSlamMap(pgmFile?: File) {
    if (!pgmFile) return;
    pendingSlamPgmRef.current = pgmFile;
    const yamlFile = slamYamlInputRef.current?.files?.[0];
    let yamlText = "";
    if (yamlFile) yamlText = await yamlFile.text().catch(() => "");
    try {
      const parsed = await parseSlamMap(pgmFile, yamlText);
      setImageUrl(parsed.imageUrl);
      setSlamInfo(parsed.info);
      setSlamLabel(yamlFile?.name ? `${pgmFile.name} + ${yamlFile.name}` : pgmFile.name);
      setPolygon([]); setClosed(false); setPlanning(null); setSamples([]); setSelectedIndex(-1);
      const originText = `原点(${parsed.info.origin[0].toFixed(2)}, ${parsed.info.origin[1].toFixed(2)})m`;
      const resText = parsed.hasResolution ? `分辨率 ${parsed.info.resolution} m/px` : "未提供 YAML，分辨率按 0.05 m/px";
      setStatus(`SLAM MAP LOADED: ${parsed.info.width}×${parsed.info.height}px，${resText}，${originText}。请标定边界（首边长度将按分辨率换算）。`);
    } catch (error) {
      showMessage("地图载入失败", error instanceof Error ? error.message : "PGM 文件无法解析。");
    }
  }

  async function selectSlamYaml() {
    const yamlFile = slamYamlInputRef.current?.files?.[0];
    if (!yamlFile) { showMessage("选择 YAML", "请先选择 .yaml 元数据文件，再点击确认。"); return; }
    // 若已载入 PGM，重新解析以应用真实分辨率
    if (pendingSlamPgmRef.current) {
      await loadSlamMap(pendingSlamPgmRef.current);
    } else {
      setStatus(`YAML SELECTED: ${yamlFile.name}。请先导入对应的 .pgm 地图。`);
    }
  }

  function closePolygon() {
    if (polygon.length < 3) { showMessage("边界错误", "至少需要 3 个顶点才能闭合农田边界。"); return; }
    // SLAM 地图模式下：首边像素长度 × 分辨率 = 真实米数，自动更新基准边长，
    // 使规划坐标直接落在真实世界坐标系（米）。
    if (slamInfo) {
      const reference = polygon[0], second = polygon[1];
      const refPixels = Math.hypot(second[0] - reference[0], second[1] - reference[1]);
      const refMeters = refPixels * slamInfo.resolution;
      if (refMeters > 0.1) {
        setPlanParams((old) => ({ ...old, refLength: Math.round(refMeters * 100) / 100 }));
        setStatus(`BOUNDARY CLOSED: ${polygon.length} 个顶点。SLAM 分辨率 ${slamInfo.resolution} m/px，首边 ${refPixels.toFixed(0)}px → ${refMeters.toFixed(2)}m，比例尺已自动换算。`);
        setClosed(true); setDrawing(false); return;
      }
    }
    setClosed(true); setDrawing(false); setStatus(`BOUNDARY CLOSED: ${polygon.length} 个顶点，首边将作为比例尺与垄向。`);
  }

  function solve() {
    if (!closed) { showMessage("路径规划", "请先闭合农田边界。"); return; }
    try {
      setStatus("CALCULATING: 正在生成垄线候选池与覆盖矩阵...");
      const result = solvePlanning(polygon, planParams); setPlanning(result); setSamples(result.samplingPoints); setSelectedIndex(-1);
      setStatus(`PLANNING DONE: ${planParams.rounds}轮 × ~${planParams.samplesPerRound}点 | 覆盖率 ${result.coveragePct.toFixed(1)}% | 均置信度 ${result.averageConfidence.toFixed(3)} | 总路程 ${result.totalDistance.toFixed(0)}m | 总时间 ${result.totalTime.toFixed(0)}s`);
    } catch (error) { showMessage("规划失败", error instanceof Error ? error.message : String(error)); }
  }

  function clearAll() {
    if (!window.confirm("确认清空边界、规划、检测、PCR和预测数据？")) return;
    stopScan(); setPolygon([]); setClosed(false); setDrawing(false); setPlanning(null); setSamples([]); setSelectedIndex(-1); setForecast(null); setImageUrl(""); setStatus("RESET: 当前工作区已清空。");
  }

  function saveProject() {
    if (!polygon.length) { showMessage("保存项目", "当前没有地块数据。"); return; }
    const name = window.prompt("请输入项目名称：", historyName || `巡检地块-${new Date().toLocaleDateString()}`)?.trim(); if (!name) return;
    const project: SavedProject = { name, savedAt: new Date().toISOString(), polygon, params: planParams, planning, samples, imageUrl };
    const next = [...history.filter((item) => item.name !== name), project];
    try { localStorage.setItem("inspection-history-v4", JSON.stringify(next)); setHistory(next); setHistoryName(name); setStatus(`PROJECT SAVED: ${name}`); }
    catch { showMessage("保存失败", "浏览器存储空间不足。可先使用“保存工作会话”下载 JSON 文件。"); }
  }

  function loadProject(name: string) {
    const project = history.find((item) => item.name === name); if (!project) return;
    stopScan(); setHistoryName(name); setPolygon(project.polygon); setClosed(project.polygon.length >= 3); setPlanParams(project.params); setPlanning(project.planning); setSamples(project.samples); setImageUrl(project.imageUrl ?? ""); setForecast(null); setSelectedIndex(-1); setStatus(`PROJECT LOADED: ${name}`);
  }

  function deleteProject() {
    if (!historyName || !window.confirm(`删除项目“${historyName}”？`)) return;
    const next = history.filter((item) => item.name !== historyName); localStorage.setItem("inspection-history-v4", JSON.stringify(next)); setHistory(next); setHistoryName(""); setStatus("PROJECT DELETED");
  }

  function savePreset() {
    const name = window.prompt("请输入预设名称：")?.trim(); if (!name) return;
    const next = { ...customPresets, [name]: planParams }; setCustomPresets(next); localStorage.setItem("inspection-presets-v4", JSON.stringify(next)); setPresetName(name); setStatus(`PRESET SAVED: ${name}`);
  }

  async function importPreset(file?: File) {
    if (!file) return;
    try { const data = JSON.parse(await file.text()) as Record<string, PlanParams>; const next = { ...customPresets, ...data }; setCustomPresets(next); localStorage.setItem("inspection-presets-v4", JSON.stringify(next)); setStatus(`PRESETS LOADED: ${Object.keys(data).length} 个预设。`); }
    catch { showMessage("载入失败", "JSON 预设文件格式不正确。"); }
  }

  function planningJson() {
    return JSON.stringify({ generated_at: new Date().toISOString(), params: planParams, field_polygon_m: planning?.fieldPolygonMeters ?? [], coverage_pct: planning?.coveragePct ?? 0, average_confidence: planning?.averageConfidence ?? 0, total_distance_m: planning?.totalDistance ?? 0, total_time_s: planning?.totalTime ?? 0, sampling_points: samples, route_segments: planning?.roundSegments ?? [] }, null, 2);
  }

  function planningReport() {
    return [`多模态智能巡检系统 - 路径规划报告`, `生成时间: ${new Date().toLocaleString()}`, `地块面积: ${planning ? polygonArea(polygon) / planning.scale ** 2 : 0} m²`, `参数: 基准边${planParams.refLength}m 垄距${planParams.ridgeDistance}m 半径${planParams.sporeRadius}m`, `采集轮次: ${planParams.rounds}，每轮目标点数: ${planParams.samplesPerRound}`, `采样点数: ${samples.length}`, `覆盖率: ${planning?.coveragePct.toFixed(2) ?? "--"}%`, `平均置信度: ${planning?.averageConfidence.toFixed(4) ?? "--"}`, `总路程: ${planning?.totalDistance.toFixed(2) ?? "--"}m`, `预计时间: ${planning?.totalTime.toFixed(1) ?? "--"}s`, "", ...samples.map((p) => `${p.point_id}\tX=${p.x_m}m\tY=${p.y_m}m\t垄=${p.ridge_idx}`)].join("\n");
  }

  function saveSession() {
    downloadFile("inspection_session.json", JSON.stringify({ version: 5, imageUrl, polygon, closed, planParams, planning, samples, curve, weather, forecast, diseaseRecords, environmentHistory, alerts, fieldRegistry, forecastHistory }, null, 2), "application/json"); setStatus("SESSION SAVED: inspection_session.json");
  }

  async function restoreSession(file?: File) {
    if (!file) return;
    try {
      const data = JSON.parse(await file.text()); stopScan(); setImageUrl(data.imageUrl ?? ""); setPolygon(data.polygon ?? []); setClosed(Boolean(data.closed)); setPlanParams(data.planParams ?? DEFAULT_PLAN); setPlanning(data.planning ?? null); setSamples(data.samples ?? []); setCurve(data.curve ?? DEFAULT_CURVE); setWeather({ ...DEFAULT_WEATHER, ...(data.weather ?? {}) }); setForecast(data.forecast ?? null); setDiseaseRecords(data.diseaseRecords ?? diseaseRecords); setEnvironmentHistory(data.environmentHistory ?? environmentHistory); setAlerts(data.alerts ?? alerts); setFieldRegistry(data.fieldRegistry ?? fieldRegistry); setForecastHistory(data.forecastHistory ?? forecastHistory); setSelectedIndex(-1); setStatus("SESSION RESTORED");
    } catch { showMessage("恢复失败", "工作会话 JSON 无法解析。"); }
  }

  function performReading(index: number) {
    if (!planning || !samples[index]) return;
    setSamples((old) => old.map((point, i) => {
      if (i !== index) return point;
      const turbidity = simulateTurbidity(point, old, polygon, planning.scale, planning.reference, simulationMode);
      return { ...point, turbidity, risk: classifyRisk(turbidity, mediumThreshold, highThreshold), read_time: new Date().toLocaleTimeString("zh-CN", { hour12: false }) };
    }));
    setSelectedIndex(index);
  }

  function readSingle() {
    if (selectedIndex < 0) { showMessage("田间检测", "请先在地图或表格中选中一个采样点。"); return; }
    performReading(selectedIndex); setStatus(`SENSOR READ: ${samples[selectedIndex].point_id}`);
  }

  function stopScan() {
    if (scanTimerRef.current) window.clearTimeout(scanTimerRef.current); scanTimerRef.current = null; setScanning(false); setScanProgress((old) => old ? "已手动停止" : "");
  }

  function startScan() {
    if (!planning) { showMessage("一键全检", "请先完成路径规划。"); return; }
    const indices = samples.map((p, i) => p.turbidity == null ? i : -1).filter((i) => i >= 0);
    if (!indices.length) { showMessage("一键全检", "所有采样点均已完成检测。"); return; }
    setScanning(true); setStatus(`SCANNING: 共 ${indices.length} 个待测点...`);
    const step = (position: number) => {
      if (position >= indices.length) { setScanning(false); setScanProgress("全检完成"); setStatus("SCAN COMPLETE: 全部待测点已完成检测。"); return; }
      performReading(indices[position]); setScanProgress(`巡检进度: ${position + 1} / ${indices.length}`);
      scanTimerRef.current = window.setTimeout(() => step(position + 1), Math.max(50, scanDelay * 1000));
    };
    step(0);
  }

  function applyThresholds() {
    if (mediumThreshold <= 0 || highThreshold <= mediumThreshold || coverageRadius <= 0) { showMessage("输入错误", "需满足：0 < 中风险 < 高风险，覆盖半径 > 0。"); return; }
    setSamples((old) => old.map((p) => p.turbidity == null ? p : { ...p, risk: classifyRisk(p.turbidity, mediumThreshold, highThreshold) })); setStatus(`阈值已更新: 中风险 > ${mediumThreshold} NTU，高风险 > ${highThreshold} NTU。`);
  }

  function resetReadings() {
    if (!window.confirm("确认清除全部传感器读数？")) return; stopScan(); setSamples((old) => old.map((p) => ({ ...p, turbidity: null, risk: "pending", read_time: "" }))); setSelectedIndex(-1); setStatus("RESET: 传感器读数已清除。");
  }

  function sensingCsv() {
    return toCsv([["采样点编号", "X(m)", "Y(m)", "垄索引", "浊度(NTU)", "风险等级", "检测时间"], ...samples.map((p) => [p.point_id, p.x_m, p.y_m, p.ridge_idx, p.turbidity, RISK_TEXT[p.risk], p.read_time])]);
  }

  function recommendation() {
    const high = samples.filter((p) => p.risk === "high");
    const body = sensingStats.done === 0 ? "尚未开始检测，请点击“一键全检”开始田间巡检。" : high.length ? `发现 ${high.length} 个高风险点：${high.slice(0, 8).map((p) => p.point_id).join("、")}。建议立即对高风险区域进行 PCR 精测采样，并视情况定点喷洒。` : `已完成 ${sensingStats.done} 点检测，当前风险可控。继续完成剩余 ${samples.length - sensingStats.done} 点。`;
    showMessage("农技建议", body);
  }

  function applyCurve() {
    if (curve.slope >= 0) { showMessage("参数错误", "标准曲线斜率应 < 0（Ct 与浓度负相关）。"); return; }
    setSamples((old) => old.map((p) => p.pcr_ct == null ? p : { ...p, pcr_conc: ctToConcentration(p.pcr_ct, p.pcr_qual, 1, curve), pcr_verdict: pcrVerdict(p.pcr_ct, p.pcr_qual, curve), pcr_gene: curve.gene }));
    setStatus(`标准曲线已更新: slope=${curve.slope}, intercept=${curve.intercept}`);
  }

  function recordPcr() {
    if (selectedIndex < 0) { showMessage("PCR 录入", "请先在地图或 PCR 表格中选择样本。"); return; }
    const ct = Number(ctInput); if (!Number.isFinite(ct) || ct < 5 || ct > 45) { showMessage("输入错误", "Ct 值应在 5~45 范围内。"); return; }
    const concentration = ctToConcentration(ct, quality, dilution, curve), verdict = pcrVerdict(ct, quality, curve);
    setSamples((old) => old.map((p, i) => i === selectedIndex ? { ...p, pcr_ct: ct, pcr_conc: concentration, pcr_qual: quality, pcr_gene: curve.gene, pcr_verdict: verdict, pcr_is_simulated: false } : p));
    if (verdict.includes("阳性")) addAlert(verdict === "强阳性" ? "critical" : "warning", "PCR阳性", `${samples[selectedIndex].point_id} Ct=${ct}，判定为${verdict}。`);
    setStatus(`PCR RECORDED: ${samples[selectedIndex].point_id} Ct=${ct} → ${verdict}`);
  }

  function batchPcr() {
    let count = 0;
    setSamples((old) => old.map((p) => { if (p.turbidity == null || p.pcr_ct != null) return p; count++; return simulatePcr(p, curve); }));
    setStatus(count ? `PCR SIMULATE: 已为 ${count} 个样本生成模拟 PCR 结果。` : "PCR SIMULATE: 没有需要补充的样本。");
  }

  async function importPcrCsv(file?: File) {
    if (!file) return;
    const rows = parseCsv(await file.text()); if (rows.length < 2) { showMessage("导入失败", "CSV 中没有有效数据行。"); return; }
    const header = rows[0].map((x) => x.replace(/^\ufeff/, "").trim());
    const find = (...aliases: string[]) => aliases.map((a) => header.indexOf(a)).find((i) => i >= 0) ?? -1;
    const idCol = find("采样点编号", "样本编号", "Point ID", "Sample ID", "编号"), xCol = find("X(m)", "X", "x_m"), yCol = find("Y(m)", "Y", "y_m"), turbCol = find("浊度(NTU)", "粗定浊度(NTU)", "浊度", "Turbidity"), ctCol = find("Ct 值", "Ct", "Ct Value", "pcr_ct", "Ct值"), qualCol = find("质量标记", "质量", "Quality", "pcr_qual"), geneCol = find("靶基因", "Gene", "pcr_gene");
    const next = [...samples]; let imported = 0;
    rows.slice(1).forEach((row) => {
      const id = row[idCol >= 0 ? idCol : 0]; if (!id) return;
      let index = next.findIndex((p) => p.point_id === id);
      if (index < 0 && next.length === 0) {
        const x = numberValue(row[xCol], 0), y = numberValue(row[yCol], 0), real: Point = planning ? [planning.reference[0] + x * planning.scale, planning.reference[1] + y * planning.scale] : [x, y];
        next.push({ point_id: id, real_xy: real, x_m: x, y_m: y, ridge_idx: 0, round: 1, turbidity: null, risk: "pending", read_time: "", pcr_ct: null, pcr_conc: null, pcr_qual: "pending", pcr_gene: null, pcr_verdict: "" }); index = next.length - 1;
      }
      if (index < 0) return;
      const base = next[index], turbidity = turbCol >= 0 && row[turbCol] ? Number(row[turbCol]) : base.turbidity, ct = ctCol >= 0 && row[ctCol] ? Number(row[ctCol]) : base.pcr_ct;
      const qual = normalizePcrQuality(qualCol >= 0 && row[qualCol] ? row[qualCol] : "", ct != null ? "valid" : base.pcr_qual);
      next[index] = { ...base, turbidity: Number.isFinite(turbidity) ? turbidity : base.turbidity, risk: Number.isFinite(turbidity) ? classifyRisk(turbidity as number, mediumThreshold, highThreshold) : base.risk, pcr_ct: Number.isFinite(ct) ? ct : base.pcr_ct, pcr_qual: qual, pcr_gene: geneCol >= 0 && row[geneCol] ? row[geneCol] : curve.gene, pcr_conc: Number.isFinite(ct) ? ctToConcentration(ct as number, qual, 1, curve) : base.pcr_conc, pcr_verdict: Number.isFinite(ct) ? pcrVerdict(ct as number, qual, curve) : base.pcr_verdict, pcr_is_simulated: false };
      imported++;
    });
    setSamples(next); setFusionEnabled(true); setStatus(`PCR IMPORT: 已更新 ${imported} 条样本记录。`);
  }

  function pcrCsv() {
    return toCsv([["样本编号", "X(m)", "Y(m)", "粗定浊度(NTU)", "粗定风险", "Ct 值", "PCR 浓度(copies/m³)", "判定结果", "质量标记", "靶基因", "数据来源"], ...samples.filter((p) => p.pcr_ct != null).map((p) => [p.point_id, p.x_m, p.y_m, p.turbidity, RISK_TEXT[p.risk], p.pcr_ct, p.pcr_conc, p.pcr_verdict, QUALITY_TEXT[p.pcr_qual], p.pcr_gene, p.pcr_is_simulated ? "模拟" : "实验"])]);
  }

  function pcrText() {
    return [`PCR 分析完整报告`, `生成: ${new Date().toLocaleString()}`, `标准曲线: Ct = ${curve.slope} × log10(C) + ${curve.intercept}`, `靶基因: ${curve.gene}`, `LOD: ${curve.lod} copies/μL`, `PCR样本:${pcrStats.done} 有效:${pcrStats.valid} 阳性:${pcrStats.positive} 阴性:${pcrStats.negative}`, "", ...samples.filter((p) => p.pcr_ct != null).map((p) => `${p.point_id}\tCt=${p.pcr_ct}\tC=${p.pcr_conc?.toExponential(3)}\t${p.pcr_verdict}\t${QUALITY_TEXT[p.pcr_qual]}`)].join("\n");
  }

  function exportGeoJson() {
    if (!planning) { showMessage("GeoJSON", "请先完成路径规划。"); return; }
    const ring = [...planning.fieldPolygonMeters, planning.fieldPolygonMeters[0]];
    const features = [{ type: "Feature", geometry: { type: "Polygon", coordinates: [ring] }, properties: { name: "农田边界", area_m2: polygonArea(polygon) / planning.scale ** 2 } }, ...samples.filter((p) => p.pcr_ct != null).map((p) => ({ type: "Feature", geometry: { type: "Point", coordinates: [p.x_m, p.y_m] }, properties: { id: p.point_id, ct_value: p.pcr_ct, concentration: p.pcr_conc, verdict: p.pcr_verdict } }))];
    downloadFile("pcr_results.geojson", JSON.stringify({ type: "FeatureCollection", features }, null, 2), "application/geo+json");
  }

  function lodCheck() {
    let count = 0; setSamples((old) => old.map((p) => { if (p.pcr_conc != null && p.pcr_conc < curve.lod && p.pcr_qual === "valid") { count++; return { ...p, pcr_qual: "doubtful" }; } return p; })); setStatus(count ? `LOD CHECK: ${count} 个样本低于 ${curve.lod}，已标记存疑。` : "LOD CHECK: 所有样本均不低于检测限。");
  }

  function outlierCheck() {
    const valid = samples.map((p, i) => ({ p, i })).filter(({ p }) => p.pcr_ct != null && p.pcr_qual === "valid"); if (valid.length < 5) { showMessage("离群值检测", "需要至少 5 个有效 PCR 结果。"); return; }
    const mean = valid.reduce((sum, x) => sum + (x.p.pcr_ct ?? 0), 0) / valid.length, std = Math.sqrt(valid.reduce((sum, x) => sum + ((x.p.pcr_ct ?? 0) - mean) ** 2, 0) / valid.length); const flagged = new Set(valid.filter((x) => std && Math.abs((x.p.pcr_ct ?? 0) - mean) / std > 2.5).map((x) => x.i)); setSamples((old) => old.map((p, i) => flagged.has(i) ? { ...p, pcr_qual: "doubtful" } : p)); setStatus(`OUTLIER DETECTION: ${flagged.size} 个 |Z|>2.5 的 Ct 值已标记。`);
  }

  function comparePcr() {
    try { const r = pearsonComparison(samples, mediumThreshold, highThreshold); showMessage("粗定浊度 vs PCR 浓度", <div className="result-grid"><b>配对样本</b><span>{r.count}</span><b>Pearson r</b><span>{r.r.toFixed(3)}</span><b>定性符合率</b><span>{r.agreement}/{r.count}（{r.agreementPct.toFixed(1)}%）</span></div>); }
    catch (error) { showMessage("对比分析", error instanceof Error ? error.message : String(error)); }
  }

  function showFusionMap() {
    if (!fusionField) { showMessage("粗精融合热力图", "请先完成路径规划，并至少录入 1 个有效 PCR 结果。"); return; }
    setFusionEnabled(true); setStatus(`FUSION MAP: PCR权重 ${(fusionField.calibration.pcrWeightMin * 100).toFixed(0)}%~${(fusionField.calibration.pcrWeightMax * 100).toFixed(0)}%，配对校准 ${fusionField.calibration.pairedCount} 组。`);
  }

  function runPrediction() {
    if (!planning) { showMessage("扩散预测", "请先完成路径规划。"); return; }
    if (!fusionField) { showMessage("扩散预测", "需要至少 1 个有效 PCR 结果以建立粗精融合基准场。"); return; }
    setFusionEnabled(true); setStatus("FORECASTING: 正在从粗精融合基准场计算3/5/7天风险演化...");
    window.setTimeout(() => { try {
      const result = runForecast(polygon, planning, fusionField, weather, [72, 120, 168]); setForecast(result); setForecastHour(72);
      const fieldName = historyName || "当前地块", latestEnvironment = environmentHistory.filter((record) => record.fieldName === fieldName).at(-1);
      const historyRecord: ForecastHistoryRecord = { id: `FC-${Date.now()}`, createdAt: new Date().toISOString(), fieldName, p90_3d: result[72].p90, p90_5d: result[120].p90, p90_7d: result[168].p90, meanSpore: sensingStats.average ?? 0, anomalyScore: latestEnvironment?.anomalyScore ?? 0 };
      void dataSource.appendForecastHistory(historyRecord).then((next) => setForecastHistory(next));
      if (result[168].p90 > 5000) addAlert("critical", "7天病害预警", `7天预测P90达到 ${result[168].p90.toFixed(0)} copies/m³，建议立即制定定点防控任务。`, fieldName);
      else if (result[168].p90 > 1000) addAlert("warning", "7天病害预警", `7天预测P90达到 ${result[168].p90.toFixed(0)} copies/m³，建议加强复测。`, fieldName);
      setStatus(`FORECAST DONE: 3/5/7天预测完成，稳定度${result[72].stability}。`);
    } catch (error) { showMessage("预测失败", error instanceof Error ? error.message : String(error)); } }, 20);
  }

  const forecastSummary = useMemo(() => {
    const slice = forecast?.[forecastHour]; if (!slice) return null;
    const fieldValues = slice.concentrations.filter((_, index) => slice.inside?.[index] ?? true);
    const red = fieldValues.filter((c) => c > 5000).length, orange = fieldValues.filter((c) => c > 1000 && c <= 5000).length, yellow = fieldValues.filter((c) => c > 200 && c <= 1000).length;
    const mean = Number.isFinite(slice.mean) ? slice.mean : fieldValues.reduce((sum, value) => sum + value, 0) / Math.max(1, fieldValues.length);
    return { peak: slice.peak, p90: slice.p90, mean, stability: slice.stability, red, orange, yellow, green: fieldValues.length - red - orange - yellow };
  }, [forecast, forecastHour]);

  function forecastCsv() {
    const slice = forecast?.[forecastHour]; if (!slice) return "";
    return toCsv([["X(m)", "Y(m)", "浓度(copies/m³)", "风险等级"], ...slice.grid.flatMap(([x, y], i) => { if (!(slice.inside?.[i] ?? true)) return []; const c = slice.concentrations[i]; return [[x.toFixed(1), y.toFixed(1), c.toExponential(4), c > 5000 ? "红" : c > 1000 ? "橙" : c > 200 ? "黄" : "绿"]]; })]);
  }

  function forecastText() {
    return ["孢子扩散预测与风险预报报告", `生成: ${new Date().toLocaleString()}`, `风速:${weather.windSpeed}m/s 风向:${weather.windDirection}° 稳定度:${classifyStability(weather.windSpeed, weather.daytime, weather.cloud)}`, `温度:${weather.temperature}°C 湿度:${weather.humidity}% 土壤墒情:${weather.soilMoisture}% 光照:${weather.lightIntensity}lux`, `DI:${weather.diseaseIndex} LAI:${weather.lai} 株高:${weather.plantHeight}m`, "", ...[72, 120, 168].map((h) => { const s = forecast?.[h]; const values = s?.concentrations.filter((_, index) => s.inside?.[index] ?? true) ?? []; const mean = s && Number.isFinite(s.mean) ? s.mean : values.reduce((sum, value) => sum + value, 0) / Math.max(1, values.length); return s ? `${h / 24}天: 峰值${s.peak.toFixed(0)} copies/m³ P90=${s.p90.toFixed(0)} 均值=${mean.toFixed(0)} 红区${values.filter((c) => c > 5000).length}格` : `${h / 24}天: 未计算`; }), "", "模型：PCR高权重回归残差融合场 + 冠层风修正的平流—扩散—沉降—再释放逐时演化；结果供田间防控决策参考。"].join("\n");
  }

  function htmlReport() {
    const positive = samples.filter((p) => p.pcr_verdict.includes("阳性")).length, area = planning ? polygonArea(polygon) / planning.scale ** 2 : 0;
    return `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>农田孢子监测与多模态病害诊断报告</title><style>body{font-family:Arial,"Microsoft YaHei";max-width:1000px;margin:40px auto;color:#263238}h1{border-bottom:3px double #34495e;padding-bottom:20px;text-align:center}.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.card{border:1px solid #ccd6dd;padding:16px;border-radius:8px}table{width:100%;border-collapse:collapse;margin-top:24px}th,td{border:1px solid #ccd6dd;padding:8px}th{background:#eef3f5}.summary{border-left:5px solid #3498db;background:#edf7ff;padding:18px;margin-top:24px}</style></head><body><h1>多维农田病害诊断与孢子飘散预报报告</h1><p>生成时间：${new Date().toLocaleString()}</p><div class="grid"><div class="card"><b>农田基本属性</b><p>面积：${area.toFixed(1)}㎡</p><p>采样：${samples.length}点</p><p>风向：${weather.windDirection}° / ${weather.windSpeed}m/s</p></div><div class="card"><b>作物表型</b><p>DI：${weather.diseaseIndex}</p><p>LAI：${weather.lai}</p><p>株高：${weather.plantHeight}m</p><p>基因：${curve.gene}</p></div></div><table><thead><tr><th>ID</th><th>浊度</th><th>粗定风险</th><th>Ct</th><th>浓度</th><th>最终判定</th></tr></thead><tbody>${samples.map((p) => `<tr><td>${p.point_id}</td><td>${p.turbidity ?? "未测"}</td><td>${RISK_TEXT[p.risk]}</td><td>${p.pcr_ct ?? "未测"}</td><td>${p.pcr_conc?.toExponential(3) ?? "--"}</td><td>${p.pcr_verdict || "待检"}</td></tr>`).join("")}</tbody></table><div class="summary">确诊阳性源点：<b>${positive}</b> 个。当前扩散阶段：<b>${positive >= 3 ? "高度风险" : positive ? "中度风险" : "低风险"}</b>。建议结合3、5、7天预测热力走向实施下风向定点防治。</div></body></html>`;
  }

  function showDashboard() {
    const counts = ["high", "medium", "low", "pending"].map((risk) => ({ risk, count: samples.filter((p) => p.risk === risk).length }));
    showMessage("多维巡检数据决策看板", <div className="dashboard-modal"><div className="risk-bars">{counts.map((item) => <div key={item.risk}><span style={{ height: `${Math.max(8, samples.length ? item.count / samples.length * 150 : 8)}px`, background: rgbaForRisk(item.risk) }} /><b>{item.count}</b><small>{RISK_TEXT[item.risk as keyof typeof RISK_TEXT]}</small></div>)}</div><div className="dashboard-summary"><p>标准曲线：Ct = {curve.slope} × lg(Q) + {curve.intercept}</p><p>拟合信度：R² = 0.9912（原程序展示值）</p><p>粗定已测：{sensingStats.done}/{samples.length}</p><p>PCR有效：{pcrStats.valid}，阳性：{pcrStats.positive}</p><p>预测状态：{forecast ? "3/5/7天已完成" : "尚未运行"}</p></div></div>);
  }

  const planningPanel = <>
    <Section title="历史巡检地块数据库"><select value={historyName} onChange={(e) => { setHistoryName(e.target.value); loadProject(e.target.value); }}><option value="">选择历史项目</option>{history.map((item) => <option key={item.name}>{item.name}</option>)}</select><div className="button-grid two"><button onClick={saveProject}>保存当前项目</button><button className="danger" onClick={deleteProject}>删除选中项目</button></div></Section>
    <Section title="1. 底图与边界"><input ref={imageInputRef} hidden type="file" accept="image/*" onChange={(e) => loadImage(e.target.files?.[0])} /><button onClick={() => imageInputRef.current?.click()}>导入空地多光谱卫星图</button><input ref={slamInputRef} hidden type="file" accept=".pgm,image/x-portable-graymap,application/octet-stream" onChange={(e) => loadSlamMap(e.target.files?.[0])} /><input ref={slamYamlInputRef} hidden type="file" accept=".yaml,.yml" onChange={() => selectSlamYaml()} /><button onClick={() => slamYamlInputRef.current?.click()}>选择 SLAM 地图 YAML 元数据</button><button onClick={() => slamInputRef.current?.click()}>导入机器人 SLAM 建图 (.pgm)</button>{slamLabel && <small className="hint">已载入：{slamLabel}，分辨率 {slamInfo?.resolution ?? 0.05} m/px</small>}<button onClick={() => showMessage("底图适配检查", imageUrl ? (slamInfo ? `SLAM 地图已加载：${slamInfo.width}×${slamInfo.height}px，分辨率 ${slamInfo.resolution} m/px，原点(${slamInfo.origin[0]}, ${slamInfo.origin[1]})m。标定边界时首边像素×分辨率=实际长度，首边长度（refLength）会自动换算为真实米数。` : `底图已加载；当前边界 ${polygon.length} 个顶点，占画布宽高比例将在闭合后参与规划。`) : "尚未加载底图，可直接使用格网标定。")}>底图适配检查</button><button className={drawing ? "active-action" : ""} onClick={() => { setDrawing(true); setClosed(false); setStatus("DRAWING: 在画布中依次点击边界顶点，前两个点定义比例尺与垄向。"); }}>标定不规则边界（首边为垄向）</button><div className="button-grid two"><button onClick={closePolygon}>闭合农田拓扑空间</button><button onClick={() => { setPolygon((old) => old.slice(0, -1)); setClosed(false); }}>撤销顶点</button></div><button onClick={() => setView({ zoom: 1, panX: 0, panY: 0 })}>复位地图显示视角</button></Section>
    <Section title="参数预设"><select value={presetName} onChange={(e) => setPresetName(e.target.value)}>{Object.keys(allPresets).map((name) => <option key={name}>{name}</option>)}</select><div className="button-grid three"><button onClick={() => { setPlanParams({ ...allPresets[presetName] }); setStatus(`PRESET APPLIED: ${presetName}`); }}>应用</button><button onClick={savePreset}>保存</button><button onClick={() => presetInputRef.current?.click()}>载入</button></div><input ref={presetInputRef} hidden type="file" accept="application/json" onChange={(e) => importPreset(e.target.files?.[0])} /></Section>
    <Section title="规划参数设定"><Field label="基准首边长度" value={planParams.refLength} onChange={(v) => updatePlan("refLength", v)} unit="m" /><Field label="作物种植垄距" value={planParams.ridgeDistance} onChange={(v) => updatePlan("ridgeDistance", v)} unit="m" /><Field label="每轮采样点数P" value={planParams.samplesPerRound} onChange={(v) => updatePlan("samplesPerRound", v)} /><Field label="孢子有效半径R" value={planParams.sporeRadius} onChange={(v) => updatePlan("sporeRadius", v)} unit="m" /><Field label="采集轮次K" value={planParams.rounds} onChange={(v) => updatePlan("rounds", v)} /><Field label="小车行驶速度" value={planParams.vehicleSpeed} onChange={(v) => updatePlan("vehicleSpeed", v)} unit="m/s" /><div className="check-row"><label><input type="checkbox" checked={showGrid} onChange={(e) => setShowGrid(e.target.checked)} />评估格网</label><label><input type="checkbox" checked={showLegend} onChange={(e) => setShowLegend(e.target.checked)} />图例</label></div></Section>
    <button className="primary panel-action-button" onClick={solve}>3. 求解全覆盖路由方案</button>
    <div className="button-list"><button onClick={() => { if (!planning) return showMessage("推荐采样密度", "请先完成边界规划。"); const area = polygonArea(polygon) / planning.scale ** 2, cover = Math.PI * planParams.sporeRadius ** 2; showMessage("推荐采样密度", `地块面积 ${area.toFixed(0)}㎡，单点覆盖 ${cover.toFixed(0)}㎡，推荐每轮约 ${Math.max(3, Math.trunc(area / cover * 1.3))} 点。`); }}>推荐采样密度</button><button onClick={() => downloadFile("planning.json", planningJson(), "application/json")}>导出路径规划 JSON</button><button onClick={() => downloadFile("planning_report.txt", planningReport())}>导出规划报告 TXT</button><button onClick={() => showMessage("综合统计摘要", planning ? <div className="result-grid"><b>候选点</b><span>{planning.candidateCount}</span><b>采样点</b><span>{samples.length}</span><b>覆盖率</b><span>{planning.coveragePct.toFixed(2)}%</span><b>总路程</b><span>{planning.totalDistance.toFixed(2)}m</span><b>预计时间</b><span>{planning.totalTime.toFixed(1)}s</span></div> : "请先运行规划。")}>综合统计摘要</button><button onClick={() => showMessage("坐标验证", planning ? `X范围 ${Math.min(...planning.fieldPolygonMeters.map((p) => p[0])).toFixed(1)}~${Math.max(...planning.fieldPolygonMeters.map((p) => p[0])).toFixed(1)}m；Y范围 ${Math.min(...planning.fieldPolygonMeters.map((p) => p[1])).toFixed(1)}~${Math.max(...planning.fieldPolygonMeters.map((p) => p[1])).toFixed(1)}m。` : "请先完成规划。")}>坐标验证</button><button onClick={saveSession}>保存工作会话</button><button onClick={() => sessionInputRef.current?.click()}>恢复工作会话</button><input ref={sessionInputRef} hidden type="file" accept="application/json" onChange={(e) => restoreSession(e.target.files?.[0])} /><button onClick={() => { downloadFile("planning.json", planningJson(), "application/json"); window.setTimeout(() => downloadFile("sensing.csv", sensingCsv(), "text/csv;charset=utf-8"), 150); window.setTimeout(() => downloadFile("report.txt", planningReport()), 300); }}>一键批量导出</button><button className="danger" onClick={clearAll}>清空画布</button></div>
  </>;

  const sensingPanel = <>
    <Section title="浊度预警阈值设定"><Field label="中风险阈值" value={mediumThreshold} onChange={(v) => setMediumThreshold(numberValue(v, mediumThreshold))} unit="NTU" /><Field label="高风险阈值" value={highThreshold} onChange={(v) => setHighThreshold(numberValue(v, highThreshold))} unit="NTU" /><Field label="全检间隔" value={scanDelay} onChange={(v) => setScanDelay(numberValue(v, scanDelay))} unit="s" /><Field label="覆盖半径" value={coverageRadius} onChange={(v) => setCoverageRadius(numberValue(v, coverageRadius))} unit="m" /><div className="radio-row">{[["uniform", "均匀"], ["hotspot", "热点"], ["gradient", "渐变"], ["twozone", "双区"]].map(([value, label]) => <label key={value}><input type="radio" checked={simulationMode === value} onChange={() => setSimulationMode(value)} />{label}</label>)}</div><button onClick={applyThresholds}>应用阈值</button></Section>
    <Section title="田间环境传感"><Field label="空气温度" value={weather.temperature} onChange={(v) => updateWeather("temperature", numberValue(v, weather.temperature))} unit="°C" /><Field label="空气湿度" value={weather.humidity} onChange={(v) => updateWeather("humidity", numberValue(v, weather.humidity))} unit="%" /><Field label="土壤墒情" value={weather.soilMoisture} onChange={(v) => updateWeather("soilMoisture", numberValue(v, weather.soilMoisture))} unit="%" /><Field label="土壤温度" value={weather.soilTemperature} onChange={(v) => updateWeather("soilTemperature", numberValue(v, weather.soilTemperature))} unit="°C" /><Field label="光照强度" value={weather.lightIntensity} onChange={(v) => updateWeather("lightIntensity", numberValue(v, weather.lightIntensity))} unit="lux" /><Field label="叶面湿度" value={weather.leafWetness} onChange={(v) => updateWeather("leafWetness", numberValue(v, weather.leafWetness))} unit="%" /><Field label="小时降雨" value={weather.rainfall} onChange={(v) => updateWeather("rainfall", numberValue(v, weather.rainfall))} unit="mm" /><button className="primary" onClick={recordEnvironmentSnapshot}>记录环境与孢子快照</button></Section>
    <Section title="光敏传感器读数"><div className="sensor-reading"><small>当前采样点：{selected?.point_id ?? "未选中"}</small><strong>{selected?.turbidity != null ? `${selected.turbidity.toFixed(1)} NTU` : "-- NTU"}</strong><em style={{ color: selected ? rgbaForRisk(selected.risk) : undefined }}>风险：{selected ? RISK_TEXT[selected.risk] : "等待检测"}</em></div><button className="primary" onClick={readSingle}>读取传感器（单点）</button><button className="primary accent" disabled={scanning} onClick={startScan}>一键全检（顺序巡检）</button><button className="danger" onClick={stopScan}>停止全检（Esc）</button><button onClick={resetReadings}>重置全部读数</button><p className="progress-text">{scanProgress}</p></Section>
    <div className="button-list"><button onClick={recommendation}>查看农技建议</button><button onClick={() => downloadFile("field_sensing.csv", sensingCsv(), "text/csv;charset=utf-8")}>导出粗定检测数据 CSV</button></div>
    <div className="stat-strip"><span>总计:{sensingStats.total}</span><span>已测:{sensingStats.done}</span><span className="danger-text">高风险:{sensingStats.high}</span><span>均值:{sensingStats.average?.toFixed(0) ?? "--"}</span></div>
    <div className="table-wrap"><table><thead><tr><th>#</th><th>采样点</th><th>浊度</th><th>风险</th><th>时间</th></tr></thead><tbody>{samples.map((p, i) => <tr key={p.point_id} className={selectedIndex === i ? "selected-row" : ""} onClick={() => setSelectedIndex(i)}><td>{i + 1}</td><td>{p.point_id}</td><td>{p.turbidity?.toFixed(1) ?? "--"}</td><td className={`risk-${p.risk}`}>{RISK_TEXT[p.risk]}</td><td>{p.read_time || "--"}</td></tr>)}</tbody></table></div>
  </>;

  const pcrPanel = <>
    <Section title="数据导入"><input ref={pcrInputRef} hidden type="file" accept=".csv,text/csv" onChange={(e) => importPcrCsv(e.target.files?.[0])} /><button className="primary" onClick={() => pcrInputRef.current?.click()}>导入田间采集数据 CSV</button><small className="hint">兼容 sample_pcr_data.csv 与中英文列名</small></Section>
    <Section title="标准曲线参数"><code>Ct = slope × log₁₀(Concentration) + intercept</code><Field label="斜率 slope" value={curve.slope} onChange={(v) => updateCurve("slope", numberValue(v, curve.slope))} /><Field label="截距 intercept" value={curve.intercept} onChange={(v) => updateCurve("intercept", numberValue(v, curve.intercept))} /><Field label="检测限 LOD" value={curve.lod} onChange={(v) => updateCurve("lod", numberValue(v, curve.lod))} unit="copies/μL" /><label className="field-row"><span>靶基因</span><select value={curve.gene} onChange={(e) => updateCurve("gene", e.target.value)}>{Object.keys(TARGET_GENE_DATABASE).map((gene) => <option key={gene}>{gene}</option>)}</select></label><p className="gene-info">{geneInfo.name}（{geneInfo.amplicon}）—— {geneInfo.note}</p><Field label="阳性 Ct" value={curve.positiveCt} onChange={(v) => updateCurve("positiveCt", numberValue(v, curve.positiveCt))} /><Field label="阴性阈值 Ct" value={curve.negativeCt} onChange={(v) => updateCurve("negativeCt", numberValue(v, curve.negativeCt))} /><button onClick={applyCurve}>应用标曲参数</button><button onClick={() => { setCurve(DEFAULT_CURVE); setStatus("标曲预设: 真菌 ITS 通用引物参数。"); }}>标曲预设：真菌ITS通用引物</button></Section>
    <Section title="PCR 结果录入"><div className="selected-sample">选中样本：{selected?.point_id ?? "--"}</div><Field label="Ct 值" value={ctInput} onChange={setCtInput} unit="cycles" /><p className="estimate">{ctInput && Number.isFinite(Number(ctInput)) ? `≈ ${ctToConcentration(Number(ctInput), quality, dilution, curve)?.toExponential(3) ?? "--"} copies/m³` : ""}</p><label className="field-row"><span>稀释倍数</span><select value={dilution} onChange={(e) => setDilution(Number(e.target.value))}>{[1, 2, 5, 10, 20, 50, 100].map((v) => <option key={v}>{v}</option>)}</select></label><div className="radio-row">{(["valid", "doubtful", "invalid"] as PcrQuality[]).map((value) => <label key={value}><input type="radio" checked={quality === value} onChange={() => setQuality(value)} />{QUALITY_TEXT[value]}</label>)}</div><button className="primary" onClick={recordPcr}>录入当前样本 PCR</button><button onClick={batchPcr}>批量生成模拟 PCR</button>{selected?.pcr_verdict && <div className="verdict">判定结果：{selected.pcr_verdict}</div>}</Section>
    <div className="stat-strip"><span>PCR:{pcrStats.done}</span><span>有效:{pcrStats.valid}</span><span className="danger-text">阳性:{pcrStats.positive}</span><span>阴性:{pcrStats.negative}</span></div>
    <div className="table-wrap"><table><thead><tr><th>#</th><th>样本</th><th>Ct</th><th>浓度</th><th>判定</th><th>质量</th><th>NTU</th></tr></thead><tbody>{samples.map((p, i) => <tr key={p.point_id} className={selectedIndex === i ? "selected-row" : ""} onClick={() => { setSelectedIndex(i); setCtInput(p.pcr_ct?.toString() ?? ""); setQuality(p.pcr_qual === "pending" ? "valid" : p.pcr_qual); }}><td>{i + 1}</td><td>{p.point_id}</td><td>{p.pcr_ct?.toFixed(1) ?? "--"}</td><td>{p.pcr_conc?.toExponential(2) ?? "--"}</td><td>{p.pcr_verdict || "--"}</td><td>{QUALITY_TEXT[p.pcr_qual]}</td><td>{p.turbidity?.toFixed(0) ?? "--"}</td></tr>)}</tbody></table></div>
    <div className="button-grid two"><button className={fusionEnabled ? "active-action" : ""} onClick={showFusionMap}>粗精融合热力图</button><button onClick={comparePcr}>对比分析</button></div>
    <div className="button-list"><button onClick={() => downloadFile("pcr_report.csv", pcrCsv(), "text/csv;charset=utf-8")}>导出 PCR 分析报告 CSV</button><button onClick={() => downloadFile("pcr_full_report.txt", pcrText())}>导出 PCR 完整报告 TXT</button><button onClick={exportGeoJson}>导出 GeoJSON</button><button onClick={showDashboard}>多维巡检数据决策看板</button></div>
    <div className="button-grid two"><button onClick={lodCheck}>LOD检测限检查</button><button onClick={outlierCheck}>离群值检测</button><button onClick={() => setStatus(`PCR STATS: ${pcrStats.done}样本 ${pcrStats.valid}有效 ${pcrStats.positive}阳性`)}>快速统计</button><button className="danger" onClick={() => { if (window.confirm("清空全部 PCR 结果？粗定数据将保留。")) setSamples((old) => old.map((p) => ({ ...p, pcr_ct: null, pcr_conc: null, pcr_qual: "pending", pcr_gene: null, pcr_verdict: "", pcr_is_simulated: null }))); }}>清空 PCR 数据</button></div>
  </>;

  const diseasePanel = <>
    <Section title="病害影像识别"><label className="field-row"><span>作物类型</span><select value={cropType} onChange={(event) => { const crop = event.target.value as CropType; setCropType(crop); setDiseasePredictions([]); setConfirmedDiseaseId(""); const first = DISEASE_DATABASE.find((disease) => disease.crop === crop); if (first) setDiseaseBrowseId(first.id); }}>{(["小麦", "玉米", "苹果", "葡萄"] as CropType[]).map((crop) => <option key={crop}>{crop}</option>)}</select></label><input ref={diseaseImageInputRef} hidden type="file" accept="image/*" onChange={(event) => analyzeDiseaseImage(event.target.files?.[0])} /><button className="primary" onClick={() => diseaseImageInputRef.current?.click()}>上传叶片/果实病害影像</button><small className="hint">当前为浏览器端颜色、纹理原型识别；比赛准确率只统计人工确认的真实标签，不使用预置假数据。</small>{diseaseImage && <div className="disease-preview" role="img" aria-label="待识别病害影像" style={{ backgroundImage: `url(${diseaseImage})` }} />}{diseasePredictions.length > 0 && <div className="prediction-list">{diseasePredictions.slice(0, 3).map((prediction, index) => <div key={prediction.diseaseId}><b>{index + 1}. {prediction.name}</b><span>{(prediction.confidence * 100).toFixed(1)}%</span><i style={{ width: `${Math.max(4, prediction.confidence * 100)}%` }} /></div>)}</div>}<label className="field-row"><span>人工真实标签</span><select value={confirmedDiseaseId} onChange={(event) => setConfirmedDiseaseId(event.target.value)}><option value="">待人工复核</option>{DISEASE_DATABASE.filter((disease) => disease.crop === cropType).map((disease) => <option key={disease.id} value={disease.id}>{disease.name}</option>)}</select></label><button onClick={confirmDiseaseEvaluation}>确认标签并计入真实准确率</button></Section>
    <div className="stat-strip"><span>病害库:{DISEASE_DATABASE.length}</span><span>真实样本:{diseaseMetrics.sampleCount}</span><span>识别正确:{diseaseMetrics.correct}</span><span className={diseaseMetrics.accuracy != null && diseaseMetrics.accuracy < .9 ? "danger-text" : ""}>准确率:{diseaseMetrics.accuracy == null ? "暂无" : `${(diseaseMetrics.accuracy * 100).toFixed(1)}%`}</span></div>
    <Section title="常见病害数据库"><select value={diseaseBrowseId} onChange={(event) => setDiseaseBrowseId(event.target.value)}>{DISEASE_DATABASE.map((disease) => <option key={disease.id} value={disease.id}>{disease.crop} · {disease.name}</option>)}</select><div className="disease-card"><b>{selectedDisease.name}</b><span>病原：{selectedDisease.pathogen}</span><span>症状：{selectedDisease.symptoms}</span><span>高风险条件：{selectedDisease.favorable}</span><span>PCR靶标：{selectedDisease.gene}</span><span>建议：{selectedDisease.management}</span></div></Section>
    <div className="button-grid two"><button onClick={() => showMessage("真实评估说明", "准确率=预测正确的人工确认样本数/全部人工确认样本数。未确认标签的图片不参与计算；该统计可以作为后续真实测试集验收入口。")}>准确率口径说明</button><button onClick={() => showMessage("分类指标", <div className="table-wrap"><table><thead><tr><th>病害</th><th>样本</th><th>精确率</th><th>召回率</th><th>F1</th></tr></thead><tbody>{diseaseMetrics.perClass.map((metric) => <tr key={metric.id}><td>{DISEASE_DATABASE.find((disease) => disease.id === metric.id)?.name}</td><td>{metric.samples}</td><td>{metric.samples ? `${(metric.precision * 100).toFixed(1)}%` : "--"}</td><td>{metric.samples ? `${(metric.recall * 100).toFixed(1)}%` : "--"}</td><td>{metric.samples ? metric.f1.toFixed(3) : "--"}</td></tr>)}</tbody></table></div>)}>查看分类指标</button></div>
    <div className="table-wrap"><table><thead><tr><th>时间</th><th>图片</th><th>预测</th><th>真实标签</th><th>结果</th></tr></thead><tbody>{diseaseRecords.map((record) => <tr key={record.id}><td>{new Date(record.createdAt).toLocaleDateString()}</td><td>{record.imageName}</td><td>{DISEASE_DATABASE.find((disease) => disease.id === record.predictedId)?.name}</td><td>{DISEASE_DATABASE.find((disease) => disease.id === record.confirmedId)?.name}</td><td className={record.predictedId === record.confirmedId ? "risk-low" : "risk-high"}>{record.predictedId === record.confirmedId ? "正确" : "错误"}</td></tr>)}</tbody></table></div>
  </>;

  const forecastPanel = <>
    <Section title="扩散基准场"><p>PCR锚点：<b>{samples.filter((p) => p.pcr_conc != null).length}</b> 个</p><p className="hint">基准：粗测空间趋势 + PCR高权重残差校正</p><button onClick={showFusionMap}>加载粗精融合基准场</button></Section>
    <Section title="气象参数设定"><Field label="风速" value={weather.windSpeed} onChange={(v) => updateWeather("windSpeed", numberValue(v, weather.windSpeed))} unit="m/s" /><Field label="风向" value={weather.windDirection} onChange={(v) => updateWeather("windDirection", numberValue(v, weather.windDirection))} unit="°" /><Field label="温度" value={weather.temperature} onChange={(v) => updateWeather("temperature", numberValue(v, weather.temperature))} unit="°C" /><Field label="湿度" value={weather.humidity} onChange={(v) => updateWeather("humidity", numberValue(v, weather.humidity))} unit="%" /><Field label="云量" value={weather.cloud} onChange={(v) => updateWeather("cloud", numberValue(v, weather.cloud))} unit="%" /><div className="radio-row"><label><input type="radio" checked={weather.daytime} onChange={() => updateWeather("daytime", true)} />日间</label><label><input type="radio" checked={!weather.daytime} onChange={() => updateWeather("daytime", false)} />夜间</label></div><button onClick={() => setStatus(`WEATHER: 风速${weather.windSpeed}m/s 风向${weather.windDirection}° 稳定度${classifyStability(weather.windSpeed, weather.daytime, weather.cloud)}`)}>应用气象参数</button></Section>
    <Section title="作物表型参数设定"><Field label="病情指数 DI" value={weather.diseaseIndex} onChange={(v) => updateWeather("diseaseIndex", numberValue(v, weather.diseaseIndex))} unit="0-100" /><Field label="叶面积指数 LAI" value={weather.lai} onChange={(v) => updateWeather("lai", numberValue(v, weather.lai))} unit="0.5-10" /><Field label="作物株高 H" value={weather.plantHeight} onChange={(v) => updateWeather("plantHeight", numberValue(v, weather.plantHeight))} unit="m" /></Section>
    <button className="primary panel-action-button" onClick={runPrediction}>运行3–7天扩散预测</button><div className="time-switch">{[72, 120, 168].map((h) => <button key={h} className={forecastHour === h ? "active" : ""} onClick={() => setForecastHour(h)}>{h / 24}天</button>)}</div>
    <Section title="风险摘要">{forecastSummary ? <div className="forecast-summary"><b>◆ {forecastHour / 24}天预报 ◆</b><span>峰值 {forecastSummary.peak.toFixed(0)} · P90 {forecastSummary.p90.toFixed(0)} · 均值 {forecastSummary.mean.toFixed(0)} copies/m³</span><span>红区:{forecastSummary.red} 橙区:{forecastSummary.orange} 黄区:{forecastSummary.yellow} 绿区:{forecastSummary.green}</span><span>稳定度 {forecastSummary.stability} · 风向{weather.windDirection}° · 风速{weather.windSpeed}m/s</span><small className="model-note">融合基准场驱动 · 冠层风平流 · 湍流扩散 · 沉降损失 · 病情再释放 · 温湿度生长</small></div> : <p>等待预测...</p>}</Section>
    <Section title="历史异常与预警趋势"><TrendChart records={environmentHistory.filter((record) => record.fieldName === (historyName || "当前地块"))} /><p className="hint">红点表示稳健异常分数≥3；黄色虚线为历史中位基线。</p><div className="table-wrap compact-table"><table><thead><tr><th>时间</th><th>3天P90</th><th>5天P90</th><th>7天P90</th></tr></thead><tbody>{forecastHistory.filter((record) => record.fieldName === (historyName || "当前地块")).slice(-8).reverse().map((record) => <tr key={record.id}><td>{new Date(record.createdAt).toLocaleDateString()}</td><td>{record.p90_3d.toFixed(0)}</td><td>{record.p90_5d.toFixed(0)}</td><td>{record.p90_7d.toFixed(0)}</td></tr>)}</tbody></table></div></Section>
    <div className="button-list"><button onClick={() => { if (!forecast) return showMessage("导出", "请先运行扩散预测。"); downloadFile("multimodal_report.html", htmlReport(), "text/html;charset=utf-8"); }}>导出多维检测诊断报告 HTML</button><button onClick={showDashboard}>多维巡检数据决策看板</button><button onClick={() => { if (!forecast) return showMessage("导出", "请先运行扩散预测。"); downloadFile("forecast_report.txt", forecastText()); }}>导出预测报告 TXT</button><button onClick={() => { if (!forecast) return showMessage("导出", "请先运行扩散预测。"); downloadFile(`forecast_${forecastHour}h.csv`, forecastCsv(), "text/csv;charset=utf-8"); }}>导出风险热力图数据 CSV</button></div>
  </>;

  const regulationPanel = <>
    <div className="stat-strip"><span>监管地块:{fieldRegistry.length}</span><span>未闭环:{openAlerts.length}</span><span className="danger-text">严重:{openAlerts.filter((alert) => alert.level === "critical").length}</span><span>已处置:{alerts.filter((alert) => alert.status === "resolved").length}</span></div>
    <Section title="数据源"><div className="data-source-chip"><i className={dataSource.isLive ? "live" : "sim"} />{dataSource.sourceName}{slamInfo && <em>· SLAM地图 {slamInfo.width}×{slamInfo.height} @ {slamInfo.resolution}m/px</em>}</div><small className="hint">当前为本地模拟数据源。接入机器人/云端真实数据时，数据层接口保持不变。</small></Section>
    <Section title="多地块监管"><button className="primary" onClick={registerCurrentField}>将当前地块加入/更新监管</button><small className="hint">地块数据均来自当前项目或人工登记，不自动生成演示指标。</small></Section>
    <div className="table-wrap"><table><thead><tr><th>地块</th><th>作物</th><th>面积</th><th>孢子均值</th><th>风险</th><th>告警</th></tr></thead><tbody>{fieldRegistry.map((field) => <tr key={field.id} onClick={() => setHistoryName(field.name)}><td>{field.name}</td><td>{field.crop}</td><td>{field.areaMu.toFixed(1)}亩</td><td>{field.sporeMean.toFixed(0)}</td><td className={`risk-${field.risk}`}>{field.risk === "high" ? "高" : field.risk === "medium" ? "中" : "低"}</td><td>{openAlerts.filter((alert) => alert.fieldName === field.name).length}</td></tr>)}</tbody></table></div>
    <Section title="异常告警闭环"><div className="alert-list">{alerts.length ? alerts.slice(0, 30).map((alert) => <article key={alert.id} className={`monitor-alert ${alert.level} ${alert.status}`}><header><b>{alert.type}</b><span>{alert.level === "critical" ? "严重" : alert.level === "warning" ? "警告" : "提示"}</span></header><p>{alert.message}</p><small>{alert.fieldName} · {new Date(alert.createdAt).toLocaleString()} · {alert.status === "new" ? "待确认" : alert.status === "acknowledged" ? `处理中/${alert.assignee}` : `已闭环/${alert.resolution}`}</small><footer>{alert.status === "new" && <button onClick={() => updateAlertStatus(alert.id, "acknowledged")}>确认告警</button>}{alert.status !== "resolved" && <button onClick={() => updateAlertStatus(alert.id, "resolved")}>处置完成</button>}</footer></article>) : <p className="hint">暂无告警。记录环境快照、录入PCR阳性或运行7天预测后可自动生成告警。</p>}</div></Section>
    <Section title="环境历史记录"><div className="table-wrap compact-table"><table><thead><tr><th>时间</th><th>地块</th><th>温湿度</th><th>墒情</th><th>光照</th><th>NTU</th><th>异常</th></tr></thead><tbody>{environmentHistory.slice(-20).reverse().map((record) => <tr key={record.id}><td>{new Date(record.createdAt).toLocaleString()}</td><td>{record.fieldName}</td><td>{record.temperature}℃/{record.humidity}%</td><td>{record.soilMoisture}%</td><td>{record.lightIntensity}</td><td>{record.sporeMean.toFixed(0)}</td><td className={record.anomalyScore >= 3 ? "risk-high" : ""}>{record.anomalyScore.toFixed(1)}</td></tr>)}</tbody></table></div><button onClick={() => downloadFile("environment_history.csv", toCsv([["时间", "地块", "温度", "湿度", "土壤墒情", "土壤温度", "光照", "降雨", "叶面湿度", "孢子均值", "异常分数"], ...environmentHistory.map((record) => [record.createdAt, record.fieldName, record.temperature, record.humidity, record.soilMoisture, record.soilTemperature, record.lightIntensity, record.rainfall, record.leafWetness, record.sporeMean, record.anomalyScore])]), "text/csv;charset=utf-8")}>导出环境与异常历史 CSV</button></Section>
  </>;

  return <main className="inspection-app">
    <header className="app-header"><div><strong>多模态农田孢子监测与病害扩散预警系统 V4.0</strong><span>Web 控制台 · 功能对照 main_inspection_system_v4_compliance.py</span></div><div className="header-actions"><button onClick={saveSession}>保存会话</button><button onClick={() => sessionInputRef.current?.click()}>恢复会话</button></div></header>
    <div className="app-body"><aside className="control-panel"><nav className="tabs">{(["planning", "sensing", "pcr", "disease", "forecast", "regulation", "robot"] as Tab[]).map((item, i) => <button key={item} className={tab === item ? "active" : ""} onClick={() => setTab(item)}>{["路径规划", "环境监测", "PCR分析", "病害识别", "趋势预警", "监管中心", "机器人监控"][i]}</button>)}</nav><div className="panel-scroll"><p className="panel-kicker">{{ planning: "PATH PLANNING CONTROL", sensing: "ENVIRONMENT & SPORE SENSING", pcr: "PCR ANALYSIS CONTROL", disease: "DISEASE IMAGE RECOGNITION", forecast: "3–7 DAY EARLY WARNING", regulation: "MULTI-FIELD SUPERVISION", robot: "ROBOT LIVE MONITOR" }[tab]}</p>{{ planning: planningPanel, sensing: sensingPanel, pcr: pcrPanel, disease: diseasePanel, forecast: forecastPanel, regulation: regulationPanel, robot: <RobotMonitorPanel slamInfo={slamInfo} slamImageUrl={imageUrl} /> }[tab]}</div></aside>
      <section className="map-workspace"><div className="map-toolbar"><span>{coordinate}</span><div><span>滚轮缩放 · Shift+拖拽平移 · 点击选择采样点</span><button onClick={() => setView((old) => ({ ...old, zoom: Math.max(.5, old.zoom / 1.2) }))}>−</button><b>{Math.round(view.zoom * 100)}%</b><button onClick={() => setView((old) => ({ ...old, zoom: Math.min(3, old.zoom * 1.2) }))}>＋</button></div></div><div className="canvas-frame"><canvas ref={canvasRef} onClick={onCanvasClick} onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={onPointerUp} onPointerCancel={onPointerUp} onContextMenu={(e) => { e.preventDefault(); if (tab === "planning" && drawing) setPolygon((old) => old.slice(0, -1)); }} onWheel={(e) => { e.preventDefault(); setView((old) => ({ ...old, zoom: Math.max(.5, Math.min(3, old.zoom * (e.deltaY < 0 ? 1.12 : .89))) })); }} /></div><footer className="status-bar"><i className={status.includes("ALERT") || status.includes("失败") ? "error" : ""} />{status}</footer></section></div>
    {modal && <div className="modal-backdrop" onMouseDown={() => setModal(null)}><div className="modal-card" onMouseDown={(e) => e.stopPropagation()}><header><h2>{modal.title}</h2><button onClick={() => setModal(null)}>×</button></header><div className="modal-body">{modal.body}</div><footer><button onClick={() => setModal(null)}>关闭</button></footer></div></div>}
  </main>;
}
