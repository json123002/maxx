/* ===== 筹码分布(CYQ 成本分布)纯计算 =====
   经典三角分布衰减模型:每日既有筹码按 (1-换手率) 衰减留存,
   当日换手部分按 [最低,最高] 三角分布(顶点在半价处)注入。
   换手率回退链:bar.turnover(东财真实值,百分数)
     → vol/floatShares 估算(兜底源无换手字段;vol 单位为手,乘 100 转股)
     → 伪换手率(5% × vol/20日均量,clamp 0.5%~30%),保证缩量日衰减慢、放量日衰减快。
   输出:分布质量数组 + 获利比例/平均成本/90%·70%成本区间/集中度。 */

// 解析每根 K 线的换手比例(0~1);返回 { rates, mode }
export function resolveTurnover(bars, floatShares = null) {
  const real = bars.map(b => (isFinite(b.turnover) ? b.turnover / 100 : NaN));
  const realCnt = real.filter(isFinite).length;
  if (realCnt >= bars.length * 0.8) {
    // 真实换手为主(个别缺失日用 20 日均量折算补齐,避免衰减断档)
    const vs = bars.map(b => b.vol).filter(isFinite);
    const meanV = vs.length ? vs.reduce((s, x) => s + x, 0) / vs.length : 0;
    const fb = meanV > 0 ? real.filter(isFinite).reduce((s, x) => s + x, 0) / Math.max(realCnt, 1) : 0.02;
    return { rates: real.map(r => (isFinite(r) ? r : fb)), mode: "real" };
  }
  if (floatShares > 0) {
    return {
      rates: bars.map(b => (isFinite(b.vol) ? clamp((b.vol * 100) / floatShares, 0, 1) : 0)),
      mode: "est",
    };
  }
  const vs = bars.map(b => (isFinite(b.vol) ? b.vol : 0));
  return {
    rates: vs.map((v, i) => {
      const win = vs.slice(Math.max(0, i - 20), i + 1);
      const m = win.reduce((s, x) => s + x, 0) / win.length;
      return m > 0 ? clamp(0.05 * (v / m), 0.005, 0.3) : 0.01;
    }),
    mode: "pseudo",
  };
}

function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }

// 最小质量窗口:按质量降序累积至 pct,取覆盖价格区间(同花顺近似口径)
function costInterval(mass, priceLo, binW, pct, total) {
  const order = [];
  for (let i = 0; i < mass.length; i++) if (mass[i] > 0) order.push([mass[i], i]);
  order.sort((a, b) => b[0] - a[0]);
  let acc = 0, loI = Infinity, hiI = -Infinity;
  for (const [m, i] of order) {
    acc += m; loI = Math.min(loI, i); hiI = Math.max(hiI, i);
    if (acc >= pct * total) break;
  }
  if (hiI < 0) return null;
  return { lo: priceLo + loI * binW, hi: priceLo + (hiI + 1) * binW };
}

// bars: 升序 [{date,open,close,high,low,vol,turnover}]
// 返回 null 表示数据不足
export function computeChips(bars, { bins = 120, floatShares = null, price = null } = {}) {
  const valid = (bars || []).filter(b => isFinite(b.high) && isFinite(b.low) && b.high >= b.low);
  if (valid.length < 2) return null;

  let priceLo = Infinity, priceHi = -Infinity;
  for (const b of valid) { priceLo = Math.min(priceLo, b.low); priceHi = Math.max(priceHi, b.high); }
  if (!(priceHi > priceLo)) return null;
  const binW = (priceHi - priceLo) / bins;

  const { rates, mode } = resolveTurnover(valid, floatShares);
  const chips = new Float64Array(bins);

  valid.forEach((b, t) => {
    const rate = clamp(rates[t], 0, 1);
    // 1) 旧筹码衰减
    for (let i = 0; i < bins; i++) chips[i] *= 1 - rate;
    // 2) 当日换手注入:[low,high] 三角分布,顶点在中价
    const iLo = Math.max(0, Math.floor((b.low - priceLo) / binW));
    const iHi = Math.min(bins - 1, Math.floor((b.high - priceLo) / binW));
    const apexP = (b.low + b.high) / 2;
    const halfW = Math.max((b.high - b.low) / 2, binW);
    let wSum = 0;
    const w = [];
    for (let i = iLo; i <= iHi; i++) {
      const p = priceLo + (i + 0.5) * binW;
      const wt = Math.max(0, 1 - Math.abs(p - apexP) / halfW);
      w.push([i, wt]); wSum += wt;
    }
    if (wSum <= 0) w.push([Math.min(bins - 1, Math.max(0, iLo)), 1]), wSum = 1;
    for (const [i, wt] of w) chips[i] += rate * (wt / wSum);
  });

  const total = chips.reduce((s, x) => s + x, 0);
  if (total <= 0) return null;

  const curPrice = (price != null && isFinite(price)) ? price : valid[valid.length - 1].close;
  let profit = 0, costSum = 0;
  for (let i = 0; i < bins; i++) {
    const p = priceLo + (i + 0.5) * binW;
    costSum += p * chips[i];
    if (p < curPrice) profit += chips[i];
  }
  const ci90 = costInterval(chips, priceLo, binW, 0.9, total);
  const ci70 = costInterval(chips, priceLo, binW, 0.7, total);
  const conc = (ci) => (ci && ci.hi + ci.lo > 0 ? (ci.hi - ci.lo) / (ci.hi + ci.lo) : null);

  return {
    priceLo, priceHi, binW,
    mass: Array.from(chips),
    price: curPrice,
    profitRatio: profit / total,
    avgCost: costSum / total,
    ci70, ci90,
    conc70: conc(ci70), conc90: conc(ci90),
    turnoverMode: mode,   // real=真实换手 / est=流通股估算 / pseudo=相对量估算
    days: valid.length,
  };
}
