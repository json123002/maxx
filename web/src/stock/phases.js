/* 日K历史阶段识别：确认日只使用截至当日数据，区间终点随新K线延伸。
 * 起点是复盘定位，不是当日信号；规则是启发式定义，不代表胜率。 */
export const PHASE_RULES = {
  flatDays: 8, flatRange: 0.12, flatDrift: 0.04, maxEfficiency: 0.55,
  breakoutDays: 10, breakoutPct: 0.015, trendDays: 40,
  bottomLookback: 20, drawdown: 0.15, reboundDays: 20, reboundPct: 0.08,
};
const valid = b => b && [b.open, b.close, b.high, b.low].every(Number.isFinite)
  && b.low > 0 && b.low <= Math.min(b.open, b.close)
  && b.high >= Math.max(b.open, b.close);
const mean = xs => xs.reduce((a, b) => a + b, 0) / xs.length;

export function selectVisiblePhase(phases, start, end, selected = null, hover = -1) {
  const visible = phases.filter(p => p.s < end && p.e >= start);
  const hits = hover >= start && hover < end ? visible.filter(p => p.s <= hover && p.e >= hover) : [];
  const latest = list => [...list].sort((a, b) => b.e - a.e || b.s - a.s)[0] || null;
  return hits.length ? latest(hits) : visible.includes(selected) ? selected : latest(visible);
}

export function detectPhases(bars) {
  const r = PHASE_RULES, n = bars.length, out = [];
  // 坏数据切断区间，不删除行，保持图表下标一致。
  function bounds(s, e) {
    const part = bars.slice(s, e + 1);
    if (!part.length || !part.every(valid)) return null;
    return { low: Math.min(...part.map(b => b.low)), high: Math.max(...part.map(b => b.high)) };
  }
  function sideways(s, e) {
    const b = bounds(s, e);
    if (!b || b.high / b.low - 1 > r.flatRange) return false;
    const edge = Math.min(5, Math.floor((e - s + 1) / 3));
    const first = mean(bars.slice(s, s + edge).map(b => b.close));
    const last = mean(bars.slice(e - edge + 1, e + 1).map(b => b.close));
    let travel = 0;
    for (let j = s + 1; j <= e; j++) travel += Math.abs(bars[j].close - bars[j - 1].close);
    const efficiency = travel ? Math.abs(bars[e].close - bars[s].close) / travel : 0;
    return Math.abs(last / first - 1) <= r.flatDrift && efficiency <= r.maxEfficiency;
  }
  function atrAt(i) {
    const values = [];
    for (let j = Math.max(0, i - 13); j <= i; j++) {
      if (!valid(bars[j])) return 0;
      const prev = j && valid(bars[j - 1]) ? bars[j - 1].close : bars[j].open;
      values.push(Math.max(bars[j].high - bars[j].low, Math.abs(bars[j].high - prev), Math.abs(bars[j].low - prev)));
    }
    return mean(values);
  }
  function volumeAt(i) {
    const prev = bars.slice(Math.max(0, i - 5), i).map(b => b.vol);
    if (prev.length < 5 || !prev.every(v => Number.isFinite(v) && v > 0)
      || !Number.isFinite(bars[i].vol) || bars[i].vol <= 0) return null;
    return bars[i].vol / mean(prev);
  }
  function add(s, e, type, confirmedAt, status, extra = {}) {
    const b = bounds(s, e);
    if (!b) return;
    out.push({ s, e, type, label: { flat: '横盘整理', rise: '横盘后上涨', bounce: '触底反弹' }[type],
      ...b, confirmedAt, status, days: e - s + 1,
      startDate: bars[s].date, endDate: bars[e].date,
      confirmedDate: confirmedAt == null ? null : bars[confirmedAt].date,
      pct: (bars[e].close / bars[s].close - 1) * 100,
      volumeRatio: confirmedAt == null ? null : volumeAt(confirmedAt), ...extra });
  }
  // 固定起点约束整个箱体振幅，避免滚动窗口拼出缓慢爬升的横盘。
  for (let s = 0; s + r.flatDays <= n;) {
    let e = s + r.flatDays - 1;
    if (!sideways(s, e)) { s++; continue; }
    const confirmed = e;
    // 先检查是否离开既有平台，再决定扩展，防止突破K被吞进箱体。
    while (e + 1 < n && sideways(s, e + 1)) {
      const box = bounds(s, e);
      if (bars[e + 1].close >= box.high + Math.max(box.high * r.breakoutPct, atrAt(e) * 0.5)) break;
      e++;
    }
    const box = bounds(s, e);
    add(s, e, 'flat', confirmed, e === n - 1 ? 'ongoing' : 'completed', {
      label: e - s + 1 < 20 ? '短平台整理' : '横盘整理',
      rangePct: (box.high / box.low - 1) * 100,
    });
    let bo = -1;
    const threshold = box.high + Math.max(box.high * r.breakoutPct, atrAt(e) * 0.5);
    let confirmationMethod = '';
    for (let j = e + 1; j <= Math.min(n - 1, e + r.breakoutDays); j++) {
      if (!valid(bars[j]) || bars[j].close < box.low) break;
      if (bars[j].close >= threshold) {
        const strong = bars[j].close >= box.high * 1.03;
        const volume = volumeAt(j) >= 1.5;
        const sustained = j > e + 1 && bars[j - 1].close >= threshold;
        if (strong || volume || sustained) {
          bo = j;
          confirmationMethod = strong ? '收盘突破箱顶≥3%' : volume ? '突破且量达前5日均量1.5倍' : '连续两日收盘站稳突破阈值';
          break;
        }
      }
    }
    if (bo >= 0) {
      // 不回填随后最高点：确认后逐日延伸，跌回箱顶或达到波动回撤阈值结束。
      let end = bo, peak = bars[bo].close, stopped = false, endReason = '';
      // 确认日冻结波动容忍度，范围8%~15%，不会随未来波动回改阈值。
      const pullback = Math.min(0.15, Math.max(0.08, 2 * atrAt(bo) / bars[bo].close));
      const limit = bo + r.trendDays - 1;
      for (let j = bo + 1; j <= Math.min(n - 1, limit); j++) {
        if (!valid(bars[j])) { stopped = true; endReason = '数据中断'; break; }
        end = j; peak = Math.max(peak, bars[j].close);
        if (bars[j].close < box.high || bars[j].close / peak - 1 <= -pullback) {
          stopped = true; endReason = bars[j].close < box.high ? '跌回平台 · 突破失效' : '高位回撤达到终止阈值'; break;
        }
      }
      add(bo, end, 'rise', bo, stopped || end >= limit ? 'completed' : 'ongoing',
        { baseStartDate: bars[s].date, baseEndDate: bars[e].date, referencePrice: box.high,
          label: endReason.startsWith('跌回') ? '平台突破失效' : '平台突破上涨',
          confirmationMethod, threshold, pullbackPct: pullback * 100,
          maxGainPct: (peak / bars[bo].close - 1) * 100,
          endReason: endReason || (end >= limit ? '观察期结束' : '尚未触发结束条件') });
      // 平台扫描独立于上涨延伸，允许识别上涨途中的再次整理。
      s = e + 1;
    } else s = e + 1;
  }
  // 底部必须有前置下跌；至少等待两日，以收盘反弹排除长上影假反弹。
  for (let i = r.bottomLookback; i < n; i++) {
    const prev = bounds(i - r.bottomLookback, i - 1);
    if (!prev || !valid(bars[i]) || bars[i].low >= prev.low
      || bars[i].low / prev.high - 1 > -r.drawdown) continue;
    const low = bars[i].low;
    let confirmed = null, e = i, invalidated = false;
    const limit = i + r.reboundDays;
    for (let j = i + 1; j <= Math.min(n - 1, limit); j++) {
      if (!valid(bars[j]) || bars[j].low < low) { invalidated = true; break; }
      e = j;
      if (j >= i + 2 && bars[j].close >= low * (1 + r.reboundPct)) { confirmed = j; break; }
    }
    if (confirmed != null) {
      let peak = bars[confirmed].close, stopped = false;
      for (let j = confirmed + 1; j <= Math.min(n - 1, limit); j++) {
        if (!valid(bars[j])) { stopped = true; break; }
        e = j; peak = Math.max(peak, bars[j].close);
        if (bars[j].low < low || bars[j].close / peak - 1 <= -0.08) { stopped = true; break; }
      }
      add(i, e, 'bounce', confirmed, stopped || e >= limit ? 'completed' : 'ongoing',
        { label: '阶段低点反弹', referencePrice: low, reboundPct: (bars[e].close / low - 1) * 100,
          confirmationMethod: '创20日低点且前置回落≥15%，等待2日后收盘反弹≥8%' });
      i = e;
    } else if (!invalidated && e === n - 1 && e < limit) {
      add(i, e, 'bounce', null, 'forming', { referencePrice: low, reboundPct: (bars[e].close / low - 1) * 100 });
    }
  }
  return out.sort((a, b) => a.s - b.s || a.e - b.e);
}
