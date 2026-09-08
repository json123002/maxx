/* ===== 格式化/转义/排序等工具(移植自旧 screener-core.js)===== */

export const fmtYiT = (v) => (typeof v === "number" ? (v / 1e8).toFixed(1) + " 亿" : "—"); // 表格用
export const fmtYiC = (v) => (typeof v === "number" ? (v / 1e8).toFixed(1) + "亿" : "—");  // 卡片用(紧凑)
export const fmtN = (v, d = 2) => (typeof v === "number" ? v.toFixed(d) : "—");
export const cls = (v) => (v > 0 ? "up" : v < 0 ? "down" : "");
export const esc = (s) =>
  String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

// 排序取值:非数值(null 等)排到最后,避免污染数值比较
const num = (v) => (typeof v === "number" ? v : -Infinity);
export function cmpRows(key, dir) {
  return (a, b) => {
    const va = a[key], vb = b[key];
    if (typeof va === "string" || typeof vb === "string")
      return String(va).localeCompare(String(vb), "zh") * dir;
    return (num(va) - num(vb)) * dir;
  };
}

// 区间读取:最低>最高时自动交换,避免填反导致 0 结果
export function rangeVal(min, max) {
  let a = parseFloat(min), b = parseFloat(max);
  if (!isNaN(a) && !isNaN(b) && a > b) { const t = a; a = b; b = t; }
  return [a, b];
}

// 个股详情跳转:东方财富(自动区分沪/深/北)
export function quoteUrl(code) {
  if (/^6/.test(code)) return "https://quote.eastmoney.com/sh" + code + ".html";
  if (/^[48]/.test(code)) return "https://quote.eastmoney.com/bj" + code + ".html";
  return "https://quote.eastmoney.com/sz" + code + ".html";
}
