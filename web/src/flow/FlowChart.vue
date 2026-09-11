<script setup>
/* ===== 板块资金累计分时曲线 =====
   纯 SVG 渲染,颜色走 CSS 变量自动跟随明暗主题;暖色系=净流入端,冷色系=净流出端。
   props.rows: [{ name, series: [[hh:mm, 亿], ...] }] */
import { computed, reactive } from "vue";
import { fmtYi, fmtYiShort } from "./capital-flow";

const props = defineProps({
  rows: { type: Array, default: () => [] },
  compact: { type: Boolean, default: false },
  emptyText: { type: String, default: "暂无可用的分钟级资金数据" },
});

const INFLOW_COLORS = ["#ff667b", "#ff8b72", "#f7aa62", "#f4c363", "#db8d9c", "#ff9f9f", "#d97286", "#e9aa78", "#ff7e95", "#e3b068", "#f28c81", "#d88f75"];
const OUTFLOW_COLORS = ["#32c9dc", "#4aa9ea", "#668ee8", "#57b7ce", "#5b9fc8", "#7aa7db", "#3fb5c5", "#6b8fc0", "#65c4cf", "#7b9fd1", "#4dabc0", "#6f98bc"];

const W = 1120;
const geom = computed(() => {
  const left = 66, right = props.compact ? 170 : 190, top = 28, bottom = 42;
  const h = props.compact ? 410 : 500;
  return { left, right, top, bottom, h, pw: W - left - right, ph: h - top - bottom };
});

/* 时间轴:所有曲线分钟标签的并集 */
const axis = computed(() => {
  const seen = new Set();
  for (const row of props.rows) for (const [label] of row.series) seen.add(label);
  return [...seen].sort();
});
const indexOf = computed(() => new Map(axis.value.map((label, i) => [label, i])));

/* 值域:±8% 边距,强制包含 0 轴 */
const extent = computed(() => {
  const values = props.rows.flatMap((r) => r.series.map((p) => p[1]));
  if (!values.length) return { min: -1, max: 1 };
  let min = Math.min(...values), max = Math.max(...values);
  const pad = (max - min) * 0.08 || 1;
  min -= pad; max += pad;
  if (min > 0) min = 0;
  if (max < 0) max = 0;
  return { min, max };
});

const x = (i) => geom.value.left + (geom.value.pw * i) / Math.max(1, axis.value.length - 1);
const y = (v) => geom.value.top + (geom.value.ph * (extent.value.max - v)) / Math.max(1e-4, extent.value.max - extent.value.min);

/* 美观刻度步长(1/2/2.5/5/10 × 10^n) */
function niceStep(span, target = 6) {
  if (!Number.isFinite(span) || span <= 0) return 1;
  const raw = span / target;
  const power = 10 ** Math.floor(Math.log10(raw));
  const scaled = raw / power;
  const nice = scaled <= 1 ? 1 : scaled <= 2 ? 2 : scaled <= 2.5 ? 2.5 : scaled <= 5 ? 5 : 10;
  return nice * power;
}

const gridLines = computed(() => {
  const { min, max } = extent.value;
  const step = niceStep(max - min);
  const lines = [];
  const digits = Math.abs(step) < 1 ? 1 : 0;
  for (let v = Math.ceil(min / step) * step; v <= max + step * 0.001; v += step) {
    lines.push({ y: y(v), zero: Math.abs(v) < step * 0.01, text: (v > 0 ? "+" : "") + v.toFixed(digits) });
  }
  return lines;
});

const xTicks = computed(() => {
  const every = Math.max(1, Math.floor(axis.value.length / (props.compact ? 5 : 7)));
  return axis.value
    .map((label, i) => ({ label, i }))
    .filter(({ i }) => i === 0 || i === axis.value.length - 1 || i % every === 0)
    .map(({ label, i }) => ({ label, x: x(i) }));
});

/* 曲线:按末值正负取暖/冷色 */
const lines = computed(() =>
  props.rows.map((row, i) => {
    const finalValue = row.series[row.series.length - 1][1];
    const color = finalValue >= 0
      ? INFLOW_COLORS[i % INFLOW_COLORS.length]
      : OUTFLOW_COLORS[(props.rows.length - i - 1) % OUTFLOW_COLORS.length];
    const points = row.series.map(([label, v]) => `${x(indexOf.value.get(label)).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
    const [lastLabel, lastValue] = row.series[row.series.length - 1];
    return { name: row.name, color, points, finalValue, endX: x(indexOf.value.get(lastLabel)), endY: y(lastValue) };
  })
);

/* 末端标签:纵向最小间距防重叠,越界整体回移 */
const endLabels = computed(() => {
  const gap = props.compact ? 13 : 15;
  const labels = lines.value
    .map((l) => ({ name: l.name, color: l.color, value: l.finalValue, y: l.endY }))
    .sort((a, b) => a.y - b.y);
  for (let i = 1; i < labels.length; i += 1) {
    if (labels[i].y - labels[i - 1].y < gap) labels[i].y = labels[i - 1].y + gap;
  }
  if (labels.length) {
    const over = labels[labels.length - 1].y - (geom.value.h - geom.value.bottom - 4);
    if (over > 0) labels.forEach((l) => { l.y -= over; });
    const under = geom.value.top - labels[0].y;
    if (under > 0) labels.forEach((l) => { l.y += under; });
  }
  return labels;
});

/* 悬停十字取点 + 浮动明细 */
const tip = reactive({ show: false, left: 0, top: 0, time: "", items: [] });
const plotLeft = computed(() => geom.value.left);
const plotTop = computed(() => geom.value.top);
const plotW = computed(() => geom.value.pw);
const plotH = computed(() => geom.value.ph);

function onMove(event) {
  const svg = event.currentTarget.ownerSVGElement;
  if (!svg || !axis.value.length) { tip.show = false; return; }
  const rect = svg.getBoundingClientRect();
  const viewX = ((event.clientX - rect.left) / rect.width) * W;
  const ratio = (viewX - geom.value.left) / geom.value.pw;
  const index = Math.max(0, Math.min(axis.value.length - 1, Math.round(ratio * (axis.value.length - 1))));
  const label = axis.value[index];
  const byLabel = new Map(props.rows.map((row) => [row.name, new Map(row.series)]));
  tip.items = lines.value
    .map((l) => ({ name: l.name, color: l.color, value: byLabel.get(l.name)?.get(label) }))
    .filter((it) => Number.isFinite(it.value))
    .sort((a, b) => b.value - a.value);
  if (!tip.items.length) { tip.show = false; return; }
  tip.time = label;
  tip.show = true;
  const targetPx = ((geom.value.left + (geom.value.pw * index) / Math.max(1, axis.value.length - 1)) / W) * rect.width;
  const wrap = svg.parentElement.getBoundingClientRect();
  const tipEl = event.currentTarget.parentElement.parentElement.querySelector(".flowTip");
  const tw = tipEl?.offsetWidth || 200, th = tipEl?.offsetHeight || 120;
  let left = targetPx + 12;
  if (left + tw > wrap.width - 8) left = targetPx - tw - 12;
  let top = event.clientY - wrap.top - th / 2;
  top = Math.max(10, Math.min(top, wrap.height - th - 8));
  tip.left = Math.max(8, left);
  tip.top = top;
}
const fmt = fmtYi;
const fmtShort = fmtYiShort;
</script>

<template>
  <div class="flowChart">
    <div v-if="!rows.length" class="chartEmpty">{{ emptyText }}</div>
    <template v-else>
      <svg :viewBox="`0 0 ${W} ${geom.h}`" role="img" aria-label="板块主力资金累计分时曲线">
        <!-- 水平网格 + 零轴 -->
        <template v-for="(g, i) in gridLines" :key="`g${i}`">
          <line :x1="geom.left" :y1="g.y" :x2="geom.left + geom.pw" :y2="g.y"
                :class="g.zero ? 'grid zero' : 'grid'" :stroke-width="g.zero ? 1.2 : 1" />
          <text :x="geom.left - 9" :y="g.y + 4" text-anchor="end" class="tick">{{ g.text }}</text>
        </template>
        <!-- 纵向时间刻度 -->
        <template v-for="t in xTicks" :key="`t${t.label}`">
          <line :x1="t.x" :y1="geom.top" :x2="t.x" :y2="geom.top + geom.ph" class="grid" />
          <text :x="t.x" :y="geom.h - 14" text-anchor="middle" class="tick">{{ t.label }}</text>
        </template>
        <!-- 资金曲线 -->
        <polyline v-for="l in lines" :key="l.name" :points="l.points" fill="none"
                  :stroke="l.color" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" opacity=".92" />
        <circle v-for="l in lines" :key="`e${l.name}`" :cx="l.endX" :cy="l.endY" r="3.2"
                :fill="l.color" class="endDot" stroke-width="1.5" />
        <!-- 末端标签 -->
        <template v-for="l in endLabels" :key="`n${l.name}`">
          <circle :cx="geom.left + geom.pw + 12" :cy="l.y" r="3" :fill="l.color" />
          <text :x="geom.left + geom.pw + 22" :y="l.y + 4" class="endName">{{ l.name }}</text>
          <text :x="W - 8" :y="l.y + 4" text-anchor="end" class="endValue" :fill="l.color">{{ fmtShort(l.value) }}</text>
        </template>
        <!-- 悬停热区 -->
        <rect :x="plotLeft" :y="plotTop" :width="plotW" :height="plotH" fill="transparent"
              @mousemove="onMove" @mouseleave="tip.show = false" />
      </svg>
      <div v-show="tip.show" class="flowTip" :style="{ left: tip.left + 'px', top: tip.top + 'px' }">
        <div class="tipTime">{{ tip.time }}</div>
        <div v-for="it in tip.items" :key="it.name" class="tipRow">
          <span class="tipName"><i class="tipDot" :style="{ background: it.color }"></i>{{ it.name }}</span>
          <b class="tipValue">{{ fmt(it.value, 1) }}</b>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.flowChart { position: relative; }
.flowChart svg { display: block; width: 100%; height: auto; }
.chartEmpty {
  min-height: 320px; display: grid; place-items: center; padding: 30px;
  color: var(--dim); text-align: center; line-height: 1.7; font-size: 12px;
  white-space: pre-line;
}
.grid { stroke: var(--line); }
.grid.zero { stroke: var(--line-strong); }
.tick { font-size: 11px; fill: var(--dim); font-family: var(--mono); }
.endDot { stroke: var(--panel); }
.endName { font-size: 11px; fill: var(--txt); }
.endValue { font-size: 11px; font-weight: 700; font-family: var(--mono); }
.flowTip {
  position: absolute; z-index: 5;
  width: min(230px, calc(100% - 28px));
  padding: 10px 11px;
  border: 1px solid var(--line-strong); border-radius: 11px;
  background: color-mix(in srgb, var(--panel) 95%, transparent);
  box-shadow: 0 16px 35px rgba(0, 0, 0, .28);
  pointer-events: none;
  -webkit-backdrop-filter: blur(12px); backdrop-filter: blur(12px);
}
.tipTime { color: var(--dim); font-size: 10px; margin-bottom: 7px; font-family: var(--mono); }
.tipRow { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 3px 0; font-size: 10px; }
.tipName { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--txt); }
.tipDot { display: inline-block; width: 6px; height: 6px; margin-right: 6px; border-radius: 50%; }
.tipValue { white-space: nowrap; font-family: var(--mono); font-weight: 600; }
</style>
