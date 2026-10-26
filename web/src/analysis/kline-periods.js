/* ===== 多周期K线:日K复用三级取数;分钟K由东财5分钟前复权数据聚合 ===== */
import { fetchHis, fetchKline, parseKlines, secidOf } from "./data.js";

export const KLINE_PERIODS = [
  { key: "5", name: "5分", minutes: 5 },
  { key: "20", name: "20分", minutes: 20 },
  { key: "30", name: "30分", minutes: 30 },
  { key: "d", name: "日K", minutes: 0 },
];

function sumField(rows, key) {
  const values = rows.map((r) => r[key]).filter(Number.isFinite);
  return values.length ? values.reduce((s, v) => s + v, 0) : NaN;
}

// 上午、下午分别按固定交易时间聚合，绝不跨午休或跨交易日拼接。
export function aggregateMinuteBars(bars, minutes) {
  if (minutes === 5) return bars.slice();
  if (![20, 30].includes(minutes)) throw new Error("unsupported minute period");
  const groups = [];
  let current = null;
  for (const bar of bars) {
    const [day, time] = String(bar.date).split(" ");
    const [hh, mm] = String(time || "").split(":").map(Number);
    if (!day || !Number.isFinite(hh) || !Number.isFinite(mm)) continue;
    const clock = hh * 60 + mm;
    const morning = clock < 12 * 60;
    const elapsed = Math.max(0, clock - (morning ? 9 * 60 + 30 : 13 * 60));
    // K线时间戳是区间结束时刻,09:35/09:40/09:45/09:50 同属首个20分钟。
    const key = `${day}|${morning ? "am" : "pm"}|${Math.floor(Math.max(0, elapsed - 1) / minutes)}`;
    if (!current || current.key !== key) {
      current = { key, rows: [] };
      groups.push(current);
    }
    current.rows.push(bar);
  }
  const out = groups.map(({ rows }) => ({
    date: rows.at(-1).date,
    open: rows[0].open,
    close: rows.at(-1).close,
    high: Math.max(...rows.map((r) => r.high)),
    low: Math.min(...rows.map((r) => r.low)),
    vol: sumField(rows, "vol"),
    amount: sumField(rows, "amount"),
    turnover: sumField(rows, "turnover"),
    pct: NaN,
  }));
  out.forEach((b, i) => {
    const prev = out[i - 1]?.close;
    b.pct = i && prev ? (b.close / prev - 1) * 100 : 0;
  });
  return out;
}

export async function fetchPeriodKline(code, period) {
  if (period === "d") return fetchKline(code, 250);
  const minutes = KLINE_PERIODS.find((p) => p.key === period)?.minutes;
  if (!minutes) throw new Error("unsupported kline period");
  const d = await fetchHis("/api/qt/stock/kline/get?secid=" + secidOf(code) +
    "&klt=5&fqt=1&lmt=1023&end=20500101" +
    "&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61", "");
  const base = parseKlines(d);
  if (!base.length) throw new Error("empty");
  return {
    bars: aggregateMinuteBars(base, minutes),
    source: `东财${minutes}分钟（前复权${minutes === 5 ? "" : " · 5分钟聚合"}）`,
  };
}
