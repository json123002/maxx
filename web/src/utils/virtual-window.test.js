import test from 'node:test';
import assert from 'node:assert/strict';
import { virtualWindow } from './virtual-window.js';

test('数千条数据仅渲染视口附近，滚动前后总高度一致', () => {
  for (const offset of [0, 34000, 170000]) {
    const w = virtualWindow(5000, offset);
    assert.ok(w.end - w.start <= 24);
    assert.equal(w.top + (w.end - w.start) * 34 + w.bottom, 5000 * 34);
  }
  assert.ok(virtualWindow(5000, 170000).end === 5000);
});
test('空列表、少量数据和筛选后旧滚动位置均不越界', () => {
  assert.deepEqual(virtualWindow(0, 10000), {start:0,end:0,top:0,bottom:0});
  assert.deepEqual(virtualWindow(3, 10000), {start:0,end:3,top:0,bottom:0});
  assert.equal(virtualWindow(100, -10).start, 0);
});
