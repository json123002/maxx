/* ===== 自定义指标注册表与纯逻辑(移植自旧 screener-metrics.js)=====
   前后端分离版:指标过滤由后端 SQL 完成(见 useScreener.js buildQuery),
   旧版 metricPass 不再使用,仅保留展示/列逻辑。
   全部为纯函数:指标状态数组 [{k, min, max}] 由 useScreener 持有,作为参数传入,
   min/max 为输入框原始字符串,空 = 不设界。 */

// 基础展示列已包含的指标不再重复出列,只参与过滤
export const BASE_COL_KEYS = ["f6", "f20", "f9"];

const numOrNull = (v) => (typeof v === "number" ? v : null);
const yiOrNull = (v) => (typeof v === "number" ? v / 1e8 : null);

// 指标注册表:k = 东财字段, disp = 原始值 → 过滤/显示用数值(如成交额转亿), fmt = 数值 → 展示文本
export const METRICS = [
  { k: "f6",  name: "成交额",       unit: "亿", disp: yiOrNull,  fmt: (v) => v.toFixed(1) + " 亿" },
  { k: "f20", name: "总市值",       unit: "亿", disp: yiOrNull,  fmt: (v) => v.toFixed(1) + " 亿" },
  { k: "f21", name: "流通市值",     unit: "亿", disp: yiOrNull,  fmt: (v) => v.toFixed(1) + " 亿" },
  { k: "f9",  name: "市盈率",       unit: "",   disp: numOrNull, fmt: (v) => v.toFixed(1) },
  { k: "f23", name: "市净率",       unit: "",   disp: numOrNull, fmt: (v) => v.toFixed(2) },
  { k: "f7",  name: "振幅",         unit: "%",  disp: numOrNull, fmt: (v) => v.toFixed(2) + "%" },
  { k: "f10", name: "量比",         unit: "",   disp: numOrNull, fmt: (v) => v.toFixed(2) },
  { k: "f24", name: "60日涨幅",     unit: "%",  disp: numOrNull, fmt: (v) => v.toFixed(2) + "%" },
  { k: "f25", name: "年初至今涨幅", unit: "%",  disp: numOrNull, fmt: (v) => v.toFixed(2) + "%" },
];

export function metricDef(k) {
  return METRICS.find((m) => m.k === k);
}

// 原始字段值 → 展示文本
export function fmtMetric(d, raw) {
  const v = d.disp(raw);
  return v === null ? "—" : d.fmt(v);
}

// 「+ 添加指标」下拉的可选项(排除已添加的)
export function metricAddOptions(active) {
  return METRICS.filter((m) => !active.some((a) => a.k === m.k));
}

// 添加指标(返回新数组;非法或重复时原样返回)
export function addMetric(active, k) {
  if (!metricDef(k) || active.some((a) => a.k === k)) return active;
  return active.concat([{ k, min: "", max: "" }]);
}

// 移除指标(返回新数组)
export function removeMetric(active, k) {
  return active.filter((a) => a.k !== k);
}

// 恢复本地保存的指标状态(过滤无效 k,补默认空界)
export function normalizeMetricsState(arr) {
  return (Array.isArray(arr) ? arr : [])
    .filter((m) => m && metricDef(m.k))
    .map((m) => ({ k: m.k, min: m.min || "", max: m.max || "" }));
}

// buildQuery 用:仅设了区间的指标参与后端过滤
export function metricsQueryParam(active) {
  return active.filter((m) => m.min !== "" || m.max !== "");
}

// 折叠面板摘要中的指标部分
export function metricsSummaryPart(active) {
  return active
    .map((m) => {
      const d = metricDef(m.k);
      if (!m.min && !m.max) return d.name;
      return d.name + " " + (m.min || "") + "~" + (m.max || "∞") + (d.unit || "");
    })
    .join(" · ");
}

// 手机卡片附加指标文本(跳过基础列已有的,避免重复展示)
export function metricCardExtras(active, r) {
  const s = active
    .filter((m) => !BASE_COL_KEYS.includes(m.k))
    .map((m) => {
      const d = metricDef(m.k);
      return d.name + " " + fmtMetric(d, r[m.k]);
    })
    .join(" · ");
  return s ? " · " + s : "";
}

// 桌面表格需要追加的指标列(跳过基础列)
export function metricExtraCols(active) {
  return active.map((m) => metricDef(m.k)).filter((d) => !BASE_COL_KEYS.includes(d.k));
}
