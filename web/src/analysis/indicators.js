/* ===== 技术指标(移植自旧 screener-analysis.js)===== */

export function smaLast(arr, n) {
  if (arr.length < n) return null;
  let s = 0; for (let i = arr.length - n; i < arr.length; i++) s += arr[i];
  return s / n;
}
export function emaSeries(arr, n) {
  const k = 2 / (n + 1), out = [arr[0]];
  for (let i = 1; i < arr.length; i++) out.push(arr[i] * k + out[i - 1] * (1 - k));
  return out;
}
export function rsiWilder(closes, n = 14) {
  if (closes.length < n + 1) return null;
  let g = 0, l = 0;
  for (let i = 1; i <= n; i++) { const d = closes[i] - closes[i - 1]; if (d > 0) g += d; else l -= d; }
  let ag = g / n, al = l / n;
  for (let i = n + 1; i < closes.length; i++) {
    const d = closes[i] - closes[i - 1];
    ag = (ag * (n - 1) + Math.max(d, 0)) / n; al = (al * (n - 1) + Math.max(-d, 0)) / n;
  }
  return al === 0 ? 100 : 100 - 100 / (1 + ag / al);
}
export function macdLast(closes) {
  const e12 = emaSeries(closes, 12), e26 = emaSeries(closes, 26);
  const dif = e12.map((v, i) => v - e26[i]);
  const dea = emaSeries(dif, 9);
  const i = dif.length - 1;
  return { dif: dif[i], dea: dea[i], difPrev: dif[i - 1], deaPrev: dea[i - 1] };
}

export function macdSeries(closes) {
  if (!closes || closes.length < 2) return [];
  const e12 = emaSeries(closes, 12), e26 = emaSeries(closes, 26);
  const dif = e12.map((v, i) => v - e26[i]);
  const dea = emaSeries(dif, 9);
  return dif.map((v, i) => ({
    dif: v,
    dea: dea[i],
    macd: (v - dea[i]) * 2,
  }));
}

export function kdjSeries(bars, n = 9) {
  if (!bars || !bars.length) return [];
  const out = [];
  let prevK = 50, prevD = 50;
  for (let i = 0; i < bars.length; i++) {
    const start = Math.max(0, i - n + 1);
    const window = bars.slice(start, i + 1);
    let high = -Infinity, low = Infinity;
    for (const b of window) {
      if (b.high != null && b.high > high) high = b.high;
      if (b.low != null && b.low < low) low = b.low;
    }
    const close = bars[i].close;
    let rsv = 50;
    if (high > low && close != null) {
      rsv = ((close - low) / (high - low)) * 100;
    }
    const k = (2 / 3) * prevK + (1 / 3) * rsv;
    const d = (2 / 3) * prevD + (1 / 3) * k;
    const j = 3 * k - 2 * d;
    out.push({ k, d, j });
    prevK = k;
    prevD = d;
  }
  return out;
}

// 摆动高低点（左右各 k 根确认的分形）
export function pivots(bars, k = 3) {
  const hi = [], lo = [];
  for (let i = k; i < bars.length - k; i++) {
    let isH = true, isL = true;
    for (let j = i - k; j <= i + k; j++) {
      if (j === i) continue;
      if (bars[j].high >= bars[i].high) isH = false;
      if (bars[j].low <= bars[i].low) isL = false;
    }
    if (isH) hi.push({ p: bars[i].high, d: bars[i].date });
    if (isL) lo.push({ p: bars[i].low, d: bars[i].date });
  }
  return { hi, lo };
}
export const pctChg = (closes, n) => closes.length > n ? (closes[closes.length - 1] / closes[closes.length - 1 - n] - 1) * 100 : null;

// 候选价位合并为区间（间距 1.5% 内归并），返回 [{lo,hi,srcs,score}]
export function makeZones(points) {
  const sorted = [...points].sort((a, b) => a.p - b.p), zones = [];
  for (const pt of sorted) {
    const last = zones[zones.length - 1];
    if (last && pt.p <= last.hi * 1.015) { last.hi = Math.max(last.hi, pt.p); last.srcs.push(pt.src); }
    else zones.push({ lo: pt.p * 0.997, hi: pt.p * 1.003, srcs: [pt.src] });
  }
  return zones.map(z => ({ ...z, score: z.srcs.length, mid: (z.lo + z.hi) / 2 }));
}
