<script setup>
/* ===== 筹码分布图(canvas,无第三方图表库,与 KChart 同一渲染骨架)=====
   - 横向直方图:y 轴=价格(与 chips 计算窗口全域对齐),x 轴=筹码质量
   - 获利盘(成本<现价)红调 / 套牢盘绿调;叠加平均成本虚线 + 90% 成本带
   - 主题变量取色,明暗切换/窗口缩放自动重绘 */
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import { themeMode } from "../utils/theme";

const props = defineProps({
  chips: { type: Object, default: null },   // computeChips() 返回值
});

const wrap = ref(null);
const cv = ref(null);
let ro = null;

const cssVar = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const fmtP = (v) => (typeof v === "number" && isFinite(v) ? v.toFixed(2) : "—");

const PAD_R = 44, PAD_T = 52, AXIS_H = 20;   // 与 KChart 同口径,便于并排视觉对齐

function draw() {
  const el = cv.value, box = wrap.value;
  if (!el || !box) return;
  const dpr = window.devicePixelRatio || 1;
  const W = Math.max(box.clientWidth, 10), H = Math.max(box.clientHeight, 10);
  el.width = W * dpr; el.height = H * dpr;
  el.style.width = W + "px"; el.style.height = H + "px";
  const ctx = el.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, W, H);

  const c = props.chips;
  if (!c || !c.mass.length) return;

  const plotW = W - PAD_R - 4;
  const y = (v) => PAD_T + ((c.priceHi - v) / (c.priceHi - c.priceLo)) * (H - PAD_T - AXIS_H);
  const maxM = Math.max(...c.mass) || 1;

  const cUp = cssVar("--up"), cDown = cssVar("--down");
  const cLine = cssVar("--line"), cDim = cssVar("--dim");

  ctx.font = "10.5px " + (cssVar("--mono") || "monospace");
  ctx.textBaseline = "middle";

  // 90% 成本带
  if (c.ci90) {
    ctx.fillStyle = cssVar("--accent-dim") || "rgba(74,144,255,0.12)";
    ctx.fillRect(2, y(c.ci90.hi), plotW, Math.max(1, y(c.ci90.lo) - y(c.ci90.hi)));
  }

  // 筹码柱(获利红 / 套牢绿,半透明叠色)
  const binH = Math.max(1, (H - PAD_T - AXIS_H) / c.mass.length);
  c.mass.forEach((m, i) => {
    if (m <= 0) return;
    const p = c.priceLo + (i + 0.5) * c.binW;
    const yc = y(c.priceLo + (i + 1) * c.binW);
    ctx.fillStyle = p < c.price ? cUp : cDown;
    ctx.globalAlpha = 0.28 + 0.62 * (m / maxM);
    ctx.fillRect(2, yc, (m / maxM) * plotW, Math.max(binH, 1));
  });
  ctx.globalAlpha = 1;

  // 平均成本虚线
  if (isFinite(c.avgCost)) {
    ctx.strokeStyle = "#f5a623"; ctx.setLineDash([4, 3]); ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(2, y(c.avgCost)); ctx.lineTo(2 + plotW, y(c.avgCost)); ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = "#f5a623"; ctx.textAlign = "left";
    ctx.fillText("均 " + fmtP(c.avgCost), 4, y(c.avgCost) - 7);
  }

  // 现价线
  if (isFinite(c.price)) {
    ctx.strokeStyle = cDim; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(2, y(c.price)); ctx.lineTo(2 + plotW, y(c.price)); ctx.stroke();
  }

  // 右侧价格刻度(4 档)
  ctx.textAlign = "left";
  for (let g = 0; g <= 3; g++) {
    const v = c.priceHi - ((c.priceHi - c.priceLo) * g) / 3;
    ctx.fillStyle = cDim;
    ctx.fillText(fmtP(v), W - PAD_R + 4, y(v));
  }
}

onMounted(() => {
  draw();
  ro = new ResizeObserver(draw);
  ro.observe(wrap.value);
});
onBeforeUnmount(() => ro && ro.disconnect());
watch(() => props.chips, draw);
watch(themeMode, () => setTimeout(draw, 0));
</script>

<template>
  <div ref="wrap" class="chipWrap">
    <canvas ref="cv"></canvas>
    <div v-if="!chips" class="chipEmpty">筹码数据不足</div>
  </div>
</template>

<style scoped>
.chipWrap { position: relative; width: 100%; height: 100%; min-height: 0; overflow: hidden; }
canvas { display: block; }
.chipEmpty { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; color: var(--dim); font-size: 12px; }
</style>
