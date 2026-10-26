import test from "node:test";
import assert from "node:assert/strict";
import { sentimentFromStats, limitPctOf } from "./strategies.js";

test("完整市场统计保留平盘口径，缺背景不伪造候选池情绪", () => {
  const s = sentimentFromStats({ valid: 100, up: 40, down: 30, flat: 30,
    limit_up: 10, limit_down: 10, big_down: 5 }, null);
  assert.equal(s.temp, 46);
  assert.equal(s.down, 30);
  assert.equal(s.valid, 100);
  assert.equal(sentimentFromStats(null, null), null);
  assert.equal(sentimentFromStats({ valid: 0 }, null), null);
});

test("北交所920代码采用30%基础幅度", () => {
  assert.equal(limitPctOf("920001"), 30);
  assert.equal(limitPctOf("300001"), 20);
});
