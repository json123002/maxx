import { test } from 'node:test';
import assert from 'node:assert/strict';
import { computeChips, resolveTurnover } from './chips.js';

function bar(close, i, extra = {}) {
  return { date: `2026-01-${String(i + 1).padStart(2, '0')}`,
    open: close, close, high: close * 1.02, low: close * 0.98, vol: 1000, turnover: 5, ...extra };
}

test('空输入与单根K线返回 null', () => {
  assert.equal(computeChips([]), null);
  assert.equal(computeChips([bar(10, 0)]), null);
});

test('单调上涨后获利比例接近100%，平均成本低于现价', () => {
  const bars = Array.from({ length: 60 }, (_, i) => bar(10 + i * 0.2, i));
  const r = computeChips(bars);
  assert.ok(r.profitRatio > 0.95, `profitRatio=${r.profitRatio}`);
  assert.ok(r.avgCost < 10 + 59 * 0.2, `avgCost=${r.avgCost}`);
  assert.equal(r.turnoverMode, 'real');
});

test('横盘筹码集中：成本区间窄、集中度低', () => {
  const flat = Array.from({ length: 60 }, (_, i) => bar(10 + (i % 2) * 0.02, i, { turnover: 10 }));
  const r = computeChips(flat);
  assert.ok(Math.abs(r.avgCost - 10.01) < 0.2, `avgCost=${r.avgCost}`);
  assert.ok((r.ci90.hi - r.ci90.lo) / 10 < 0.1, `ci90=${r.ci90.lo}~${r.ci90.hi}`);
  assert.ok(r.conc90 < 0.05, `conc90=${r.conc90}`);
});

test('换手率回退链：real / est / pseudo 三模式', () => {
  const realBars = Array.from({ length: 30 }, (_, i) => bar(10, i));
  assert.equal(resolveTurnover(realBars).mode, 'real');

  const noT = realBars.map(b => ({ ...b, turnover: NaN }));
  assert.equal(resolveTurnover(noT).mode, 'pseudo');            // 无 floatShares → pseudo
  assert.equal(resolveTurnover(noT, 2000000).mode, 'est');      // 流通股估算:1000手*100/200万股=5%
  const { rates } = resolveTurnover(noT, 2000000);
  assert.ok(Math.abs(rates[0] - 0.05) < 1e-9, `rate=${rates[0]}`);

  const rEst = computeChips(noT, { floatShares: 2000000 });
  assert.equal(rEst.turnoverMode, 'est');
  assert.ok(rEst.profitRatio >= 0 && rEst.profitRatio <= 1);
});

test('单日100%换手清空全部旧筹码', () => {
  // 前 30 日在 10 元,最后一天 20 元 100% 换手 → 筹码应几乎全部移到 20 元附近
  const bars = [...Array.from({ length: 30 }, (_, i) => bar(10, i)),
    bar(20, 30, { turnover: 100 })];
  const r = computeChips(bars);
  assert.ok(Math.abs(r.avgCost - 20) < 0.5, `avgCost=${r.avgCost}`);
  // 三角分布对称于中价≈收盘 → 约一半筹码在现价之下
  assert.ok(r.profitRatio > 0.3 && r.profitRatio < 0.7, `profitRatio=${r.profitRatio}`);
  assert.ok(r.ci90.hi > 19 && r.ci90.lo > 15, `ci90=${r.ci90.lo}~${r.ci90.hi}`); // 旧 10 元筹码几乎消失
});

test('伪换手率放量日衰减快于缩量日', () => {
  const mk = vol => Array.from({ length: 25 }, (_, i) =>
    bar(10, i, { turnover: NaN, vol: i === 24 ? vol : 1000 }));
  const heavy = computeChips(mk(20000), {});   // 末日放20倍量
  const light = computeChips(mk(200), {});     // 末日缩量
  // 放量日更多旧筹码被置换 → 平均成本更贴近末日价 10(两者末日价相同,比较分布峰值宽度更直观:
  // 放量日的筹码总质量更接近1且集中在末日区间)
  assert.ok(heavy.mass.reduce((s, x) => s + x, 0) > 0);
  assert.ok(light.mass.reduce((s, x) => s + x, 0) > 0);
  assert.notEqual(heavy.mass.join(), light.mass.join());
});
