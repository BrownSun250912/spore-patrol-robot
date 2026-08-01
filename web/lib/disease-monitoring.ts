export type CropType = "小麦" | "玉米" | "苹果" | "葡萄";

export interface ImageFeatures {
  yellow: number;
  brown: number;
  white: number;
  orange: number;
  dark: number;
  green: number;
  saturation: number;
  texture: number;
}

export interface DiseaseProfile {
  id: string;
  name: string;
  crop: CropType;
  pathogen: string;
  symptoms: string;
  favorable: string;
  gene: string;
  management: string;
  prototype: ImageFeatures;
}

export interface DiseasePrediction {
  diseaseId: string;
  name: string;
  confidence: number;
  distance: number;
}

export interface DiseaseEvaluationRecord {
  id: string;
  createdAt: string;
  fieldName: string;
  crop: CropType;
  imageName: string;
  imageUrl: string;
  predictedId: string;
  confidence: number;
  confirmedId: string;
  features: ImageFeatures;
}

export const DISEASE_DATABASE: DiseaseProfile[] = [
  { id: "wheat_fusarium", name: "小麦赤霉病", crop: "小麦", pathogen: "禾谷镰刀菌复合群", symptoms: "穗部早期水浸状褐斑，后期出现粉红色霉层与白穗。", favorable: "扬花期连续阴雨、湿度>80%、20–28℃。", gene: "EF1-α-F/EF1-α-R", management: "抽穗扬花期重点监测，雨前预防、雨后补防，高风险区定点施药。", prototype: { yellow:.22,brown:.26,white:.18,orange:.12,dark:.16,green:.18,saturation:.48,texture:.42 } },
  { id: "wheat_powdery", name: "小麦白粉病", crop: "小麦", pathogen: "禾本科布氏白粉菌", symptoms: "叶片出现白色粉状霉斑，后期霉层变灰并产生黑色小点。", favorable: "15–22℃、田间郁闭、湿度较高但叶面无明水。", gene: "ITS1-F/ITS4-R", management: "降低群体密度、控制氮肥，中心病株出现后及时精准施药。", prototype: { yellow:.08,brown:.07,white:.42,orange:.03,dark:.08,green:.25,saturation:.25,texture:.55 } },
  { id: "wheat_stripe_rust", name: "小麦条锈病", crop: "小麦", pathogen: "条形柄锈菌", symptoms: "叶片形成沿叶脉排列的鲜黄色条状夏孢子堆。", favorable: "9–16℃、高湿、春季降雨和远距离孢子传播。", gene: "ITS1-F/ITS4-R", management: "发现中心病团立即封锁施药，并对下风向田块加强巡检。", prototype: { yellow:.34,brown:.08,white:.05,orange:.24,dark:.08,green:.22,saturation:.68,texture:.47 } },
  { id: "maize_northern_blight", name: "玉米大斑病", crop: "玉米", pathogen: "突脐蠕孢", symptoms: "叶片形成大型梭形灰褐色病斑，潮湿时产生灰黑色霉层。", favorable: "18–27℃、连续高湿、密植和通风不良。", gene: "ITS1-F/ITS4-R", management: "清除病残体，改善通风，发病初期针对高风险叶层施药。", prototype: { yellow:.13,brown:.39,white:.08,orange:.09,dark:.28,green:.15,saturation:.42,texture:.51 } },
  { id: "maize_rust", name: "玉米锈病", crop: "玉米", pathogen: "玉米柄锈菌", symptoms: "叶片散生黄褐至铁锈色孢子堆，破裂后释放粉状孢子。", favorable: "16–25℃、高湿、多露和风传播条件。", gene: "ITS1-F/ITS4-R", management: "监测孢子浓度突增，发病初期对下风向区域优先防治。", prototype: { yellow:.18,brown:.24,white:.04,orange:.31,dark:.15,green:.18,saturation:.72,texture:.58 } },
  { id: "apple_ring_rot", name: "苹果轮纹病", crop: "苹果", pathogen: "葡萄座腔菌", symptoms: "果实出现褐色同心轮纹病斑，后期软腐并形成黑色小粒点。", favorable: "高温高湿、果园郁闭、伤口和降雨传播。", gene: "β-tub-F/β-tub-R", management: "清除病果病枝、保护伤口，幼果期和雨季前实施保护性防治。", prototype: { yellow:.12,brown:.36,white:.05,orange:.18,dark:.31,green:.10,saturation:.54,texture:.49 } },
  { id: "apple_scab", name: "苹果黑星病", crop: "苹果", pathogen: "苹果黑星菌", symptoms: "叶片和果面形成橄榄褐色绒状斑，后期龟裂畸形。", favorable: "春季低温多雨、叶面持续湿润超过9小时。", gene: "ITS1-F/ITS4-R", management: "依据叶面湿度确定侵染窗口，雨前保护、雨后及时铲除治疗。", prototype: { yellow:.09,brown:.23,white:.04,orange:.06,dark:.42,green:.17,saturation:.38,texture:.61 } },
  { id: "grape_downy", name: "葡萄霜霉病", crop: "葡萄", pathogen: "葡萄生单轴霉", symptoms: "叶面出现油渍状黄斑，叶背形成白色霜状霉层。", favorable: "18–25℃、降雨频繁、叶面湿度持续偏高。", gene: "TEF-F/TEF-R", management: "改善架面通风，降低叶面湿度，侵染窗口前后精准施药。", prototype: { yellow:.26,brown:.08,white:.28,orange:.05,dark:.08,green:.24,saturation:.38,texture:.52 } },
];

const FEATURE_KEYS: Array<keyof ImageFeatures> = ["yellow", "brown", "white", "orange", "dark", "green", "saturation", "texture"];
const FEATURE_WEIGHTS: ImageFeatures = { yellow:1.25,brown:1.25,white:1.2,orange:1.1,dark:1,green:.65,saturation:.75,texture:1.15 };

function rgbToHsv(r: number, g: number, b: number) {
  r /= 255; g /= 255; b /= 255;
  const max = Math.max(r, g, b), min = Math.min(r, g, b), delta = max - min;
  let hue = 0;
  if (delta) hue = max === r ? 60 * (((g - b) / delta) % 6) : max === g ? 60 * ((b - r) / delta + 2) : 60 * ((r - g) / delta + 4);
  if (hue < 0) hue += 360;
  return { h: hue, s: max ? delta / max : 0, v: max };
}

export function extractImageFeatures(image: HTMLImageElement): ImageFeatures {
  const canvas = document.createElement("canvas"), size = 160;
  canvas.width = size; canvas.height = size;
  const context = canvas.getContext("2d", { willReadFrequently: true });
  if (!context) throw new Error("浏览器无法读取图像像素。");
  context.drawImage(image, 0, 0, size, size);
  const data = context.getImageData(0, 0, size, size).data;
  let yellow = 0, brown = 0, white = 0, orange = 0, dark = 0, green = 0, saturation = 0, texture = 0, count = 0;
  let previousValue = 0;
  for (let i = 0; i < data.length; i += 4) {
    if (data[i + 3] < 100) continue;
    const hsv = rgbToHsv(data[i], data[i + 1], data[i + 2]);
    yellow += hsv.h >= 42 && hsv.h < 72 && hsv.s > .28 ? 1 : 0;
    orange += hsv.h >= 12 && hsv.h < 42 && hsv.s > .35 ? 1 : 0;
    brown += hsv.h >= 10 && hsv.h < 45 && hsv.s > .28 && hsv.v < .68 ? 1 : 0;
    green += hsv.h >= 72 && hsv.h < 175 && hsv.s > .2 ? 1 : 0;
    white += hsv.s < .18 && hsv.v > .72 ? 1 : 0;
    dark += hsv.v < .28 ? 1 : 0;
    saturation += hsv.s;
    if (count) texture += Math.abs(hsv.v - previousValue);
    previousValue = hsv.v; count++;
  }
  const divisor = Math.max(1, count);
  return { yellow:yellow/divisor,brown:brown/divisor,white:white/divisor,orange:orange/divisor,dark:dark/divisor,green:green/divisor,saturation:saturation/divisor,texture:texture/divisor };
}

export function classifyDiseaseImage(features: ImageFeatures, crop: CropType) {
  const candidates = DISEASE_DATABASE.filter((disease) => disease.crop === crop);
  const ranked = candidates.map((disease) => {
    const distance = Math.sqrt(FEATURE_KEYS.reduce((sum, key) => sum + FEATURE_WEIGHTS[key] * (features[key] - disease.prototype[key]) ** 2, 0));
    return { disease, distance, score: Math.exp(-distance * 8) };
  }).sort((a, b) => a.distance - b.distance);
  const total = ranked.reduce((sum, item) => sum + item.score, 0) || 1;
  return ranked.map<DiseasePrediction>((item) => ({ diseaseId: item.disease.id, name: item.disease.name, confidence: item.score / total, distance: item.distance }));
}

export function calculateDiseaseMetrics(records: DiseaseEvaluationRecord[]) {
  const confirmed = records.filter((record) => record.confirmedId);
  const correct = confirmed.filter((record) => record.predictedId === record.confirmedId).length;
  const labels = DISEASE_DATABASE.map((disease) => disease.id);
  const confusion = labels.map((actual) => labels.map((predicted) => confirmed.filter((record) => record.confirmedId === actual && record.predictedId === predicted).length));
  const perClass = labels.map((id, index) => {
    const tp = confusion[index][index], actual = confusion[index].reduce((sum, value) => sum + value, 0);
    const predicted = confusion.reduce((sum, row) => sum + row[index], 0);
    const precision = predicted ? tp / predicted : 0, recall = actual ? tp / actual : 0;
    return { id, samples: actual, precision, recall, f1: precision + recall ? 2 * precision * recall / (precision + recall) : 0 };
  });
  return { sampleCount: confirmed.length, correct, accuracy: confirmed.length ? correct / confirmed.length : null, confusion, perClass };
}
