/* ===== 取数层(移植自旧 screener-analysis.js)=====
   数据:东财日K(qfq,JSONP) → 腾讯(qfq,CORS) → 新浪(不复权,var-JSONP) 三级兜底;资金流仅东财;现价用筛选快照(row.f2)做实时校正。 */
import { jsonp, jsonpVar } from "../utils/jsonp";

export const HIS_HOSTS = ["https://push2his.eastmoney.com"]; // 东财日K唯一可用域名(延迟/编号镜像均为302死链,已实测);失败兜底走腾讯 fqkline
export const KLINE_DAYS = 130;
export const MF_DAYS = 10;

// ===== 取数 =====
export function secidOf(code) { return (/^6/.test(code) ? "1." : "0.") + code; }
// 腾讯行情代码（日K兜底源）：sh/sz/bj 前缀
export function txCodeOf(code) {
  if (/^6/.test(code)) return "sh" + code;
  if (/^[48]/.test(code)) return "bj" + code;
  return "sz" + code;
}

export async function fetchHis(path, params) {
  let lastErr;
  // 东财历史接口有 IP 风控,可能返回 HTML 拦截页:按次数重试
  for (let attempt = 0; attempt <= 2; attempt++) {
    for (const h of HIS_HOSTS) {
      try {
        const d = await jsonp(h + path + (path.includes("?") ? "&" : "?") + params);
        if (d && d.data) return d.data;
        lastErr = new Error("empty");
      } catch (e) { lastErr = e; }
    }
    if (attempt < 2) await new Promise(r => setTimeout(r, 600));
  }
  throw lastErr;
}

export function parseKlines(data) {
  return (data.klines || []).map(s => {
    const a = s.split(",");
    return { date: a[0], open: +a[1], close: +a[2], high: +a[3], low: +a[4],
             vol: +a[5], amount: +a[6], pct: +a[8], turnover: +a[10] };
  }).filter(b => isFinite(b.close));
}

// 新浪日K（不复权,成交量单位为股;无成交额/换手率,涨跌幅由收盘价推算）——最稳定兜底源
export async function fetchKlineSina(symbol, lmt) {
  const varName = "sinaKl" + Math.random().toString(36).slice(2, 8);
  const d = await jsonpVar("https://quotes.sina.cn/cn/api/jsonp_v2.php/var%20" + varName +
    "=/CN_MarketDataService.getKLineData?symbol=" + symbol + "&scale=240&ma=no&datalen=" + Math.min(lmt, 1023), varName);
  const bars = (Array.isArray(d) ? d : []).map(a => ({ date: a.day, open: +a.open, close: +a.close,
    high: +a.high, low: +a.low, vol: +a.volume / 100, amount: NaN, pct: NaN, turnover: NaN }))
    .filter(b => isFinite(b.close));
  bars.forEach((b, i) => { b.pct = i ? (b.close / bars[i - 1].close - 1) * 100 : 0; });
  if (!bars.length) throw new Error("empty");
  return bars;
}

// 东财日K（前复权,JSONP,带重试）
export async function fetchKlineEm(secid, lmt) {
  const d = await fetchHis("/api/qt/stock/kline/get?secid=" + secid +
    "&klt=101&fqt=1&lmt=" + lmt + "&end=20500101" +
    "&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61", "");
  const bars = parseKlines(d);
  if (!bars.length) throw new Error("empty");
  return bars;
}

// 腾讯日K（前复权,CORS fetch;被 WAF 挑战时响应无 CORS 头,fetch 直接 reject → 落下一源）
export async function fetchKlineTx(tx, lmt) {
  const r = await fetch("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=" + tx + ",day,,," + lmt + ",qfq");
  const d = await r.json();
  const node = d && d.data && d.data[tx];
  const arr = (node && (node.qfqday || node.day)) || [];
  const bars = arr.map(a => ({ date: a[0], open: +a[1], close: +a[2], high: +a[3], low: +a[4],
                               vol: +a[5], amount: NaN, pct: NaN, turnover: NaN }))
    .filter(b => isFinite(b.close));
  bars.forEach((b, i) => { b.pct = i ? (b.close / bars[i - 1].close - 1) * 100 : 0; });
  if (!bars.length) throw new Error("empty");
  return bars;
}

// 三级取数链：东财(qfq) → 腾讯(qfq) → 新浪(不复权)，返回 { bars, source } 供口径标注
export async function fetchKlineChain(emSecid, txCode, sinaSym, lmt) {
  let lastErr;
  try { return { bars: await fetchKlineEm(emSecid, lmt), source: "东财日K（前复权）" }; } catch (e) { lastErr = e; }
  try { return { bars: await fetchKlineTx(txCode, lmt), source: "腾讯日K（前复权）" }; } catch (e) { lastErr = e; }
  try { return { bars: await fetchKlineSina(sinaSym, lmt), source: "新浪日K（不复权）" }; } catch (e) { lastErr = e; }
  throw lastErr;
}

export async function fetchKline(code, lmt) {
  const s = txCodeOf(code);   // 腾讯/新浪代码前缀一致（sh/sz/bj）
  return fetchKlineChain(secidOf(code), s, s, lmt);
}

// 资金流日K：f51 日期 f52 主力净流入 f53 小单 f54 中单 f55 大单 f56 超大单（仅东财,无兜底源）
export async function fetchMoneyFlow(code) {
  const d = await fetchHis("/api/qt/stock/fflow/daykline/get?secid=" + secidOf(code) +
    "&klt=101&lmt=" + MF_DAYS + "&fields1=f1,f2,f3,f7&fields2=f51,f52,f53,f54,f55,f56", "");
  return (d.klines || []).map(s => {
    const a = s.split(",");
    return { date: a[0], main: +a[1], small: +a[2], mid: +a[3], big: +a[4], super: +a[5] };
  }).filter(b => isFinite(b.main));
}

let _indexKline = null, _indexKlineErr = null;
// 上证指数日K（相对强度基准），与个股同一三级取数链
export async function fetchIndexKline() {
  if (_indexKline || _indexKlineErr) return _indexKline;
  try {
    const r = await fetchKlineChain("1.000001", "sh000001", "sh000001", 60);
    _indexKline = r.bars;
  } catch (e) { _indexKline = null; _indexKlineErr = e; }
  return _indexKline;
}
