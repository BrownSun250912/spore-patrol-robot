# 多模态农田孢子监测与病害扩散预警系统 V4.0 - Web 控制台

本项目以 `main_inspection_system_v4_compliance.py` 为功能基准，将原 Tkinter 桌面程序迁移为本地浏览器控制台。

## 本地运行

```powershell
npm install
npm run dev
```

浏览器打开：<http://localhost:3000>

网站在本机运行，不需要 ChatGPT 登录，也不会自动上传或公开发布数据。

## 使用顺序

1. 路径规划：导入底图（可选），点击“标定不规则边界”，在画布上依次点击顶点，闭合边界并运行规划。
2. 田间检测：在地图或表格选择采样点，可单点读取或顺序全检。
3. PCR 分析：选择样本录入 Ct，也可导入 CSV 或批量生成模拟数据；之后生成融合热力图和对比分析。
4. 趋势预警：加载 PCR 源点，设置气象、环境与表型参数，运行 3/5/7 天预测。
5. 使用各页按钮导出 JSON、CSV、TXT、GeoJSON 或 HTML 报告。

鼠标滚轮缩放地图，按住 Shift 加左键拖拽平移，右键可在边界标定过程中撤销顶点。

完整迁移清单见 [FUNCTION_PARITY.md](./FUNCTION_PARITY.md)。
