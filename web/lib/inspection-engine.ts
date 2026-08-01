export type Point = [number, number];
export type Risk = "low" | "medium" | "high" | "pending";
export type PcrQuality = "valid" | "doubtful" | "invalid" | "pending";

export interface SamplingPoint {
  point_id: string;
  real_xy: Point;
  x_m: number;
  y_m: number;
  ridge_idx: number;
  round: number;
  turbidity: number | null;
  risk: Risk;
  read_time: string;
  pcr_ct: number | null;
  pcr_conc: number | null;
  pcr_qual: PcrQuality;
  pcr_gene: string | null;
  pcr_verdict: string;
  pcr_is_simulated?: boolean | null;
}

export interface PlanParams {
  refLength: number;
  ridgeDistance: number;
  samplesPerRound: number;
  sporeRadius: number;
  rounds: number;
  vehicleSpeed: number;
}

interface Candidate {
  real_xy: Point;
  rot_xy: Point;
  ridge_idx: number;
}

interface Ridge {
  y_rot: number;
  left_rot: number;
  right_rot: number;
}

export interface RouteSegment {
  from: number;
  to: number;
  dist_m: number;
  time_s: number;
  waypoints: Point[];
}

export interface PlanningResult {
  scale: number;
  reference: Point;
  rotationTheta: number;
  rotationCenter: Point;
  fieldPolygonMeters: Point[];
  ridgeDatabase: Record<number, Ridge>;
  roundNodes: Candidate[][];
  roundTours: number[][];
  roundSegments: RouteSegment[][];
  evaluationGrid: Point[];
  cumulativeConfidence: number[];
  gridStepPx: number;
  samplingPoints: SamplingPoint[];
  coveragePct: number;
  averageConfidence: number;
  totalDistance: number;
  totalTime: number;
  candidateCount: number;
}

export interface StandardCurve {
  slope: number;
  intercept: number;
  lod: number;
  positiveCt: number;
  negativeCt: number;
  gene: string;
}

export interface WeatherParams {
  windSpeed: number;
  windDirection: number;
  temperature: number;
  humidity: number;
  cloud: number;
  daytime: boolean;
  diseaseIndex: number;
  lai: number;
  plantHeight: number;
  soilMoisture: number;
  soilTemperature: number;
  lightIntensity: number;
  rainfall: number;
  leafWetness: number;
}

export interface FusionField {
  grid: Point[];
  concentrations: number[];
  coarseConcentrations: number[];
  pcrConcentrations: number[];
  reliabilities: number[];
  inside: boolean[];
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
  gridStep: number;
  cols: number;
  rows: number;
  calibration: {
    slope: number;
    intercept: number;
    pairedCount: number;
    pcrWeightMin: number;
    pcrWeightMax: number;
  };
}

export interface ForecastSlice {
  grid: Point[];
  concentrations: number[];
  inside: boolean[];
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
  gridStep: number;
  cols: number;
  rows: number;
  stability: keyof typeof STABILITY;
  peak: number;
  p90: number;
  mean: number;
  model: "fusion-advection-diffusion";
}

export type ForecastResult = Record<number, ForecastSlice>;

export const PARAMETER_PRESETS: Record<string, PlanParams> = {
  "小麦试验田(小)": { refLength: 50, ridgeDistance: 2.5, samplesPerRound: 6, sporeRadius: 15, rounds: 2, vehicleSpeed: 0.4 },
  "玉米大田(中)": { refLength: 100, ridgeDistance: 4, samplesPerRound: 8, sporeRadius: 20, rounds: 2, vehicleSpeed: 0.5 },
  "水稻连片(大)": { refLength: 200, ridgeDistance: 3, samplesPerRound: 12, sporeRadius: 25, rounds: 3, vehicleSpeed: 0.6 },
  "果园稀疏(宽垄)": { refLength: 80, ridgeDistance: 5, samplesPerRound: 5, sporeRadius: 30, rounds: 1, vehicleSpeed: 0.4 },
  "菜地密植(窄垄)": { refLength: 60, ridgeDistance: 1.5, samplesPerRound: 10, sporeRadius: 12, rounds: 2, vehicleSpeed: 0.3 },
};

export const TARGET_GENE_DATABASE: Record<string, { name: string; amplicon: string; slope: number; intercept: number; note: string }> = {
  "ITS1-F/ITS4-R": { name: "真菌ITS通用引物", amplicon: "~550bp", slope: -3.32, intercept: 38.5, note: "适用于大多数真菌病原菌的初步筛查" },
  "EF1-α-F/EF1-α-R": { name: "翻译延伸因子1-α", amplicon: "~350bp", slope: -3.45, intercept: 37.2, note: "镰刀菌属(Fusarium)鉴定常用" },
  "β-tub-F/β-tub-R": { name: "β-微管蛋白基因", amplicon: "~450bp", slope: -3.28, intercept: 39.1, note: "多种植物病原真菌系统发育分析" },
  "CAL-F/CAL-R": { name: "钙调蛋白基因", amplicon: "~400bp", slope: -3.4, intercept: 38, note: "曲霉属(Aspergillus)鉴定" },
  "TEF-F/TEF-R": { name: "转录延伸因子", amplicon: "~300bp", slope: -3.35, intercept: 37.8, note: "疫霉属(Phytophthora)检测" },
  "自定义引物": { name: "用户自定义引物对", amplicon: "待定", slope: -3.32, intercept: 38.5, note: "请根据实验室标定填写标准曲线参数" },
};

export const round2 = (value: number) => Math.round(value * 100) / 100;

export function rotatePoint(point: Point, center: Point, theta: number): Point {
  const dx = point[0] - center[0];
  const dy = point[1] - center[1];
  const cos = Math.cos(theta);
  const sin = Math.sin(theta);
  return [dx * cos - dy * sin + center[0], dx * sin + dy * cos + center[1]];
}

export function pointInPolygon(point: Point, polygon: Point[]) {
  let inside = false;
  let j = polygon.length - 1;
  for (let i = 0; i < polygon.length; i++) {
    const [xi, yi] = polygon[i];
    const [xj, yj] = polygon[j];
    if ((yi > point[1]) !== (yj > point[1]) &&
        point[0] < ((xj - xi) * (point[1] - yi)) / (yj - yi) + xi) inside = !inside;
    j = i;
  }
  return inside;
}

export function scanlineIntersections(scanY: number, polygon: Point[]) {
  const intersections: number[] = [];
  let j = polygon.length - 1;
  for (let i = 0; i < polygon.length; i++) {
    const [x1, y1] = polygon[i];
    const [x2, y2] = polygon[j];
    if ((y1 <= scanY && scanY < y2) || (y2 <= scanY && scanY < y1)) {
      if (Math.abs(y2 - y1) > 1e-9) intersections.push(x1 + ((scanY - y1) * (x2 - x1)) / (y2 - y1));
    }
    j = i;
  }
  return intersections.sort((a, b) => a - b);
}

export function polygonArea(polygon: Point[]) {
  if (polygon.length < 3) return 0;
  let sum = 0;
  let j = polygon.length - 1;
  for (let i = 0; i < polygon.length; i++) {
    sum += polygon[i][0] * polygon[j][1] - polygon[j][0] * polygon[i][1];
    j = i;
  }
  return Math.abs(sum) / 2;
}

export function polygonCentroid(polygon: Point[]): Point {
  let cx = 0, cy = 0, signedArea = 0;
  let j = polygon.length - 1;
  for (let i = 0; i < polygon.length; i++) {
    const cross = polygon[j][0] * polygon[i][1] - polygon[i][0] * polygon[j][1];
    signedArea += cross;
    cx += (polygon[j][0] + polygon[i][0]) * cross;
    cy += (polygon[j][1] + polygon[i][1]) * cross;
    j = i;
  }
  signedArea *= 0.5;
  return Math.abs(signedArea) < 1e-9 ? polygon[0] ?? [0, 0] : [cx / (6 * signedArea), cy / (6 * signedArea)];
}

class CoverageEvaluator {
  private radiusSquared: number;
  private cellSize: number;
  private bins = new Map<string, number[]>();
  private grid: Point[];
  private candidates: Candidate[];
  constructor(grid: Point[], candidates: Candidate[], radius: number) {
    this.grid = grid;
    this.candidates = candidates;
    this.radiusSquared = radius ** 2;
    this.cellSize = Math.max(radius, 20);
    grid.forEach(([x, y], index) => {
      const key = `${Math.trunc(x / this.cellSize)},${Math.trunc(y / this.cellSize)}`;
      this.bins.set(key, [...(this.bins.get(key) ?? []), index]);
    });
  }
  private nearby(x: number, y: number) {
    const bx = Math.trunc(x / this.cellSize), by = Math.trunc(y / this.cellSize);
    const result: number[] = [];
    for (const dx of [-1, 0, 1]) for (const dy of [-1, 0, 1]) result.push(...(this.bins.get(`${bx + dx},${by + dy}`) ?? []));
    return result;
  }
  private evaluate(candidate: Candidate, base: number[]) {
    const next = [...base];
    let gain = 0;
    for (const index of this.nearby(...candidate.real_xy)) {
      const dx = this.grid[index][0] - candidate.real_xy[0];
      const dy = this.grid[index][1] - candidate.real_xy[1];
      const d2 = dx * dx + dy * dy;
      if (d2 < this.radiusSquared) {
        const coverage = 1 - d2 / this.radiusSquared;
        if (coverage > base[index]) { gain += coverage - base[index]; next[index] = coverage; }
      }
    }
    return { gain, next };
  }
  greedy(base: number[], count: number) {
    const selected: Candidate[] = [];
    let confidence = [...base];
    const available = this.candidates.map(() => true);
    for (let step = 0; step < count; step++) {
      let bestIndex = -1, bestGain = -1, bestConfidence = confidence;
      this.candidates.forEach((candidate, index) => {
        if (!available[index]) return;
        const result = this.evaluate(candidate, confidence);
        if (result.gain > bestGain) { bestIndex = index; bestGain = result.gain; bestConfidence = result.next; }
      });
      if (bestIndex < 0 || bestGain < 0.001) break;
      selected.push(this.candidates[bestIndex]);
      confidence = bestConfidence;
      available[bestIndex] = false;
    }
    return { selected, confidence };
  }
}

function headlandPath(a: Candidate, b: Candidate, ridges: Record<number, Ridge>, center: Point, theta: number) {
  const [xa, ya] = a.rot_xy, [xb, yb] = b.rot_xy;
  if (a.ridge_idx === b.ridge_idx) return { distance: Math.abs(xa - xb), waypoints: [a.real_xy, b.real_xy] };
  const ra = ridges[a.ridge_idx], rb = ridges[b.ridge_idx];
  const left = xa - ra.left_rot + Math.abs(ya - yb) + xb - rb.left_rot;
  const right = ra.right_rot - xa + Math.abs(ya - yb) + rb.right_rot - xb;
  if (left < right) return { distance: left, waypoints: [a.real_xy, rotatePoint([ra.left_rot, ya], center, theta), rotatePoint([rb.left_rot, yb], center, theta), b.real_xy] };
  return { distance: right, waypoints: [a.real_xy, rotatePoint([ra.right_rot, ya], center, theta), rotatePoint([rb.right_rot, yb], center, theta), b.real_xy] };
}

function nearestNeighbor(nodes: Candidate[], ridges: Record<number, Ridge>, center: Point, theta: number) {
  if (nodes.length <= 2) return nodes.map((_, i) => i);
  const visited = nodes.map(() => false), tour = [0]; visited[0] = true;
  while (tour.length < nodes.length) {
    const last = tour[tour.length - 1]; let best = -1, bestDistance = Infinity;
    nodes.forEach((node, index) => {
      if (visited[index]) return;
      const distance = headlandPath(nodes[last], node, ridges, center, theta).distance;
      if (distance < bestDistance) { best = index; bestDistance = distance; }
    });
    tour.push(best); visited[best] = true;
  }
  return tour;
}

function twoOpt(tour: number[], nodes: Candidate[], ridges: Record<number, Ridge>, center: Point, theta: number) {
  if (nodes.length < 3) return tour;
  const result = [...tour]; let improved = true, iteration = 0;
  while (improved && iteration++ < 50) {
    improved = false;
    for (let i = 1; i < nodes.length - 2; i++) for (let j = i + 1; j < nodes.length; j++) {
      if (j - i === 1) continue;
      const [ai, bi] = [result[i - 1], result[i]], [ci, di] = [result[j], result[(j + 1) % nodes.length]];
      const current = headlandPath(nodes[ai], nodes[bi], ridges, center, theta).distance + headlandPath(nodes[ci], nodes[di], ridges, center, theta).distance;
      const proposed = headlandPath(nodes[ai], nodes[ci], ridges, center, theta).distance + headlandPath(nodes[bi], nodes[di], ridges, center, theta).distance;
      if (proposed < current) { result.splice(i, j - i + 1, ...result.slice(i, j + 1).reverse()); improved = true; }
    }
  }
  return result;
}

export function solvePlanning(polygon: Point[], params: PlanParams): PlanningResult {
  if (polygon.length < 3) throw new Error("请先闭合农田边界多边形。");
  if (Object.values(params).some((v) => !Number.isFinite(v) || v <= 0)) throw new Error("规划参数必须为正数。");
  const [reference, second] = polygon;
  const referencePixels = Math.hypot(second[0] - reference[0], second[1] - reference[1]);
  if (referencePixels < 1) throw new Error("基准边像素长度过短，请重新标定。");
  const scale = referencePixels / params.refLength;
  const ridgePx = params.ridgeDistance * scale, radiusPx = params.sporeRadius * scale;
  const theta = Math.atan2(second[1] - reference[1], second[0] - reference[0]);
  const rotated = polygon.map((point) => rotatePoint(point, reference, -theta));
  const xs = rotated.map((p) => p[0]), ys = rotated.map((p) => p[1]);
  const [minX, maxX, minY, maxY] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  const boxW = maxX - minX, boxH = maxY - minY;
  // 评估网格步长：以 ~1200 个评估点为目标，下限为 1 米（而非 4 米），
  // 使高分辨率地图（如 SLAM 0.05m/px）也能铺满整个农田范围。
  const gridStepPx = Math.max(4, 1 * scale, Math.sqrt((boxW * boxH) / 1200));
  const approximateRidges = Math.max(1, boxH / ridgePx);
  const stepPx = Math.max(1.5 * scale, (boxW * approximateRidges) / 800);
  const candidates: Candidate[] = [], ridges: Record<number, Ridge> = {};
  let scanY = minY + ridgePx / 2, ridgeIndex = 0;
  while (scanY <= maxY) {
    const intersections = scanlineIntersections(scanY, rotated);
    for (let i = 0; i < intersections.length - 1; i += 2) {
      const start = intersections[i], end = intersections[i + 1];
      ridges[ridgeIndex] = { y_rot: scanY, left_rot: start, right_rot: end };
      for (let x = start + stepPx; x <= end - stepPx; x += stepPx) candidates.push({ real_xy: rotatePoint([x, scanY], reference, theta), rot_xy: [x, scanY], ridge_idx: ridgeIndex });
    }
    if (intersections.length) ridgeIndex++;
    scanY += ridgePx;
  }
  const evaluationGrid: Point[] = [];
  for (let x = minX; x <= maxX; x += gridStepPx) for (let y = minY; y <= maxY; y += gridStepPx) {
    const point = rotatePoint([x, y], reference, theta);
    if (pointInPolygon(point, polygon)) evaluationGrid.push(point);
  }
  if (!evaluationGrid.length || !candidates.length) throw new Error("算子空间结构异常，请检查标定范围或放宽参数。");
  const evaluator = new CoverageEvaluator(evaluationGrid, candidates, radiusPx);
  let confidence = evaluationGrid.map(() => 0);
  const roundNodes: Candidate[][] = [];
  for (let round = 0; round < params.rounds; round++) {
    const result = evaluator.greedy(confidence, params.samplesPerRound);
    roundNodes.push(result.selected); confidence = result.confidence;
  }
  const roundTours: number[][] = [], roundSegments: RouteSegment[][] = [];
  roundNodes.forEach((nodes) => {
    const tour = twoOpt(nearestNeighbor(nodes, ridges, reference, theta), nodes, ridges, reference, theta);
    roundTours.push(tour);
    const segments: RouteSegment[] = [];
    tour.forEach((from, index) => {
      const to = tour[(index + 1) % tour.length];
      if (to == null) return;
      const path = headlandPath(nodes[from], nodes[to], ridges, reference, theta);
      const distM = path.distance / scale;
      segments.push({ from, to, dist_m: round2(distM), time_s: Math.round((distM / params.vehicleSpeed) * 10) / 10, waypoints: path.waypoints });
    });
    roundSegments.push(segments);
  });
  const samplingPoints: SamplingPoint[] = [];
  roundNodes.forEach((nodes, round) => nodes.forEach((node, index) => samplingPoints.push({
    point_id: `R${round + 1}-P${index + 1}`, real_xy: node.real_xy,
    x_m: round2((node.real_xy[0] - reference[0]) / scale), y_m: round2((node.real_xy[1] - reference[1]) / scale),
    ridge_idx: node.ridge_idx, round: round + 1, turbidity: null, risk: "pending", read_time: "",
    pcr_ct: null, pcr_conc: null, pcr_qual: "pending", pcr_gene: null, pcr_verdict: "",
  })));
  const covered = confidence.filter((value) => value > 0.5).length;
  const totalDistance = roundSegments.flat().reduce((sum, item) => sum + item.dist_m, 0);
  return {
    scale, reference, rotationTheta: theta, rotationCenter: reference,
    fieldPolygonMeters: polygon.map(([x, y]) => [round2((x - reference[0]) / scale), round2((y - reference[1]) / scale)]),
    ridgeDatabase: ridges, roundNodes, roundTours, roundSegments, evaluationGrid,
    cumulativeConfidence: confidence, gridStepPx, samplingPoints,
    coveragePct: evaluationGrid.length ? covered / evaluationGrid.length * 100 : 0,
    averageConfidence: evaluationGrid.length ? confidence.reduce((a, b) => a + b, 0) / evaluationGrid.length : 0,
    totalDistance, totalTime: roundSegments.flat().reduce((sum, item) => sum + item.time_s, 0), candidateCount: candidates.length,
  };
}

function gaussianRandom(mean = 0, deviation = 1) {
  const u = 1 - Math.random(), v = Math.random();
  return mean + deviation * Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}

export function classifyRisk(value: number, medium: number, high: number): Risk {
  return value < medium ? "low" : value < high ? "medium" : "high";
}

export function simulateTurbidity(point: SamplingPoint, all: SamplingPoint[], polygon: Point[], scale: number, reference: Point, mode: string) {
  if (mode === "hotspot") {
    const centroid = polygonCentroid(polygon);
    const cx = (centroid[0] - reference[0]) / scale, cy = (centroid[1] - reference[1]) / scale;
    return round2(Math.max(0, gaussianRandom(Math.max(50, 600 - Math.hypot(point.x_m - cx, point.y_m - cy) * 8), 40)));
  }
  const xs = all.map((p) => p.x_m), min = Math.min(...xs), max = Math.max(...xs);
  if (mode === "gradient" && max > min) return round2(Math.max(0, gaussianRandom(50 + ((point.x_m - min) / (max - min)) * 500, 30)));
  if (mode === "twozone") return round2(Math.max(0, gaussianRandom(point.x_m < (min + max) / 2 ? 420 : 80, point.x_m < (min + max) / 2 ? 50 : 25)));
  return round2(30 + Math.random() * 570);
}

export function ctToConcentration(ct: number | null, quality: PcrQuality, dilution: number, curve: StandardCurve) {
  if (ct == null || ct <= 0 || quality === "invalid" || curve.slope >= 0) return null;
  const value = 10 ** ((ct - curve.intercept) / curve.slope) * dilution;
  return Number.isFinite(value) ? Math.round(value * 10) / 10 : null;
}

export function pcrVerdict(ct: number | null, quality: PcrQuality, curve: StandardCurve) {
  if (ct == null || quality === "invalid") return "无效";
  if (ct <= curve.positiveCt + 2) return "强阳性";
  if (ct <= curve.negativeCt - 2) return "阳性";
  if (ct >= curve.negativeCt) return "阴性";
  return "弱阳性";
}

export function simulatePcr(point: SamplingPoint, curve: StandardCurve) {
  if (point.turbidity == null) return point;
  const logEstimate = Math.log10(Math.max(1, point.turbidity * (0.5 + Math.random() * 1.5)));
  const ct = Math.max(10, Math.min(40, round2(curve.intercept + curve.slope * logEstimate + gaussianRandom(0, 0.5))));
  const quality: PcrQuality = "valid";
  return { ...point, pcr_ct: ct, pcr_is_simulated: true, pcr_qual: quality, pcr_gene: curve.gene, pcr_conc: ctToConcentration(ct, quality, 1, curve), pcr_verdict: pcrVerdict(ct, quality, curve) };
}

export function pearsonComparison(points: SamplingPoint[], medium: number, high: number) {
  const matched = points.filter((p) => p.turbidity != null && p.pcr_conc != null && p.pcr_qual === "valid");
  if (matched.length < 3) throw new Error("需要至少 3 个同时有粗定和 PCR 数据的样本。");
  const xs = matched.map((p) => p.turbidity as number), ys = matched.map((p) => p.pcr_conc as number);
  const mx = xs.reduce((a, b) => a + b, 0) / xs.length, my = ys.reduce((a, b) => a + b, 0) / ys.length;
  const numerator = xs.reduce((sum, value, i) => sum + (value - mx) * (ys[i] - my), 0);
  const dx = Math.sqrt(xs.reduce((sum, value) => sum + (value - mx) ** 2, 0));
  const dy = Math.sqrt(ys.reduce((sum, value) => sum + (value - my) ** 2, 0));
  const r = dx && dy ? numerator / (dx * dy) : 0;
  const agreement = matched.filter((p) => {
    const risk = classifyRisk(p.turbidity as number, medium, high);
    return (risk === "high" && p.pcr_verdict.includes("阳性")) || (risk === "low" && p.pcr_verdict === "阴性");
  }).length;
  return { count: matched.length, r, agreement, agreementPct: agreement / matched.length * 100 };
}

const STABILITY = {
  A: [0.22, 0.92, 0.2, 0.94], B: [0.16, 0.92, 0.12, 0.89], C: [0.11, 0.92, 0.08, 0.85],
  D: [0.08, 0.9, 0.06, 0.81], E: [0.06, 0.89, 0.03, 0.78], F: [0.04, 0.89, 0.016, 0.74],
} as const;

export function classifyStability(wind: number, daytime: boolean, cloud: number): keyof typeof STABILITY {
  if (daytime) return wind < 2 ? "A" : wind < 3 ? "B" : wind < 5 ? "C" : "D";
  return cloud < 50 && wind < 3 ? "F" : wind < 3 ? "E" : "D";
}

export function gaussianPlume(sourceX: number, sourceY: number, q: number, wind: number, direction: number, stability: keyof typeof STABILITY, targetX: number, targetY: number, height = 1.5) {
  wind = Math.max(0.1, wind);
  const [ay, by, az, bz] = STABILITY[stability];
  const radians = direction * Math.PI / 180, wdx = Math.sin(radians), wdy = -Math.cos(radians);
  const dx = targetX - sourceX, dy = targetY - sourceY;
  const downwind = dx * wdx + dy * wdy, crosswind = dx * -wdy + dy * wdx;
  if (downwind <= 0) return 0;
  const sy = Math.max(ay * downwind ** by, 0.5), sz = Math.max(az * downwind ** bz, 0.3);
  // Ground-level receptor with image-source reflection. This is the standard
  // two-term Gaussian plume solution and avoids the original model's repeated
  // single vertical term, which under-estimated concentrations near the canopy.
  const receptorHeight = Math.max(0.15, height * 0.55);
  const lateral = Math.exp(-0.5 * (crosswind / sy) ** 2);
  const direct = Math.exp(-0.5 * ((receptorHeight - height) / sz) ** 2);
  const reflected = Math.exp(-0.5 * ((receptorHeight + height) / sz) ** 2);
  const travelSeconds = downwind / wind;
  const settling = Math.exp(-0.00045 * travelSeconds);
  return Math.max(0, q / (2 * Math.PI * sy * sz * wind) * lateral * (direct + reflected) * settling);
}

interface SpatialValue {
  x: number;
  y: number;
  value: number;
  quality: number;
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

function median(values: number[]) {
  if (!values.length) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
}

function qualityWeight(quality: PcrQuality) {
  if (quality === "valid") return 1;
  if (quality === "doubtful") return 0.48;
  if (quality === "invalid") return 0.08;
  return 0;
}

function idw(samples: SpatialValue[], x: number, y: number, power = 2, nugget = 2) {
  if (!samples.length) return { value: 0, nearest: Infinity };
  let weighted = 0, weights = 0, nearest = Infinity;
  samples.forEach((sample) => {
    const distance = Math.hypot(x - sample.x, y - sample.y);
    nearest = Math.min(nearest, distance);
    const weight = sample.quality / (distance + nugget) ** power;
    weighted += weight * sample.value; weights += weight;
  });
  return { value: weights ? weighted / weights : samples[0].value, nearest };
}

function robustCalibration(pairs: Array<{ x: number; y: number; weight: number }>, fallbackIntercept: number) {
  if (pairs.length < 2) return { slope: 1, intercept: fallbackIntercept };
  let weights = pairs.map((pair) => pair.weight);
  let slope = 1, intercept = fallbackIntercept;
  for (let iteration = 0; iteration < 3; iteration++) {
    const total = weights.reduce((sum, weight) => sum + weight, 0) || 1;
    const meanX = pairs.reduce((sum, pair, i) => sum + pair.x * weights[i], 0) / total;
    const meanY = pairs.reduce((sum, pair, i) => sum + pair.y * weights[i], 0) / total;
    const covariance = pairs.reduce((sum, pair, i) => sum + weights[i] * (pair.x - meanX) * (pair.y - meanY), 0);
    const variance = pairs.reduce((sum, pair, i) => sum + weights[i] * (pair.x - meanX) ** 2, 0);
    slope = clamp(variance > 1e-8 ? covariance / variance : 1, 0.25, 2.5);
    intercept = meanY - slope * meanX;
    const residuals = pairs.map((pair) => pair.y - (slope * pair.x + intercept));
    const center = median(residuals), mad = Math.max(0.05, median(residuals.map((value) => Math.abs(value - center))) * 1.4826);
    weights = pairs.map((pair, i) => pair.weight * Math.min(1, 1.5 * mad / Math.max(mad, Math.abs(residuals[i] - center))));
  }
  return { slope, intercept };
}

export function buildFusionField(polygon: Point[], planning: PlanningResult, samples: SamplingPoint[], mediumThreshold: number, highThreshold: number): FusionField {
  if (polygon.length < 3 || planning.fieldPolygonMeters.length < 3) throw new Error("需要已闭合的农田边界和有效规划结果。");
  const pcrSamples = samples.filter((sample) => sample.pcr_conc != null && qualityWeight(sample.pcr_qual) > 0).map((sample) => ({ x: sample.x_m, y: sample.y_m, value: Math.log10(Math.max(1, sample.pcr_conc ?? 1)), quality: qualityWeight(sample.pcr_qual) }));
  if (!pcrSamples.length) throw new Error("至少需要 1 个有效或存疑的 PCR 浓度结果。");
  const coarseSamples = samples.filter((sample) => sample.turbidity != null).map((sample) => ({ x: sample.x_m, y: sample.y_m, value: Math.log10(Math.max(1, sample.turbidity ?? 1)), quality: 1 }));
  const paired = samples.filter((sample) => sample.turbidity != null && sample.pcr_conc != null && qualityWeight(sample.pcr_qual) > 0).map((sample) => ({ x: Math.log10(Math.max(1, sample.turbidity ?? 1)), y: Math.log10(Math.max(1, sample.pcr_conc ?? 1)), weight: qualityWeight(sample.pcr_qual) }));
  const pcrMedian = median(pcrSamples.map((sample) => sample.value));
  const coarseMedian = coarseSamples.length ? median(coarseSamples.map((sample) => sample.value)) : Math.log10(Math.max(1, (mediumThreshold + highThreshold) / 2));
  const calibration = robustCalibration(paired, pcrMedian - coarseMedian);
  const calibratedCoarse = coarseSamples.map((sample) => ({ ...sample, value: calibration.slope * sample.value + calibration.intercept }));
  const residualSamples = pcrSamples.map((sample) => {
    const coarse = calibratedCoarse.length ? idw(calibratedCoarse, sample.x, sample.y, 1.7, 3).value : sample.value;
    return { x: sample.x, y: sample.y, value: sample.value - coarse, quality: sample.quality };
  });

  const field = planning.fieldPolygonMeters;
  const xs = field.map((point) => point[0]), ys = field.map((point) => point[1]);
  const rawMinX = Math.min(...xs), rawMaxX = Math.max(...xs), rawMinY = Math.min(...ys), rawMaxY = Math.max(...ys);
  const span = Math.max(rawMaxX - rawMinX, rawMaxY - rawMinY);
  let gridStep = clamp(span / 82, 2, 6);
  let minX = rawMinX - gridStep / 2, maxX = rawMaxX + gridStep / 2, minY = rawMinY - gridStep / 2, maxY = rawMaxY + gridStep / 2;
  let cols = Math.ceil((maxX - minX) / gridStep) + 1, rows = Math.ceil((maxY - minY) / gridStep) + 1;
  if (Math.max(cols, rows) > 105) {
    gridStep = span / 100; minX = rawMinX - gridStep / 2; maxX = rawMaxX + gridStep / 2; minY = rawMinY - gridStep / 2; maxY = rawMaxY + gridStep / 2;
    cols = Math.ceil((maxX - minX) / gridStep) + 1; rows = Math.ceil((maxY - minY) / gridStep) + 1;
  }
  const influenceRange = Math.max(gridStep * 4, Math.hypot(rawMaxX - rawMinX, rawMaxY - rawMinY) / (2 + Math.sqrt(pcrSamples.length)));
  const grid: Point[] = [], concentrations: number[] = [], coarseConcentrations: number[] = [], pcrConcentrations: number[] = [], reliabilities: number[] = [], inside: boolean[] = [];
  let pcrWeightMin = 1, pcrWeightMax = 0;
  for (let col = 0; col < cols; col++) for (let row = 0; row < rows; row++) {
    const x = minX + col * gridStep, y = minY + row * gridStep;
    const directPcr = idw(pcrSamples, x, y, 2.25, Math.max(1, gridStep * .45));
    const coarseLog = calibratedCoarse.length ? idw(calibratedCoarse, x, y, 1.65, Math.max(2, gridStep)).value : directPcr.value;
    const residual = idw(residualSamples, x, y, 2, Math.max(2, gridStep * .7));
    const correctedCoarse = coarseLog + residual.value;
    const distanceConfidence = Math.exp(-directPcr.nearest / influenceRange);
    const densityConfidence = clamp(pcrSamples.length / 6, 0, 1);
    const spatialConfidence = clamp(.76 * distanceConfidence + .24 * densityConfidence, 0, 1);
    const pcrWeight = .82 + .14 * spatialConfidence;
    const fusedLog = pcrWeight * directPcr.value + (1 - pcrWeight) * correctedCoarse;
    const toConcentration = (logValue: number) => clamp(10 ** logValue, 0, 1e8);
    grid.push([x, y]); concentrations.push(toConcentration(fusedLog)); coarseConcentrations.push(toConcentration(coarseLog)); pcrConcentrations.push(toConcentration(directPcr.value));
    reliabilities.push(clamp(.68 + .28 * spatialConfidence, 0, .96)); inside.push(pointInPolygon([x, y], field));
    pcrWeightMin = Math.min(pcrWeightMin, pcrWeight); pcrWeightMax = Math.max(pcrWeightMax, pcrWeight);
  }
  return { grid, concentrations, coarseConcentrations, pcrConcentrations, reliabilities, inside, minX, maxX, minY, maxY, gridStep, cols, rows, calibration: { slope: calibration.slope, intercept: calibration.intercept, pairedCount: paired.length, pcrWeightMin, pcrWeightMax } };
}

export function runForecast(polygon: Point[], planning: PlanningResult, baseline: FusionField, weather: WeatherParams, hoursList = [72, 120, 168]): ForecastResult {
  if (polygon.length < 3 || planning.fieldPolygonMeters.length < 3 || !baseline.grid.length) throw new Error("需要闭合边界和已生成的粗精融合基准场。");
  if (weather.diseaseIndex < 0 || weather.diseaseIndex > 100 || weather.lai < 0.5 || weather.lai > 10 || weather.plantHeight < 0.1 || weather.plantHeight > 5) throw new Error("作物表型参数超出范围。DI:0-100, LAI:0.5-10, 株高:0.1-5m。");
  const horizons = [...new Set(hoursList.map((hours) => Math.max(1, Math.round(hours))))].sort((a, b) => a - b);
  const maxHours = horizons[horizons.length - 1] ?? 72;
  const { cols, rows, gridStep, minX, maxX, minY, maxY } = baseline;
  const indexOf = (col: number, row: number) => col * rows + row;
  let state = Float64Array.from(baseline.concentrations);
  const result: ForecastResult = {}, stability = classifyStability(weather.windSpeed, weather.daytime, weather.cloud);
  const stabilityDiffusion: Record<keyof typeof STABILITY, number> = { A: .31, B: .27, C: .23, D: .19, E: .15, F: .12 };
  const effectiveTemperature = .78 * weather.temperature + .22 * (weather.soilTemperature ?? weather.temperature);
  const temperatureSuitability = Math.exp(-((effectiveTemperature - 24) ** 2) / 72);
  const leafWetness = clamp((weather.leafWetness ?? weather.humidity) / 100, 0, 1);
  const soilMoisture = clamp((weather.soilMoisture ?? 55) / 100, 0, 1);
  const humiditySuitability = clamp(.58 * ((weather.humidity - 42) / 48) + .3 * leafWetness + .12 * soilMoisture, 0, 1);
  const ultravioletStress = clamp((weather.lightIntensity ?? 30000) / 90000, 0, 1);
  const rainWashout = clamp((weather.rainfall ?? 0) / 35, 0, .75);
  const diseasePressure = clamp(weather.diseaseIndex / 100, 0, 1);
  const canopyAttenuation = Math.exp(-.38 * weather.lai);
  const canopyCapture = 1 - Math.exp(-.3 * weather.lai);

  const sampleField = (field: Float64Array, x: number, y: number) => {
    const gx = clamp((x - minX) / gridStep, 0, cols - 1), gy = clamp((y - minY) / gridStep, 0, rows - 1);
    const c0 = Math.floor(gx), r0 = Math.floor(gy), c1 = Math.min(cols - 1, c0 + 1), r1 = Math.min(rows - 1, r0 + 1);
    const tx = gx - c0, ty = gy - r0;
    const top = field[indexOf(c0, r0)] * (1 - tx) + field[indexOf(c1, r0)] * tx;
    const bottom = field[indexOf(c0, r1)] * (1 - tx) + field[indexOf(c1, r1)] * tx;
    return top * (1 - ty) + bottom * ty;
  };

  for (let hour = 1; hour <= maxHours; hour++) {
    const direction = (weather.windDirection + 13 * Math.sin(2 * Math.PI * hour / 24) + 5 * Math.sin(2 * Math.PI * hour / 8) + 360) % 360;
    const radians = direction * Math.PI / 180, windX = Math.sin(radians), windY = -Math.cos(radians);
    const nearCanopyWind = Math.max(.08, weather.windSpeed * canopyAttenuation * (.7 + .3 * weather.plantHeight));
    const displacement = Math.min(gridStep * 1.45, nearCanopyWind * 3600 * .0025);
    const diffusion = clamp(stabilityDiffusion[stability] + Math.min(.09, weather.windSpeed * .015), .1, .38);
    const hourlyGrowth = Math.exp(.002 + .012 * temperatureSuitability * humiditySuitability * (.3 + .7 * diseasePressure));
    const hourlyLoss = .006 + .004 * Math.min(weather.windSpeed, 8) + .006 * (1 - humiditySuitability) + .004 * canopyCapture + .007 * ultravioletStress + .018 * rainWashout;
    const survival = Math.exp(-hourlyLoss);
    const reEmission = .01 + .025 * diseasePressure * temperatureSuitability * (.45 + .55 * humiditySuitability) + .006 * rainWashout * leafWetness;
    const next = new Float64Array(state.length);
    for (let col = 0; col < cols; col++) for (let row = 0; row < rows; row++) {
      const index = indexOf(col, row), [x, y] = baseline.grid[index];
      const advected = sampleField(state, x - windX * displacement, y - windY * displacement);
      let neighborSum = 0, neighborWeight = 0;
      for (let dc = -1; dc <= 1; dc++) for (let dr = -1; dr <= 1; dr++) {
        if (!dc && !dr) continue;
        const nc = col + dc, nr = row + dr; if (nc < 0 || nc >= cols || nr < 0 || nr >= rows) continue;
        const weight = dc && dr ? .7 : 1; neighborSum += state[indexOf(nc, nr)] * weight; neighborWeight += weight;
      }
      const diffused = neighborWeight ? neighborSum / neighborWeight : advected;
      const transported = advected * (1 - diffusion) + diffused * diffusion;
      const localSource = baseline.concentrations[index] * reEmission * (.65 + .35 * baseline.reliabilities[index]);
      next[index] = clamp(transported * survival * hourlyGrowth + localSource, 0, 1e8);
    }
    state = next;
    if (horizons.includes(hour)) {
      const concentrations = Array.from(state);
      const fieldValues = concentrations.filter((_, index) => baseline.inside[index]).sort((a, b) => a - b);
      const peak = fieldValues[fieldValues.length - 1] ?? 0, p90 = fieldValues[Math.floor(Math.max(0, fieldValues.length - 1) * .9)] ?? 0;
      const mean = fieldValues.length ? fieldValues.reduce((sum, value) => sum + value, 0) / fieldValues.length : 0;
      result[hour] = { grid: baseline.grid, concentrations, inside: baseline.inside, minX, maxX, minY, maxY, gridStep, cols, rows, stability, peak, p90, mean, model: "fusion-advection-diffusion" };
    }
  }
  return result;
}
