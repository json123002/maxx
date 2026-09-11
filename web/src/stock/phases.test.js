import { test } from 'node:test';
import assert from 'node:assert/strict';
import { detectPhases, selectVisiblePhase } from './phases.js';
import { readFileSync } from 'node:fs';

function bar(close, i, extra = {}) {
  return { date: new Date(Date.UTC(2025, 0, i + 1)).toISOString().slice(0, 10),
    open: close, close, high: close * 1.01, low: close * 0.99, vol: 100, ...extra };
}
const flat = n => Array.from({ length: n }, (_, i) => bar(10 + (i % 2) * 0.05, i));
const bottom = () => [...Array.from({ length: 60 }, (_, i) => bar(15 - i * 0.05, i)), bar(10, 60, { low: 9.8 })];

test('8日起识别短平台，20日及以上归为中期横盘', () => {
  assert.deepEqual(detectPhases([]), []);
  assert.deepEqual(detectPhases(flat(7)), []);
  assert.equal(detectPhases(flat(10))[0].label, '短平台整理');
  const p = detectPhases(flat(25));
  assert.equal(p.length, 1); assert.equal(p[0].confirmedAt, 7);
  assert.equal(p[0].days, 25); assert.equal(p[0].status, 'ongoing');
});
test('缓慢单边上涨不能拼成横盘', () => {
  const bars = Array.from({ length: 100 }, (_, i) => bar(10 * 1.004 ** i, i));
  assert.equal(detectPhases(bars).filter(p => p.type === 'flat').length, 0);
});
test('突破确认日、成交量与跌回箱体终止', () => {
  const bars = [...flat(25), bar(11.4, 25, { vol: 200 }), bar(12, 26), bar(10, 27)];
  const p = detectPhases(bars).find(p => p.type === 'rise');
  assert.equal(p.confirmedAt, 25); assert.equal(p.volumeRatio, 2);
  assert.equal(p.e, 27); assert.equal(p.status, 'completed');
  assert.equal(p.baseStartDate, bars[0].date);
});
test('长上影不确认反弹，至少等待两日', () => {
  const bars = [...bottom(), bar(10.1, 61, { high: 12 }), bar(10.2, 62)];
  let p = detectPhases(bars).find(p => p.type === 'bounce');
  assert.equal(p.status, 'forming'); assert.equal(p.confirmedAt, null);
  bars.push(bar(10.8, 63));
  p = detectPhases(bars).find(p => p.type === 'bounce');
  assert.equal(p.confirmedAt, 63); assert.equal(p.s, 60);
});
test('没有前置下跌不识别底部；创新低替换待确认底部', () => {
  const calm = [...flat(60), bar(9.85, 60), bar(10.8, 61), bar(10.9, 62)];
  assert.equal(detectPhases(calm).filter(p => p.type === 'bounce').length, 0);
  const p = detectPhases([...bottom(), bar(9.5, 61), bar(9.6, 62)]).filter(p => p.type === 'bounce');
  assert.equal(p.length, 1); assert.equal(p[0].s, 61);
});
test('无效价格不跨越；缺量不伪造放量证据', () => {
  const bars = [...flat(25), bar(11.4, 25, { vol: NaN }), bar(12, 26)];
  assert.equal(detectPhases(bars).find(p => p.type === 'rise').volumeRatio, null);
  bars[12].low = NaN;
  assert.ok(detectPhases(bars).every(p => !(p.s <= 12 && p.e >= 12)));
});

test('海鸥股份真实案例：10日平台、8月27日突破、9月11日回撤结束', () => {
  const { bars } = JSON.parse(readFileSync(new URL('./fixtures/603269.json', import.meta.url), 'utf8'));
  const phases = detectPhases(bars);
  const platform = phases.find(p => p.type === 'flat' && p.startDate === '2026-08-13');
  assert.ok(platform); assert.equal(platform.days, 10);
  assert.equal(platform.endDate, '2026-08-26');
  assert.equal(platform.low, 17.09); assert.equal(platform.high, 18.79);
  const rise = phases.find(p => p.type === 'rise' && p.startDate === '2026-08-27');
  assert.ok(rise); assert.equal(rise.confirmedDate, '2026-08-27');
  assert.equal(rise.endDate, '2026-09-11');
  assert.equal(rise.endReason, '高位回撤达到终止阈值');
  assert.equal(selectVisiblePhase(phases, bars.length - 60, bars.length), rise);
  for (let n = 1; n <= bars.length; n++) {
    for (const p of detectPhases(bars.slice(0, n)).filter(p => p.confirmedAt != null)) {
      const later = phases.find(q => q.type === p.type && q.s === p.s);
      assert.ok(later, p.type + ' ' + p.startDate + ' 不应消失');
      assert.equal(later.confirmedAt, p.confirmedAt);
    }
  }
});
test('可见区域无匹配时不展示过期详情，悬停/选中仅在可见区域生效', () => {
  const old = { s: 0, e: 10 }, recent = { s: 90, e: 100 };
  assert.equal(selectVisiblePhase([old], 50, 120, old), null);
  assert.equal(selectVisiblePhase([old, recent], 50, 120, old), recent);
  assert.equal(selectVisiblePhase([old, recent], 0, 120, null, 5), old);
});
test('弱突破需两日站稳，单日上影与小幅越线不确认', () => {
  const bars = [...flat(10), bar(10.35, 10), bar(10.36, 11)];
  assert.equal(detectPhases(bars.slice(0, 11)).filter(p => p.type === 'rise').length, 0);
  const rise = detectPhases(bars).find(p => p.type === 'rise');
  assert.ok(rise); assert.equal(rise.confirmedAt, 11);
  assert.equal(rise.confirmationMethod, '连续两日收盘站稳突破阈值');
});
test('逐日回放：已确认信号不因未来K线变更确认时间', () => {
  const histories = [
    [...flat(25), ...Array.from({ length: 35 }, (_, i) => bar(11.4 + i * 0.1, i + 25))],
    [...bottom(), ...Array.from({ length: 25 }, (_, i) => bar(10.2 + i * 0.3, i + 61))],
  ];
  for (const bars of histories) {
    const full = detectPhases(bars);
    for (let n = 1; n <= bars.length; n++) {
      for (const p of detectPhases(bars.slice(0, n)).filter(p => p.confirmedAt != null)) {
        const later = full.find(q => q.s === p.s && q.type === p.type);
        assert.ok(later); assert.equal(later.confirmedAt, p.confirmedAt);
      }
    }
  }
});
