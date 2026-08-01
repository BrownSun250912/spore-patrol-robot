// SLAM PGM 地图解析模块
// 支持 ROS 2 SLAM Toolbox / map_server 输出的 PGM 灰度图 + YAML 元数据。
// 浏览器端可直接解析，为"真实地图导入路径规划"提供地理坐标系底子。
// 来源参考: ROS nav2 map_saver_cli 输出格式 (PGM P5/P2 + YAML)。

export interface SlamMapInfo {
  /** 每像素对应的世界坐标米数 */
  resolution: number;
  /** 地图原点世界坐标 (米) */
  origin: [number, number];
  width: number;
  height: number;
}

export interface ParsedSlamMap {
  /** 可直接赋给 <img src> 的 data URL */
  imageUrl: string;
  info: SlamMapInfo;
  /** PGM 原始二进制（P5）或 ASCII（P2）灰度值矩阵，0=障碍 255=自由 */
  cells: Uint8Array;
  /** 该地图是否成功带出分辨率信息（决定能否自动换算比例尺） */
  hasResolution: boolean;
}

function parseYamlPairs(text: string): Record<string, string> {
  const result: Record<string, string> = {};
  for (const line of text.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#") || trimmed.includes("%")) continue;
    const match = trimmed.match(/^([\w.]+)\s*:\s*(.*)$/);
    if (match) result[match[1].trim()] = match[2].trim();
  }
  return result;
}

function parsePgmHeader(bytes: Uint8Array): { width: number; height: number; maxVal: number; dataOffset: number; format: "P5" | "P2" } {
  let offset = 0;
  const readToken = (): string => {
    while (offset < bytes.length && /\s/.test(String.fromCharCode(bytes[offset]))) offset++;
    // 跳过注释行
    while (bytes[offset] === 0x23 /* '#' */) {
      while (offset < bytes.length && bytes[offset] !== 0x0a) offset++;
      while (offset < bytes.length && /\s/.test(String.fromCharCode(bytes[offset]))) offset++;
    }
    let token = "";
    while (offset < bytes.length && !/\s/.test(String.fromCharCode(bytes[offset]))) {
      token += String.fromCharCode(bytes[offset++]);
    }
    return token;
  };
  const format = readToken() as "P5" | "P2";
  const width = Number(readToken());
  const height = Number(readToken());
  const maxVal = Number(readToken());
  return { width, height, maxVal, dataOffset: offset, format };
}

/** 将 PGM 灰度图渲染为可视化底图。255=可通行(白/浅灰)，0=障碍(黑)，-1(未知)=中性灰 */
export function renderSlamPgmToImageUrl(cells: Uint8Array, width: number, height: number, maxVal = 255, resolution = 0.05): { imageUrl: string; dataUrl: string } {
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d");
  if (!context) return { imageUrl: "", dataUrl: "" };
  const imageData = context.createImageData(width, height);
  for (let i = 0; i < cells.length; i++) {
    const v = cells[i];
    const gray = v === 255 ? 235 : v === 0 ? 18 : Math.round(200 - (v / maxVal) * 40);
    imageData.data[i * 4] = gray;
    imageData.data[i * 4 + 1] = gray;
    imageData.data[i * 4 + 2] = gray;
    imageData.data[i * 4 + 3] = 255;
  }
  context.putImageData(imageData, 0, 0);
  const dataUrl = canvas.toDataURL("image/png");
  return { imageUrl: dataUrl, dataUrl };
}

/**
 * 解析 SLAM PGM + YAML 地图文件。
 * 返回渲染好的底图 URL、分辨率信息与灰度矩阵。
 */
export async function parseSlamMap(pgmFile: File, yamlText?: string): Promise<ParsedSlamMap> {
  const buffer = await pgmFile.arrayBuffer();
  const bytes = new Uint8Array(buffer);
  const header = parsePgmHeader(bytes);
  const { width, height, maxVal, dataOffset, format } = header;
  const cells = new Uint8Array(width * height);
  if (format === "P5") {
    const bitDepth = maxVal > 255 ? 2 : 1;
    for (let i = 0; i < cells.length; i++) {
      const idx = dataOffset + i * bitDepth;
      cells[i] = bitDepth === 2 ? (bytes[idx] << 8) | bytes[idx + 1] : bytes[idx];
    }
  } else {
    const text = new TextDecoder().decode(bytes.subarray(dataOffset));
    const tokens = text.trim().split(/\s+/).map((t) => Number(t));
    for (let i = 0; i < cells.length && i < tokens.length; i++) cells[i] = tokens[i];
  }
  const resolution = 0.05;
  let info: SlamMapInfo = { resolution, origin: [0, 0], width, height };
  let hasResolution = false;
  if (yamlText) {
    const pairs = parseYamlPairs(yamlText);
    const parsedResolution = Number(pairs.resolution);
    if (Number.isFinite(parsedResolution) && parsedResolution > 0) {
      info = { ...info, resolution: parsedResolution };
      hasResolution = true;
    }
    const originMatch = pairs.origin?.match(/\[([-\d.eE+]+)[,\s]+([-\d.eE+]+)/);
    if (originMatch) info = { ...info, origin: [Number(originMatch[1]), Number(originMatch[2])] };
  }
  const { imageUrl } = renderSlamPgmToImageUrl(cells, width, height, maxVal, resolution);
  return { imageUrl, info, cells, hasResolution };
}
