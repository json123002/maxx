import test from "node:test";
import assert from "node:assert/strict";
import { aggregateMinuteBars } from "./kline-periods.js";

const bar = (date, open, close, vol = 10, amount = 100) => ({
  date, open, close, high: Math.max(open, close) + 1,
  low: Math.min(open, close) - 1, vol, amount, turnover: 0.1,
});

test("5分钟保持原始K线且不改写数据", () => {
  const bars = [bar("2026-10-23 09:35", 10, 11)];
  assert.deepEqual(aggregateMinuteBars(bars, 5), bars);
  assert.notEqual(aggregateMinuteBars(bars, 5), bars);
});

test("20分钟按四根5分钟K线聚合OHLC量额和换手", () => {
  const bars = [
    bar("2026-10-23 09:35", 10, 11, 10, 100),
    bar("2026-10-23 09:40", 11, 12, 20, 200),
    bar("2026-10-23 09:45", 12, 11.5, 30, 300),
    bar("2026-10-23 09:50", 11.5, 13, 40, 400),
    bar("2026-10-23 09:55", 13, 12, 50, 500),
  ];
  const out = aggregateMinuteBars(bars, 20);
  assert.equal(out.length, 2);
  assert.deepEqual(out[0], {
    date: "2026-10-23 09:50", open: 10, close: 13, high: 14, low: 9,
    vol: 100, amount: 1000, turnover: 0.4, pct: 0,
  });
  assert.equal(out[1].open, 13);
  assert.equal(out[1].close, 12);
  assert.ok(out[1].pct < 0);
});

test("30分钟在午休和跨日处重新开始，不混合交易时段", () => {
  const times = [
    "2026-10-23 11:05", "2026-10-23 11:10", "2026-10-23 11:15",
    "2026-10-23 13:05", "2026-10-23 13:10", "2026-10-23 13:15",
    "2026-10-24 09:35", "2026-10-24 09:40", "2026-10-24 09:45",
  ];
  const out = aggregateMinuteBars(times.map((t, i) => bar(t, 10 + i, 11 + i)), 30);
  assert.equal(out.length, 3);
  assert.equal(out[0].date, "2026-10-23 11:15");
  assert.equal(out[1].date, "2026-10-23 13:15");
  assert.equal(out[2].date, "2026-10-24 09:45");
  assert.equal(out[0].vol, 30);
  assert.equal(out[1].vol, 30);
});
